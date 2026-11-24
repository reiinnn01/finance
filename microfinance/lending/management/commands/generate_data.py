import random
from datetime import datetime, time, timedelta
from decimal import Decimal
from io import BytesIO
from django.core.files.base import ContentFile
from PIL import Image, ImageDraw
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from faker import Faker

from lending import services
from lending.models import (Client, Loan, LoanApplication, LoanType, Notification, Payment, Penalty,
                            RepaymentSchedule, Role, User)

PASSWORD = 'Password123!'
TOWNS = ['Calamba', 'Los Baños', 'Cabuyao', 'Santa Rosa', 'Biñan', 'San Pablo']
JOBS = ['Sari-sari store owner', 'Tricycle driver', 'Market vendor', 'Seamstress', 'Farmer', 'Carinderia owner',
        'Barber', 'Online seller', 'Factory worker', 'Teacher', 'Delivery rider', 'Welder']
IDS = ["Driver's License", 'UMID', 'National ID', 'Postal ID', 'Voter ID', 'PhilHealth ID']
PURPOSES = ['Business capital', 'School tuition', 'Home repair', 'Medical expenses', 'Buy inventory',
            'Buy equipment', 'Emergency expenses']
REMARKS = ['Income is too low for the requested amount', 'Incomplete requirements', 'Existing unpaid obligations']


def at(day, hour=9):
    return timezone.make_aware(datetime.combine(day, time(hour, 0)))

def id_image(label, text):
    image = Image.new('RGB', (640, 400), (236, 240, 232))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 620, 380), outline=(31, 102, 80), width=4)
    draw.text((40, 40), f'SAMPLE ID - {label}', fill=(31, 74, 64))
    draw.text((40, 90), text, fill=(42, 36, 32))
    buffer = BytesIO()
    image.save(buffer, 'PNG')
    return ContentFile(buffer.getvalue())

class Command(BaseCommand):
    help = 'Generate fake clients, loans, payments and penalties'

    def add_arguments(self, parser):
        parser.add_argument('--clients', type=int, default=30)
        parser.add_argument('--seed', type=int, default=None)
        parser.add_argument('--clear', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        if options['seed'] is not None:
            random.seed(options['seed'])
            Faker.seed(options['seed'])
        self.fake = Faker('en_PH')
        call_command('seed', verbosity=0)
        if options['clear']:
            self.clear()

        officer = self.account('officer1', 'Loan Officer', 'Maria Officer')
        cashier = self.account('cashier1', 'Cashier', 'Carlo Cashier')
        clients = [self.client(officer) for _ in range(options['clients'])]
        active = [c for c in clients if c.status == Client.Status.ACTIVE]
        self.portal_accounts(active[:3])

        types = list(LoanType.objects.all())
        today = timezone.localdate()
        released = 0
        for client in active:
            for _ in range(random.choice([0, 1, 1, 2])):
                released += self.application(client, random.choice(types), officer, cashier, today)

        new_penalties = services.apply_penalties(today)
        services.send_due_reminders(today)
        for penalty in Penalty.objects.filter(status=Penalty.Status.UNPAID):
            roll = random.random()
            if roll < 0.25:
                penalty.status = Penalty.Status.PAID
                penalty.save(update_fields=['status'])
            elif roll < 0.35:
                penalty.status = Penalty.Status.WAIVED
                penalty.save(update_fields=['status'])

        self.stdout.write(self.style.SUCCESS(
            f'Created {len(clients)} clients, {released} released loans, {new_penalties} penalties.'))
        self.stdout.write(f'Logins (password {PASSWORD}): officer1, cashier1, client1, client2, client3')

    def clear(self):
        Payment.objects.all().delete()
        Penalty.objects.all().delete()
        RepaymentSchedule.objects.all().delete()
        Notification.objects.all().delete()
        Loan.objects.all().delete()
        LoanApplication.objects.all().delete()
        Client.objects.all().delete()
        User.objects.filter(role__role_name='Client').delete()

    def account(self, username, role_name, full_name):
        user = User.objects.filter(username=username).first()
        if user:
            return user
        return User.objects.create_user(
            username=username, password=PASSWORD, full_name=full_name,
            email=f'{username}@example.com', role=Role.objects.get(role_name=role_name),
        )

    def client(self, officer):
        fake = self.fake
        id_no = fake.bothify('??-########').upper()
        while Client.objects.filter(valid_id_no=id_no).exists():
            id_no = fake.bothify('??-########').upper()
        sex = random.choice(['Male', 'Female'])
        first = fake.first_name_male() if sex == 'Male' else fake.first_name_female()
        last = fake.last_name()
        town = random.choice(TOWNS)
        client = Client.objects.create(
            registered_by=officer,
            first_name=first,
            middle_name=fake.last_name() if random.random() < 0.7 else '',
            last_name=last,
            sex=sex,
            civil_status=random.choice(Client.CivilStatus.values),
            birth_date=fake.date_of_birth(minimum_age=21, maximum_age=60),
            contact_no=f'09{random.randint(100000000, 999999999)}',
            email=f'{first}.{last}{random.randint(1, 99)}@example.com'.lower().replace(' ', ''),
            address=f'{fake.street_name()}, Brgy. {fake.last_name()}, {town}, Laguna',
            employer_name=fake.company(),
            occupation=random.choice(JOBS),
            monthly_income=random.randrange(8000, 60001, 500),
            emergency_contact_name=fake.name(),
            emergency_contact_no=f'09{random.randint(100000000, 999999999)}',
            valid_id_type=random.choice(IDS),
            valid_id_no=id_no,
            status=random.choices([Client.Status.ACTIVE, Client.Status.INACTIVE], weights=[95, 5])[0],
            latitude=Decimal(f'{random.uniform(14.10, 14.30):.6f}'),
            longitude=Decimal(f'{random.uniform(121.05, 121.25):.6f}'),
        )
        client.id_front.save(f'front_{client.pk}.png', id_image('FRONT', client.full_name), save=False)
        client.id_back.save(f'back_{client.pk}.png', id_image('BACK', client.valid_id_no), save=False)
        client.save(update_fields=['id_front', 'id_back'])
        Client.objects.filter(pk=client.pk).update(created_at=timezone.now() - timedelta(days=random.randint(430, 520)))
        return client

    def portal_accounts(self, clients):
        role = Role.objects.get(role_name='Client')
        for number, client in enumerate(clients, 1):
            username = f'client{number}'
            if User.objects.filter(username=username).exists():
                continue
            user = User.objects.create_user(
                username=username, password=PASSWORD, full_name=client.full_name,
                email=f'{username}@example.com', role=role,
            )
            client.user = user
            client.save(update_fields=['user'])

    def application(self, client, loan_type, officer, cashier, today):
        max_k = int(loan_type.max_amount / 1000)
        amount = random.randint(min(5, max_k), max_k) * 1000
        term = random.choice([t for t in (3, 6, 9, 12, 18, 24) if t <= loan_type.max_term_months])
        roll = random.random()

        application = LoanApplication.objects.create(
            client=client, loan_type=loan_type, amount_requested=amount,
            term_months=term, purpose=random.choice(PURPOSES),
        )

        if roll < 0.15:
            applied = today - timedelta(days=random.randint(0, 5))
            LoanApplication.objects.filter(pk=application.pk).update(applied_at=at(applied))
            return 0

        if roll < 0.25:
            applied = today - timedelta(days=random.randint(5, 60))
            application.status = LoanApplication.Status.REJECTED
            application.processed_by = officer
            application.remarks = random.choice(REMARKS)
            application.decided_at = at(applied + timedelta(days=1))
            application.save()
            LoanApplication.objects.filter(pk=application.pk).update(applied_at=at(applied))
            return 0

        start = today - timedelta(days=random.randint(20, 420))
        applied = start - timedelta(days=random.randint(1, 4))
        plan = services.build_schedule(amount, loan_type.interest_rate, term, loan_type.interest_method, start)
        application.status = LoanApplication.Status.APPROVED
        application.processed_by = officer
        application.decided_at = at(start)
        application.save()
        LoanApplication.objects.filter(pk=application.pk).update(applied_at=at(applied))

        loan = Loan.objects.create(
            application=application, principal=amount, interest_rate=loan_type.interest_rate,
            term_months=term, release_date=start, maturity_date=plan['rows'][-1]['due_date'],
            total_payable=plan['total_payable'], installment_amount=plan['installment'],
            balance=plan['total_payable'], status=Loan.Status.ACTIVE,
        )
        RepaymentSchedule.objects.bulk_create([RepaymentSchedule(loan=loan, **row) for row in plan['rows']])
        self.pay(loan, plan['rows'], cashier, today)
        return 1

    def pay(self, loan, rows, cashier, today):
        due = [r for r in rows if r['due_date'] <= today]
        profile = random.choices(['good', 'late', 'partial'], weights=[60, 25, 15])[0]
        if profile == 'late':
            due = due[:max(len(due) - random.randint(1, 2), 0)]
        elif profile == 'partial':
            due = due[:len(due) // 2]
        for row in due:
            paid_on = min(row['due_date'] + timedelta(days=random.choice([0, 0, 0, 1, 2])), today)
            try:
                services.record_payment(
                    loan, row['principal_due'] + row['interest_due'],
                    random.choice(Payment.Method.values), cashier, paid_on,
                )
            except ValueError:
                break