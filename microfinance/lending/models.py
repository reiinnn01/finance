import os
import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone



class Role(models.Model):
    role_id = models.AutoField(primary_key=True)
    role_name = models.CharField(max_length=30, unique=True)

    class Meta:
        db_table = 'role'
        ordering = ['role_name']

    def __str__(self):
        return self.role_name


class UserManager(BaseUserManager):
    def create_user(self, username, password=None, **extra):
        if not username:
            raise ValueError('Username is required')
        user = self.model(username=username, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra):
        role, _ = Role.objects.get_or_create(role_name='Admin')
        extra.setdefault('role', role)
        extra['is_superuser'] = True
        return self.create_user(username, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    user_id = models.AutoField(primary_key=True)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, null=True, blank=True, db_column='role_id', related_name='users')
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=255, db_column='password_hash')
    full_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['full_name', 'email']

    class Meta:
        db_table = 'users'
        ordering = ['username']

    def __str__(self):
        return self.full_name or self.username

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.username

    @property
    def role_name(self):
        return self.role.role_name if self.role_id else ''

    @property
    def is_admin_role(self):
        return self.is_active and (self.is_superuser or self.role_name == 'Admin')

    @property
    def is_staff(self):
        return self.is_admin_role

    def has_perm(self, perm, obj=None):
        return self.is_admin_role

    def has_module_perms(self, app_label):
        return self.is_admin_role

    @property
    def initials(self):
        parts = (self.full_name or self.username).split()
        return ''.join(p[0] for p in parts[:2]).upper()

def id_upload(instance, filename):
    return f'ids/{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()}'

class Client(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'Active', 'Active'
        INACTIVE = 'Inactive', 'Inactive'
        BLACKLISTED = 'Blacklisted', 'Blacklisted'

    class Sex(models.TextChoices):
        MALE = 'Male', 'Male'
        FEMALE = 'Female', 'Female'

    class CivilStatus(models.TextChoices):
        SINGLE = 'Single', 'Single'
        MARRIED = 'Married', 'Married'
        WIDOWED = 'Widowed', 'Widowed'
        SEPARATED = 'Separated', 'Separated'

    client_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, db_column='user_id', related_name='client_profile')
    registered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, db_column='registered_by', related_name='registered_clients')
    first_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50, blank=True, default='')
    last_name = models.CharField(max_length=50)
    sex = models.CharField(max_length=10, choices=Sex.choices, blank=True, default='')
    civil_status = models.CharField(max_length=20, choices=CivilStatus.choices, blank=True, default='')
    birth_date = models.DateField()
    contact_no = models.CharField(max_length=20)
    email = models.EmailField(max_length=100, blank=True, default='')
    address = models.CharField(max_length=255)
    employer_name = models.CharField(max_length=100, blank=True, default='')
    occupation = models.CharField(max_length=100)
    monthly_income = models.DecimalField(max_digits=12, decimal_places=2)
    emergency_contact_name = models.CharField(max_length=100, blank=True, default='')
    emergency_contact_no = models.CharField(max_length=20, blank=True, default='')
    valid_id_type = models.CharField(max_length=50)
    valid_id_no = models.CharField(max_length=50)
    id_front = models.ImageField(upload_to=id_upload, blank=True)
    id_back = models.ImageField(upload_to=id_upload, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'client'
        ordering = ['last_name', 'first_name']
        constraints = [
            models.UniqueConstraint(fields=['valid_id_type', 'valid_id_no'], name='uq_client_valid_id'),
        ]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'

    @property
    def initials(self):
        return f'{self.first_name[:1]}{self.last_name[:1]}'.upper()


class LoanType(models.Model):
    class Method(models.TextChoices):
        FLAT = 'Flat', 'Flat rate'
        DIMINISHING = 'Diminishing', 'Diminishing balance'

    loan_type_id = models.AutoField(primary_key=True)
    type_name = models.CharField(max_length=50, unique=True)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, help_text='Percent per year')
    interest_method = models.CharField(max_length=20, choices=Method.choices, default=Method.FLAT)
    penalty_rate = models.DecimalField(max_digits=5, decimal_places=2, help_text='Percent of the unpaid installment for each month late')
    grace_period_days = models.IntegerField(default=3)
    max_amount = models.DecimalField(max_digits=12, decimal_places=2)
    max_term_months = models.IntegerField()

    class Meta:
        db_table = 'loan_type'
        ordering = ['type_name']

    def __str__(self):
        return self.type_name


class LoanApplication(models.Model):
    class Status(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        APPROVED = 'Approved', 'Approved'
        REJECTED = 'Rejected', 'Rejected'

    application_id = models.AutoField(primary_key=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, db_column='client_id', related_name='applications')
    loan_type = models.ForeignKey(LoanType, on_delete=models.PROTECT, db_column='loan_type_id', related_name='applications')
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, db_column='processed_by', related_name='processed_applications')
    amount_requested = models.DecimalField(max_digits=12, decimal_places=2)
    term_months = models.IntegerField()
    purpose = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    remarks = models.CharField(max_length=255, blank=True)
    applied_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'loan_application'
        ordering = ['-applied_at']

    def __str__(self):
        return f'Application #{self.application_id} - {self.client}'


class Loan(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'Active', 'Active'
        PAID = 'Paid', 'Paid'
        DEFAULTED = 'Defaulted', 'Defaulted'

    loan_id = models.AutoField(primary_key=True)
    application = models.OneToOneField(LoanApplication, on_delete=models.PROTECT, db_column='application_id', related_name='loan')
    principal = models.DecimalField(max_digits=12, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    term_months = models.IntegerField()
    release_date = models.DateField()
    maturity_date = models.DateField()
    total_payable = models.DecimalField(max_digits=12, decimal_places=2)
    installment_amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        db_table = 'loan'
        ordering = ['-release_date', '-loan_id']

    def __str__(self):
        return f'Loan #{self.loan_id}'

    @property
    def client(self):
        return self.application.client


class RepaymentSchedule(models.Model):
    class Status(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        PARTIAL = 'Partial', 'Partial'
        PAID = 'Paid', 'Paid'
        OVERDUE = 'Overdue', 'Overdue'

    schedule_id = models.AutoField(primary_key=True)
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, db_column='loan_id', related_name='schedule')
    installment_no = models.IntegerField()
    due_date = models.DateField()
    principal_due = models.DecimalField(max_digits=12, decimal_places=2)
    interest_due = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    class Meta:
        db_table = 'repayment_schedule'
        ordering = ['loan_id', 'installment_no']
        constraints = [
            models.UniqueConstraint(fields=['loan', 'installment_no'], name='uq_schedule_installment'),
        ]

    def __str__(self):
        return f'Loan #{self.loan_id} installment {self.installment_no}'

    @property
    def amount_due(self):
        return self.principal_due + self.interest_due

    @property
    def outstanding(self):
        return self.amount_due - self.amount_paid


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = 'Cash', 'Cash'
        GCASH = 'GCash', 'GCash'
        BANK = 'Bank Transfer', 'Bank transfer'
        CHECK = 'Check', 'Check'

    payment_id = models.AutoField(primary_key=True)
    loan = models.ForeignKey(Loan, on_delete=models.PROTECT, db_column='loan_id', related_name='payments')
    schedule = models.ForeignKey(RepaymentSchedule, on_delete=models.SET_NULL, null=True, blank=True, db_column='schedule_id', related_name='payments')
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, db_column='received_by', related_name='received_payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField()
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    receipt_no = models.CharField(max_length=30, unique=True)

    class Meta:
        db_table = 'payment'
        ordering = ['-payment_date', '-payment_id']

    def __str__(self):
        return self.receipt_no


class Penalty(models.Model):
    class Status(models.TextChoices):
        UNPAID = 'Unpaid', 'Unpaid'
        PAID = 'Paid', 'Paid'
        WAIVED = 'Waived', 'Waived'

    penalty_id = models.AutoField(primary_key=True)
    schedule = models.ForeignKey(RepaymentSchedule, on_delete=models.CASCADE, db_column='schedule_id', related_name='penalties')
    days_late = models.IntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date_applied = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNPAID)

    class Meta:
        db_table = 'penalty'
        ordering = ['-date_applied', '-penalty_id']

    def __str__(self):
        return f'Penalty #{self.penalty_id}'


class Notification(models.Model):
    class Kind(models.TextChoices):
        DUE = 'Due Reminder', 'Due reminder'
        OVERDUE = 'Overdue', 'Overdue'
        SYSTEM = 'System', 'System'
        INFO = 'Info', 'Info'

    notification_id = models.AutoField(primary_key=True)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, null=True, blank=True, db_column='client_id', related_name='notifications')
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, db_column='user_id', related_name='notifications')
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, null=True, blank=True, db_column='loan_id', related_name='notifications')
    type = models.CharField(max_length=20, choices=Kind.choices, default=Kind.INFO)
    message = models.CharField(max_length=500)
    sent_at = models.DateTimeField(default=timezone.now)
    is_read = models.BooleanField(default=False)

    class Meta:
        db_table = 'notification'
        ordering = ['-sent_at', '-notification_id']

    def __str__(self):
        return self.message[:60]


class BackupLog(models.Model):
    class Kind(models.TextChoices):
        MANUAL = 'Manual', 'Manual'
        SCHEDULED = 'Scheduled', 'Scheduled'
        RESTORE = 'Restore', 'Restore'

    class Status(models.TextChoices):
        SUCCESS = 'Success', 'Success'
        FAILED = 'Failed', 'Failed'

    backup_id = models.AutoField(primary_key=True)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, db_column='performed_by', related_name='backups')
    file_name = models.CharField(max_length=255)
    backup_type = models.CharField(max_length=20, choices=Kind.choices, default=Kind.MANUAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUCCESS)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'backup_log'
        ordering = ['-created_at', '-backup_id']

    def __str__(self):
        return self.file_name
