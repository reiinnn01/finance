import calendar
import json
import math
import os
import subprocess
import urllib.parse
import urllib.request
import uuid
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import BackupLog, Loan, LoanApplication, LoanType, Notification, Payment, Penalty, RepaymentSchedule, User

CENT = Decimal('0.01')


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def add_months(start, months):
    index = start.month - 1 + months
    year = start.year + index // 12
    month = index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def build_schedule(principal, annual_rate, term_months, method, start):
    principal = money(principal)
    rate = Decimal(annual_rate)
    rows = []

    if method == LoanType.Method.FLAT:
        total_interest = money(principal * rate / 100 * Decimal(term_months) / 12)
        base_principal = money(principal / term_months)
        base_interest = money(total_interest / term_months)
        principal_left = principal
        interest_left = total_interest
        for number in range(1, term_months + 1):
            if number == term_months:
                p, i = principal_left, interest_left
            else:
                p, i = base_principal, base_interest
            principal_left -= p
            interest_left -= i
            rows.append({'installment_no': number, 'due_date': add_months(start, number), 'principal_due': p, 'interest_due': i})
    else:
        monthly = rate / 100 / 12
        if monthly == 0:
            installment = money(principal / term_months)
        else:
            installment = money(principal * monthly / (1 - (1 + monthly) ** -term_months))
        balance = principal
        for number in range(1, term_months + 1):
            i = money(balance * monthly)
            p = balance if number == term_months else money(installment - i)
            balance -= p
            rows.append({'installment_no': number, 'due_date': add_months(start, number), 'principal_due': p, 'interest_due': i})

    total_interest = sum((r['interest_due'] for r in rows), Decimal('0'))
    first = rows[0]
    return {
        'rows': rows,
        'total_interest': money(total_interest),
        'total_payable': money(principal + total_interest),
        'installment': money(first['principal_due'] + first['interest_due']),
    }


def estimate(amount, term_months, loan_type):
    plan = build_schedule(amount, loan_type.interest_rate, int(term_months), loan_type.interest_method, timezone.localdate())
    return {
        'total_interest': str(plan['total_interest']),
        'total_payable': str(plan['total_payable']),
        'installment': str(plan['installment']),
    }


def has_overdue(client):
    return RepaymentSchedule.objects.filter(
        loan__application__client=client,
        loan__status=Loan.Status.ACTIVE,
        status=RepaymentSchedule.Status.OVERDUE,
    ).exists()


def is_ready_to_approve(application):
    client = application.client
    if client.status != client.Status.ACTIVE or has_overdue(client):
        return False
    plan = build_schedule(application.amount_requested, application.loan_type.interest_rate, application.term_months, application.loan_type.interest_method, timezone.localdate())
    return client.monthly_income >= plan['installment'] * 3


def notify_admins(message, kind, client=None, loan=None):
    for admin in User.objects.filter(is_active=True, role__role_name='Admin'):
        Notification.objects.create(user=admin, client=client, loan=loan, type=kind, message=message)


@transaction.atomic
def approve_application(application, user):
    if application.status != LoanApplication.Status.PENDING:
        raise ValueError('Only pending applications can be approved.')
    loan_type = application.loan_type
    today = timezone.localdate()
    plan = build_schedule(application.amount_requested, loan_type.interest_rate, application.term_months, loan_type.interest_method, today)

    application.status = LoanApplication.Status.APPROVED
    application.processed_by = user
    application.decided_at = timezone.now()
    application.save(update_fields=['status', 'processed_by', 'decided_at'])

    loan = Loan.objects.create(
        application=application,
        principal=application.amount_requested,
        interest_rate=loan_type.interest_rate,
        term_months=application.term_months,
        release_date=today,
        maturity_date=plan['rows'][-1]['due_date'],
        total_payable=plan['total_payable'],
        installment_amount=plan['installment'],
        balance=plan['total_payable'],
        status=Loan.Status.ACTIVE,
    )
    RepaymentSchedule.objects.bulk_create([RepaymentSchedule(loan=loan, **row) for row in plan['rows']])
    Notification.objects.create(
        client=application.client,
        loan=loan,
        type=Notification.Kind.INFO,
        message=f'Loan of PHP {loan.principal:,.2f} was approved for {application.client}. Monthly installment is PHP {loan.installment_amount:,.2f}.',
    )
    return loan


@transaction.atomic
def reject_application(application, user, remarks):
    if application.status != LoanApplication.Status.PENDING:
        raise ValueError('Only pending applications can be rejected.')
    application.status = LoanApplication.Status.REJECTED
    application.processed_by = user
    application.remarks = remarks[:255]
    application.decided_at = timezone.now()
    application.save(update_fields=['status', 'processed_by', 'remarks', 'decided_at'])
    Notification.objects.create(
        client=application.client,
        type=Notification.Kind.INFO,
        message=f'Loan application #{application.pk} for {application.client} was not approved.',
    )


@transaction.atomic
def record_payment(loan, amount, method, user, payment_date=None):
    loan = Loan.objects.select_for_update().get(pk=loan.pk)
    amount = money(amount)
    if loan.status != Loan.Status.ACTIVE:
        raise ValueError('This loan is not active.')
    if amount <= 0:
        raise ValueError('Payment amount must be greater than zero.')
    if amount > loan.balance:
        raise ValueError(f'Payment is more than the remaining balance of PHP {loan.balance:,.2f}.')

    payment = Payment.objects.create(
        loan=loan,
        received_by=user,
        amount=amount,
        payment_date=payment_date or timezone.localdate(),
        method=method,
        receipt_no=uuid.uuid4().hex[:30],
    )

    remaining = amount
    first = None
    for item in loan.schedule.exclude(status=RepaymentSchedule.Status.PAID).order_by('installment_no'):
        if remaining <= 0:
            break
        applied = min(item.outstanding, remaining)
        item.amount_paid += applied
        item.status = RepaymentSchedule.Status.PAID if item.amount_paid >= item.amount_due else RepaymentSchedule.Status.PARTIAL
        item.save(update_fields=['amount_paid', 'status'])
        remaining -= applied
        if first is None:
            first = item

    payment.schedule = first
    payment.receipt_no = f'RCT-{payment.payment_date:%Y%m%d}-{payment.pk:06d}'
    payment.save(update_fields=['schedule', 'receipt_no'])

    loan.balance -= amount
    if loan.balance <= 0:
        loan.balance = Decimal('0.00')
        loan.status = Loan.Status.PAID
    loan.save(update_fields=['balance', 'status'])
    return payment


def apply_penalties(today=None):
    today = today or timezone.localdate()
    overdue = (
        RepaymentSchedule.objects
        .filter(loan__status=Loan.Status.ACTIVE, due_date__lt=today)
        .exclude(status=RepaymentSchedule.Status.PAID)
        .select_related('loan__application__loan_type', 'loan__application__client')
    )
    created = 0
    for item in overdue:
        loan_type = item.loan.application.loan_type
        days_late = (today - item.due_date).days
        if days_late <= loan_type.grace_period_days:
            continue
        months_late = math.ceil(days_late / 30)
        amount = money(item.outstanding * loan_type.penalty_rate / 100 * months_late)

        if item.status != RepaymentSchedule.Status.OVERDUE:
            item.status = RepaymentSchedule.Status.OVERDUE
            item.save(update_fields=['status'])

        penalty = item.penalties.first()
        if penalty is None:
            Penalty.objects.create(schedule=item, days_late=days_late, amount=amount, date_applied=today)
            client = item.loan.application.client
            notify_admins(
                f'{client} missed installment {item.installment_no} of Loan #{item.loan_id}. A penalty of PHP {amount:,.2f} was added.',
                Notification.Kind.OVERDUE, client=client, loan=item.loan,
            )
            created += 1
        elif penalty.status == Penalty.Status.UNPAID:
            penalty.days_late = days_late
            penalty.amount = amount
            penalty.save(update_fields=['days_late', 'amount'])
    return created


def send_due_reminders(today=None):
    today = today or timezone.localdate()
    tomorrow = today + timedelta(days=1)
    items = (
        RepaymentSchedule.objects
        .filter(loan__status=Loan.Status.ACTIVE, due_date=tomorrow)
        .exclude(status=RepaymentSchedule.Status.PAID)
        .select_related('loan__application__client')
    )
    created = 0
    for item in items:
        client = item.loan.application.client
        message = f'Reminder: PHP {item.outstanding:,.2f} is due on {item.due_date:%B %d, %Y} for Loan #{item.loan_id} ({client}).'
        _, was_created = Notification.objects.get_or_create(client=client, loan=item.loan, type=Notification.Kind.DUE, message=message)
        created += int(was_created)
    return created


def geocode_address(address):
    query = urllib.parse.urlencode({'q': address, 'format': 'json', 'limit': 1, 'countrycodes': 'ph'})
    request = urllib.request.Request(
        f'https://nominatim.openstreetmap.org/search?{query}',
        headers={'User-Agent': 'MicrofinanceBMS/1.0 (school project)'},
    )
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            data = json.loads(response.read().decode('utf-8'))
    except Exception:
        return None
    if not data:
        return None
    precision = Decimal('0.000001')
    return Decimal(data[0]['lat']).quantize(precision), Decimal(data[0]['lon']).quantize(precision)


def _db():
    return settings.DATABASES['default']


def _connection_args():
    db = _db()
    return ['-h', str(db['HOST']), '-P', str(db['PORT']), '-u', db['USER']]


def _env():
    env = os.environ.copy()
    env['MYSQL_PWD'] = str(_db()['PASSWORD'])
    return env


def run_backup(user, backup_type=BackupLog.Kind.MANUAL):
    if _db()['ENGINE'].endswith('sqlite3'):
        return BackupLog.objects.create(performed_by=user, file_name='unavailable', backup_type=BackupLog.Kind.MANUAL, status=BackupLog.Status.FAILED)
    settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    name = f'backup_{timezone.localtime():%Y%m%d_%H%M%S}.sql'
    path = settings.BACKUP_DIR / name
    status = BackupLog.Status.SUCCESS
    try:
        with open(path, 'wb') as handle:
            subprocess.run(
                [settings.MYSQLDUMP_PATH, *_connection_args(), '--single-transaction', '--routines', _db()['NAME']],
                stdout=handle, stderr=subprocess.PIPE, env=_env(), check=True,
            )
    except (OSError, subprocess.CalledProcessError):
        status = BackupLog.Status.FAILED
        if path.exists():
            path.unlink()
    log = BackupLog.objects.create(performed_by=user, file_name=name, backup_type=backup_type, status=status)
    if status == BackupLog.Status.FAILED:
        notify_admins('A database backup failed. Check that mysqldump is installed and the database login is correct.', Notification.Kind.SYSTEM)
    return log


def run_restore(user, log):
    if _db()['ENGINE'].endswith('sqlite3'):
        return BackupLog.objects.create(performed_by=user, file_name='unavailable', backup_type=BackupLog.Kind.MANUAL, status=BackupLog.Status.FAILED)
    path = settings.BACKUP_DIR / os.path.basename(log.file_name)
    status = BackupLog.Status.SUCCESS
    try:
        with open(path, 'rb') as handle:
            subprocess.run(
                [settings.MYSQL_CLIENT_PATH, *_connection_args(), _db()['NAME']],
                stdin=handle, stderr=subprocess.PIPE, env=_env(), check=True,
            )
    except (OSError, subprocess.CalledProcessError):
        status = BackupLog.Status.FAILED
    result = BackupLog.objects.create(performed_by=user, file_name=log.file_name, backup_type=BackupLog.Kind.RESTORE, status=status)
    if status == BackupLog.Status.FAILED:
        notify_admins(f'Restoring {log.file_name} failed.', Notification.Kind.SYSTEM)
    return result
