from datetime import date

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from .models import Client, Loan, LoanApplication, LoanType, Payment, Role, User


def date_input():
    return forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'field')


class ClientForm(StyledModelForm):
    class Meta:
        model = Client
        fields = ['first_name', 'middle_name', 'last_name', 'sex', 'civil_status', 'birth_date', 'contact_no',
                  'email', 'address', 'employer_name', 'occupation', 'monthly_income',
                  'emergency_contact_name', 'emergency_contact_no', 'valid_id_type', 'valid_id_no', 'status']
        widgets = {'birth_date': date_input()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('sex', 'civil_status', 'email', 'employer_name', 'emergency_contact_name', 'emergency_contact_no'):
            self.fields[name].required = True
        self.fields['middle_name'].required = False
        self.fields['employer_name'].label = 'Employer or business name'
        self.fields['emergency_contact_name'].label = 'Emergency contact name'
        self.fields['emergency_contact_no'].label = 'Emergency contact number'

    def clean(self):
        data = super().clean()
        id_type, id_no = data.get('valid_id_type'), data.get('valid_id_no')
        if id_type and id_no:
            clash = Client.objects.filter(valid_id_type__iexact=id_type, valid_id_no__iexact=id_no)
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                self.add_error('valid_id_no', 'A client with this ID is already registered.')
        return data

class LoanApplicationForm(StyledModelForm):
    class Meta:
        model = LoanApplication
        fields = ['client', 'loan_type', 'amount_requested', 'term_months', 'purpose']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'client' in self.fields:
            self.fields['client'].queryset = Client.objects.filter(status=Client.Status.ACTIVE)

    def clean(self):
        data = super().clean()
        loan_type = data.get('loan_type')
        amount = data.get('amount_requested')
        term = data.get('term_months')
        if loan_type and amount is not None and amount <= 0:
            self.add_error('amount_requested', 'Amount must be greater than zero.')
        if loan_type and amount and amount > loan_type.max_amount:
            self.add_error('amount_requested', f'{loan_type} allows up to PHP {loan_type.max_amount:,.2f}.')
        if loan_type and term is not None and term < 1:
            self.add_error('term_months', 'Term must be at least 1 month.')
        if loan_type and term and term > loan_type.max_term_months:
            self.add_error('term_months', f'{loan_type} allows up to {loan_type.max_term_months} months.')
        return data


class PaymentForm(forms.Form):
    loan = forms.ModelChoiceField(queryset=Loan.objects.none())
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    method = forms.ChoiceField(choices=Payment.Method.choices)
    payment_date = forms.DateField(widget=date_input())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['loan'].queryset = Loan.objects.filter(status=Loan.Status.ACTIVE).select_related('application__client')
        self.fields['loan'].label_from_instance = lambda l: f'Loan #{l.loan_id} - {l.client} (balance PHP {l.balance:,.2f})'
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'field')

    def clean(self):
        data = super().clean()
        loan, amount = data.get('loan'), data.get('amount')
        if loan and amount and amount > loan.balance:
            self.add_error('amount', f'Payment is more than the remaining balance of PHP {loan.balance:,.2f}.')
        return data


class LoanTypeForm(StyledModelForm):
    class Meta:
        model = LoanType
        fields = ['type_name', 'interest_rate', 'interest_method', 'penalty_rate', 'grace_period_days', 'max_amount', 'max_term_months']


class UserForm(StyledModelForm):
    password = forms.CharField(widget=forms.PasswordInput(render_value=False), required=False, help_text='Leave blank to keep the current password.')

    class Meta:
        model = User
        fields = ['username', 'full_name', 'email', 'role', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password'].widget.attrs['class'] = 'field'
        self.fields['role'].required = True
        self.fields['role'].queryset = Role.objects.exclude(role_name='Client')
        if not self.instance.pk:
            self.fields['password'].required = True
            self.fields['password'].help_text = ''

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get('password'):
            user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class PortalApplicationForm(LoanApplicationForm):
    class Meta(LoanApplicationForm.Meta):
        fields = ['loan_type', 'amount_requested', 'term_months', 'purpose']


class SignupForm(ClientForm):
    username = forms.CharField(max_length=50)
    email = forms.EmailField(max_length=100)
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirm password', widget=forms.PasswordInput)

    class Meta(ClientForm.Meta):
        fields = ['first_name', 'middle_name', 'last_name', 'sex', 'civil_status', 'birth_date', 'contact_no',
                  'email', 'address', 'employer_name', 'occupation', 'monthly_income',
                  'emergency_contact_name', 'emergency_contact_no', 'valid_id_type', 'valid_id_no']

    field_order = ['username', 'password1', 'password2', 'first_name', 'middle_name', 'last_name', 'sex',
                   'civil_status', 'birth_date', 'contact_no', 'email', 'address', 'employer_name',
                   'occupation', 'monthly_income', 'emergency_contact_name', 'emergency_contact_no',
                   'valid_id_type', 'valid_id_no']

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('That username is taken. Try another one.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean(self):
        data = super().clean()
        p1, p2 = data.get('password1'), data.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Passwords do not match.')
        elif p1:
            try:
                validate_password(p1)
            except forms.ValidationError as error:
                self.add_error('password1', error)
        return data

    @transaction.atomic
    def save(self, commit=True):
        role, _ = Role.objects.get_or_create(role_name='Client')
        first, last = self.cleaned_data['first_name'], self.cleaned_data['last_name']
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            password=self.cleaned_data['password1'],
            full_name=f'{first} {last}',
            email=self.cleaned_data['email'],
            role=role,
        )
        client = super().save(commit=False)
        client.user = user
        client.status = Client.Status.ACTIVE
        client.save()
        return client
