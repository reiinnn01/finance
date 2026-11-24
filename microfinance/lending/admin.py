from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import (BackupLog, Client, Loan, LoanApplication, LoanType, Notification, Payment, Penalty,
                     RepaymentSchedule, Role, User)


class StaffUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'full_name', 'email', 'role')


class StaffUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = '__all__'


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = StaffUserChangeForm
    add_form = StaffUserCreationForm
    list_display = ('username', 'full_name', 'email', 'role', 'is_active')
    list_filter = ('role', 'is_active')
    search_fields = ('username', 'full_name', 'email')
    ordering = ('username',)
    filter_horizontal = ()
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Profile', {'fields': ('full_name', 'email', 'role')}),
        ('Access', {'fields': ('is_active', 'is_superuser')}),
        ('Dates', {'fields': ('last_login', 'created_at')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('username', 'full_name', 'email', 'role', 'password1', 'password2')}),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('role_id', 'role_name')


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('client_id', 'last_name', 'first_name', 'contact_no', 'occupation', 'monthly_income', 'status')
    list_filter = ('status',)
    search_fields = ('first_name', 'last_name', 'contact_no', 'valid_id_no')
    exclude = ('id_front', 'id_back')


@admin.register(LoanType)
class LoanTypeAdmin(admin.ModelAdmin):
    list_display = ('type_name', 'interest_rate', 'interest_method', 'penalty_rate', 'grace_period_days', 'max_amount', 'max_term_months')


@admin.register(LoanApplication)
class LoanApplicationAdmin(admin.ModelAdmin):
    list_display = ('application_id', 'client', 'loan_type', 'amount_requested', 'term_months', 'status', 'applied_at')
    list_filter = ('status', 'loan_type')
    search_fields = ('client__first_name', 'client__last_name')


class ScheduleInline(admin.TabularInline):
    model = RepaymentSchedule
    extra = 0


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ('loan_id', 'application', 'principal', 'total_payable', 'balance', 'release_date', 'maturity_date', 'status')
    list_filter = ('status',)
    inlines = [ScheduleInline]


@admin.register(RepaymentSchedule)
class RepaymentScheduleAdmin(admin.ModelAdmin):
    list_display = ('schedule_id', 'loan', 'installment_no', 'due_date', 'principal_due', 'interest_due', 'amount_paid', 'status')
    list_filter = ('status',)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('receipt_no', 'loan', 'amount', 'payment_date', 'method', 'received_by')
    list_filter = ('method',)
    search_fields = ('receipt_no',)


@admin.register(Penalty)
class PenaltyAdmin(admin.ModelAdmin):
    list_display = ('penalty_id', 'schedule', 'days_late', 'amount', 'date_applied', 'status')
    list_filter = ('status',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('notification_id', 'type', 'message', 'user', 'client', 'sent_at', 'is_read')
    list_filter = ('type', 'is_read')


@admin.register(BackupLog)
class BackupLogAdmin(admin.ModelAdmin):
    list_display = ('backup_id', 'file_name', 'backup_type', 'status', 'performed_by', 'created_at')
    list_filter = ('backup_type', 'status')
