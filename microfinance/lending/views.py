import os
import calendar
import time
from datetime import datetime, timedelta
from decimal import Decimal


from django.conf import settings
from django.http import FileResponse, Http404

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Q, Sum
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, TemplateView, UpdateView

from . import services
from .context import ADMIN, CASHIER, OFFICER

CLIENT = 'Client'
from .forms import (ClientForm, LoanApplicationForm, LoanTypeForm, PaymentForm, PortalApplicationForm,
                    SignupForm, UserForm)
from .models import (BackupLog, Client, Loan, LoanApplication, LoanType, Notification, Payment, Penalty,
                     RepaymentSchedule, User)


class RoleMixin(LoginRequiredMixin, UserPassesTestMixin):
    allowed_roles = None

    def test_func(self):
        user = self.request.user
        if user.is_admin_role or self.allowed_roles is None:
            return True
        return user.role_name in self.allowed_roles

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return render(self.request, 'forbidden.html', status=403)
        return super().handle_no_permission()


class SafeDeleteView(RoleMixin, DeleteView):
    template_name = 'confirm_delete.html'

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        try:
            self.object.delete()
        except ProtectedError:
            messages.error(request, 'This record is used by other records, so it cannot be deleted.')
        else:
            messages.success(request, 'Record deleted.')
        return redirect(self.success_url)


def visible_notifications(user):
    qs = Notification.objects.all()
    if user.is_admin_role:
        return qs
    if user.role_name == CLIENT:
        return qs.filter(Q(client__user=user) | Q(user=user))
    return qs.filter(user=user)


def is_client_user(user):
    return user.role_name == CLIENT and not user.is_superuser


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = 'home.html'

    def get(self, request, *args, **kwargs):
        if is_client_user(request.user):
            return redirect('portal_home')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        services.apply_penalties(today)
        services.send_due_reminders(today)

        active = Loan.objects.filter(status=Loan.Status.ACTIVE)
        pending = list(LoanApplication.objects.filter(status=LoanApplication.Status.PENDING).select_related('client', 'loan_type').order_by('applied_at')[:6])
        for application in pending:
            application.ready = services.is_ready_to_approve(application)

        ctx.update({
            'today': today,
            'loans_running': active.count(),
            'still_to_collect': active.aggregate(total=Sum('balance'))['total'] or Decimal('0'),
            'collected_today': Payment.objects.filter(payment_date=today).aggregate(total=Sum('amount'))['total'] or Decimal('0'),
            'late_clients': Client.objects.filter(applications__loan__status=Loan.Status.ACTIVE, applications__loan__schedule__status=RepaymentSchedule.Status.OVERDUE).distinct().count(),
            'pending': pending,
            'penalized_accounts': Loan.objects.filter(schedule__penalties__status=Penalty.Status.UNPAID).distinct().count(),
            'due_tomorrow': RepaymentSchedule.objects.filter(due_date=today + timedelta(days=1), loan__status=Loan.Status.ACTIVE).exclude(status=RepaymentSchedule.Status.PAID).count(),
            'last_backup': BackupLog.objects.exclude(backup_type=BackupLog.Kind.RESTORE).first(),
        })
        return ctx


class ClientList(LoginRequiredMixin, ListView):
    model = Client
    template_name = 'clients/list.html'
    paginate_by = 15

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q', '').strip()
        if q:
            match = Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(contact_no__icontains=q) | Q(valid_id_no__icontains=q)
            if q.isdigit():
                match |= Q(pk=int(q))
            qs = qs.filter(match)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        return ctx


class ClientDetail(LoginRequiredMixin, DetailView):
    model = Client
    template_name = 'clients/detail.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['applications'] = self.object.applications.select_related('loan_type')
        ctx['loans'] = Loan.objects.filter(application__client=self.object)
        return ctx


class ClientSaveMixin:
    model = Client
    form_class = ClientForm
    template_name = 'form.html'
    success_url = reverse_lazy('client_list')
    allowed_roles = (OFFICER,)

    def form_valid(self, form):
        client = form.save(commit=False)
        if not client.registered_by_id:
            client.registered_by = self.request.user
        if 'address' in form.changed_data or client.latitude is None:
            point = services.geocode_address(client.address)
            client.latitude, client.longitude = point if point else (None, None)
        client.save()
        messages.success(self.request, 'Client saved.')
        return redirect(self.success_url)


class ClientCreate(ClientSaveMixin, RoleMixin, CreateView):
    extra_context = {'page_title': 'Register a client', 'cancel_url': reverse_lazy('client_list')}


class ClientUpdate(ClientSaveMixin, RoleMixin, UpdateView):
    extra_context = {'page_title': 'Update client', 'cancel_url': reverse_lazy('client_list')}


class ClientDelete(SafeDeleteView):
    model = Client
    allowed_roles = (OFFICER,)
    success_url = reverse_lazy('client_list')


class ClientMap(LoginRequiredMixin, TemplateView):
    template_name = 'clients/map.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        clients = Client.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True)
        ctx['points'] = [
            {'name': c.full_name, 'address': c.address, 'status': c.status, 'lat': float(c.latitude), 'lng': float(c.longitude), 'url': reverse('client_detail', args=[c.pk])}
            for c in clients
        ]
        ctx['missing'] = Client.objects.filter(Q(latitude__isnull=True) | Q(longitude__isnull=True)).count()
        return ctx


class ClientGeocode(RoleMixin, View):
    allowed_roles = (OFFICER,)

    def post(self, request):
        found = 0
        for client in Client.objects.filter(Q(latitude__isnull=True) | Q(longitude__isnull=True))[:8]:
            point = services.geocode_address(client.address)
            if point:
                client.latitude, client.longitude = point
                client.save(update_fields=['latitude', 'longitude'])
                found += 1
            time.sleep(1)
        messages.success(request, f'Placed {found} client(s) on the map.')
        return redirect('client_map')


class ApplicationList(RoleMixin, ListView):
    model = LoanApplication
    template_name = 'applications/list.html'
    allowed_roles = (OFFICER,)
    paginate_by = 15

    def get_queryset(self):
        qs = super().get_queryset().select_related('client', 'loan_type')
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status'] = self.request.GET.get('status', '')
        ctx['statuses'] = LoanApplication.Status.choices
        return ctx


class ApplicationCreate(RoleMixin, CreateView):
    model = LoanApplication
    form_class = LoanApplicationForm
    template_name = 'form.html'
    allowed_roles = (OFFICER,)
    success_url = reverse_lazy('application_list')
    extra_context = {'page_title': 'Start a new loan', 'cancel_url': reverse_lazy('application_list'), 'with_estimate': True}

    def get_initial(self):
        return {'client': self.request.GET.get('client')}

    def form_valid(self, form):
        messages.success(self.request, 'Application saved and waiting for a decision.')
        return super().form_valid(form)


class ApplicationUpdate(RoleMixin, UpdateView):
    model = LoanApplication
    form_class = LoanApplicationForm
    template_name = 'form.html'
    allowed_roles = (OFFICER,)
    success_url = reverse_lazy('application_list')
    extra_context = {'page_title': 'Update application', 'cancel_url': reverse_lazy('application_list'), 'with_estimate': True}

    def get_queryset(self):
        return super().get_queryset().filter(status=LoanApplication.Status.PENDING)


class ApplicationDelete(SafeDeleteView):
    model = LoanApplication
    allowed_roles = (OFFICER,)
    success_url = reverse_lazy('application_list')

    def get_queryset(self):
        return super().get_queryset().filter(status=LoanApplication.Status.PENDING)


class ApplicationDetail(RoleMixin, DetailView):
    model = LoanApplication
    template_name = 'applications/detail.html'
    allowed_roles = (OFFICER,)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        app = self.object
        ctx['estimate'] = services.estimate(app.amount_requested, app.term_months, app.loan_type)
        ctx['ready'] = services.is_ready_to_approve(app)
        ctx['overdue'] = services.has_overdue(app.client)
        return ctx


class ApplicationDecide(RoleMixin, View):
    allowed_roles = (OFFICER,)

    def post(self, request, pk):
        application = get_object_or_404(LoanApplication, pk=pk)
        action = request.POST.get('action')
        try:
            if action == 'approve':
                loan = services.approve_application(application, request.user)
                messages.success(request, f'Approved. Loan #{loan.pk} was created with its payment schedule.')
                return redirect('loan_detail', pk=loan.pk)
            if action == 'reject':
                services.reject_application(application, request.user, request.POST.get('remarks', ''))
                messages.success(request, 'Application rejected.')
        except ValueError as error:
            messages.error(request, str(error))
        return redirect('application_detail', pk=pk)


class LoanList(RoleMixin, ListView):
    model = Loan
    template_name = 'loans/list.html'
    allowed_roles = (OFFICER,)
    paginate_by = 15

    def get_queryset(self):
        qs = super().get_queryset().select_related('application__client', 'application__loan_type')
        status = self.request.GET.get('status', '')
        q = self.request.GET.get('q', '').strip()
        if status:
            qs = qs.filter(status=status)
        if q:
            qs = qs.filter(Q(application__client__first_name__icontains=q) | Q(application__client__last_name__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status'] = self.request.GET.get('status', '')
        ctx['q'] = self.request.GET.get('q', '')
        ctx['statuses'] = Loan.Status.choices
        return ctx


class LoanDetail(LoginRequiredMixin, DetailView):
    model = Loan
    template_name = 'loans/detail.html'

    def get_queryset(self):
        qs = super().get_queryset()
        if is_client_user(self.request.user):
            qs = qs.filter(application__client__user=self.request.user)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['schedule'] = self.object.schedule.prefetch_related('penalties')
        ctx['payments'] = self.object.payments.select_related('received_by')
        ctx['total_paid'] = self.object.total_payable - self.object.balance
        return ctx


class PaymentList(RoleMixin, ListView):
    model = Payment
    template_name = 'payments/list.html'
    allowed_roles = (CASHIER,)
    paginate_by = 15

    def get_queryset(self):
        qs = super().get_queryset().select_related('loan__application__client', 'received_by')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(receipt_no__icontains=q) | Q(loan__application__client__first_name__icontains=q) | Q(loan__application__client__last_name__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        return ctx


class PaymentCreate(RoleMixin, FormView):
    form_class = PaymentForm
    template_name = 'form.html'
    allowed_roles = (CASHIER,)
    extra_context = {'page_title': 'Record a payment', 'cancel_url': reverse_lazy('payment_list')}

    def get_initial(self):
        return {'loan': self.request.GET.get('loan'), 'payment_date': timezone.localdate()}

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            payment = services.record_payment(data['loan'], data['amount'], data['method'], self.request.user, data['payment_date'])
        except ValueError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)
        messages.success(self.request, 'Payment recorded and the loan balance was updated.')
        return redirect('payment_receipt', pk=payment.pk)


class PaymentReceipt(RoleMixin, DetailView):
    model = Payment
    template_name = 'payments/receipt.html'
    allowed_roles = (CASHIER, OFFICER, CLIENT)

    def get_queryset(self):
        qs = super().get_queryset().select_related('loan__application__client', 'received_by', 'schedule')
        if is_client_user(self.request.user):
            qs = qs.filter(loan__application__client__user=self.request.user)
        return qs


class PenaltyList(RoleMixin, TemplateView):
    template_name = 'penalties/list.html'
    allowed_roles = (OFFICER,)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        services.apply_penalties()
        ctx['loan_types'] = LoanType.objects.all()
        ctx['penalties'] = Penalty.objects.select_related('schedule__loan__application__client')[:50]
        ctx['unpaid_total'] = Penalty.objects.filter(status=Penalty.Status.UNPAID).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        return ctx


class PenaltyAction(RoleMixin, View):
    allowed_roles = (OFFICER,)

    def post(self, request, pk):
        penalty = get_object_or_404(Penalty, pk=pk)
        action = request.POST.get('action')
        if action in (Penalty.Status.PAID, Penalty.Status.WAIVED):
            penalty.status = action
            penalty.save(update_fields=['status'])
            messages.success(request, f'Penalty marked as {action.lower()}.')
        return redirect('penalty_list')


class LoanTypeCreate(RoleMixin, CreateView):
    model = LoanType
    form_class = LoanTypeForm
    template_name = 'form.html'
    allowed_roles = ()
    success_url = reverse_lazy('penalty_list')
    extra_context = {'page_title': 'Add a loan type', 'cancel_url': reverse_lazy('penalty_list')}


class LoanTypeUpdate(RoleMixin, UpdateView):
    model = LoanType
    form_class = LoanTypeForm
    template_name = 'form.html'
    allowed_roles = ()
    success_url = reverse_lazy('penalty_list')
    extra_context = {'page_title': 'Update loan type', 'cancel_url': reverse_lazy('penalty_list')}


class LoanTypeDelete(SafeDeleteView):
    model = LoanType
    allowed_roles = ()
    success_url = reverse_lazy('penalty_list')


class ReportView(RoleMixin, TemplateView):
    template_name = 'reports.html'
    allowed_roles = (OFFICER,)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        period = self.request.GET.get('period', 'daily')
        try:
            ref = datetime.strptime(self.request.GET.get('date', ''), '%Y-%m-%d').date()
        except ValueError:
            ref = timezone.localdate()

        if period == 'weekly':
            start = ref - timedelta(days=ref.weekday())
            end = start + timedelta(days=6)
        elif period == 'monthly':
            start = ref.replace(day=1)
            end = ref.replace(day=calendar.monthrange(ref.year, ref.month)[1])
        else:
            period = 'daily'
            start = end = ref

        loans = Loan.objects.filter(release_date__range=(start, end)).select_related('application__client')
        payments = Payment.objects.filter(payment_date__range=(start, end)).select_related('loan__application__client')
        zero = Decimal('0')
        ctx.update({
            'period': period,
            'ref': ref,
            'start': start,
            'end': end,
            'loans': loans,
            'payments': payments,
            'total_disbursed': loans.aggregate(t=Sum('principal'))['t'] or zero,
            'total_collections': payments.aggregate(t=Sum('amount'))['t'] or zero,
            'outstanding': Loan.objects.filter(status=Loan.Status.ACTIVE).aggregate(t=Sum('balance'))['t'] or zero,
            'loan_count': loans.count(),
            'payment_count': payments.count(),
            'status_counts': Loan.objects.values('status').annotate(n=Count('pk')).order_by('status'),
        })
        return ctx


class NotificationList(LoginRequiredMixin, ListView):
    model = Notification
    template_name = 'notifications/list.html'
    paginate_by = 20

    def get_queryset(self):
        return visible_notifications(self.request.user).select_related('client', 'loan')


class NotificationAction(LoginRequiredMixin, View):
    def post(self, request):
        qs = visible_notifications(request.user)
        action = request.POST.get('action')
        if action == 'read_all':
            qs.update(is_read=True)
        elif action in ('read', 'delete'):
            item = get_object_or_404(qs, pk=request.POST.get('pk'))
            if action == 'read':
                item.is_read = True
                item.save(update_fields=['is_read'])
            else:
                item.delete()
        return redirect('notification_list')


class UserList(RoleMixin, ListView):
    model = User
    template_name = 'users/list.html'
    allowed_roles = ()

    def get_queryset(self):
        return super().get_queryset().select_related('role')


class UserCreate(RoleMixin, CreateView):
    model = User
    form_class = UserForm
    template_name = 'form.html'
    allowed_roles = ()
    success_url = reverse_lazy('user_list')
    extra_context = {'page_title': 'Add a user account', 'cancel_url': reverse_lazy('user_list')}


class UserUpdate(RoleMixin, UpdateView):
    model = User
    form_class = UserForm
    template_name = 'form.html'
    allowed_roles = ()
    success_url = reverse_lazy('user_list')
    extra_context = {'page_title': 'Update user account', 'cancel_url': reverse_lazy('user_list')}


class UserDelete(SafeDeleteView):
    model = User
    allowed_roles = ()
    success_url = reverse_lazy('user_list')

    def post(self, request, *args, **kwargs):
        if self.get_object().pk == request.user.pk:
            messages.error(request, 'You cannot delete the account you are signed in with.')
            return redirect(self.success_url)
        return super().post(request, *args, **kwargs)


class BackupDownload(RoleMixin, View):
    allowed_roles = ()

    def get(self, request, pk):
        log = get_object_or_404(BackupLog, pk=pk, status=BackupLog.Status.SUCCESS)
        path = settings.BACKUP_DIR / os.path.basename(log.file_name)
        if not path.exists():
            raise Http404('Backup file not found.')
        return FileResponse(open(path, 'rb'), as_attachment=True, filename=path.name)
    
class BackupView(RoleMixin, TemplateView):
    template_name = 'backup.html'
    allowed_roles = ()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['logs'] = BackupLog.objects.select_related('performed_by')[:50]
        return ctx

    def post(self, request):
        action = request.POST.get('action')
        if action == 'backup':
            log = services.run_backup(request.user)
            if log.status == BackupLog.Status.SUCCESS:
                messages.success(request, f'Backup saved as {log.file_name}.')
            else:
                messages.error(request, 'Backup failed. Check the mysqldump path and database login in settings.')
        elif action == 'restore':
            source = get_object_or_404(BackupLog, pk=request.POST.get('pk'), status=BackupLog.Status.SUCCESS)
            if source.backup_type == BackupLog.Kind.RESTORE:
                messages.error(request, 'Choose a backup entry to restore from.')
            else:
                result = services.run_restore(request.user, source)
                if result.status == BackupLog.Status.SUCCESS:
                    messages.success(request, f'Database restored from {source.file_name}.')
                else:
                    messages.error(request, 'Restore failed. Check that the backup file exists and the mysql path is correct.')
        elif action == 'upload':
            upload = request.FILES.get('file')
            if not upload or not upload.name.lower().endswith('.sql'):
                messages.error(request, 'Choose a .sql backup file.')
            else:
                settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
                name = f'uploaded_{timezone.localtime():%Y%m%d_%H%M%S}.sql'
                with open(settings.BACKUP_DIR / name, 'wb') as handle:
                    for chunk in upload.chunks():
                        handle.write(chunk)
                source = BackupLog.objects.create(performed_by=request.user, file_name=name, backup_type=BackupLog.Kind.MANUAL, status=BackupLog.Status.SUCCESS)
                result = services.run_restore(request.user, source)
                if result.status == BackupLog.Status.SUCCESS:
                    messages.success(request, 'Database restored from the uploaded file.')
                else:
                    messages.error(request, 'Restore failed. Make sure the file is a MySQL dump of this system.')
        return redirect('backup')

class SignupView(FormView):
    form_class = SignupForm
    template_name = 'registration/signup.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('home')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        client = form.save()
        point = services.geocode_address(client.address)
        if point:
            client.latitude, client.longitude = point
            client.save(update_fields=['latitude', 'longitude'])
        login(self.request, client.user)
        messages.success(self.request, 'Your account is ready. You can apply for a loan now.')
        return redirect('portal_home')


class ClientPortalMixin(RoleMixin):
    allowed_roles = (CLIENT,)

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not hasattr(request.user, 'client_profile'):
            return redirect('home')
        return super().dispatch(request, *args, **kwargs)


class PortalHome(ClientPortalMixin, TemplateView):
    template_name = 'portal/home.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        client = self.request.user.client_profile
        loans = Loan.objects.filter(application__client=client).select_related('application__loan_type')
        active = loans.filter(status=Loan.Status.ACTIVE)
        next_due = (RepaymentSchedule.objects.filter(loan__in=active)
                    .exclude(status=RepaymentSchedule.Status.PAID).order_by('due_date').first())
        for loan in loans:
            loan.next_due = loan.schedule.exclude(status=RepaymentSchedule.Status.PAID).order_by('due_date').first()
        applications = client.applications.select_related('loan_type')
        ctx.update({
            'client': client,
            'loans': loans,
            'applications': applications,
            'active_count': active.count(),
            'balance': active.aggregate(t=Sum('balance'))['t'] or Decimal('0'),
            'next_due': next_due,
            'pending_count': applications.filter(status=LoanApplication.Status.PENDING).count(),
            'today': timezone.localdate(),
        })
        return ctx


class PortalApply(ClientPortalMixin, CreateView):
    model = LoanApplication
    form_class = PortalApplicationForm
    template_name = 'form.html'
    success_url = reverse_lazy('portal_home')
    extra_context = {'page_title': 'Apply for a loan', 'cancel_url': reverse_lazy('portal_home'), 'with_estimate': True}

    def form_valid(self, form):
        client = self.request.user.client_profile
        if client.status != Client.Status.ACTIVE:
            form.add_error(None, 'Your account is not active right now. Please contact our office.')
            return self.form_invalid(form)
        if client.applications.filter(status=LoanApplication.Status.PENDING).exists():
            form.add_error(None, 'You already have an application waiting for a decision.')
            return self.form_invalid(form)
        application = form.save(commit=False)
        application.client = client
        application.save()
        Notification.objects.create(
            client=client, type=Notification.Kind.INFO,
            message=f'Application #{application.pk} was received and is waiting for a decision.',
        )
        notify_text = f'{client} applied for PHP {application.amount_requested:,.2f}.'
        services.notify_admins(notify_text, Notification.Kind.INFO, client=client)
        messages.success(self.request, 'Application sent. We will let you know once it is reviewed.')
        return redirect(self.success_url)
