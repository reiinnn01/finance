from django.core.management.base import BaseCommand

from lending.models import LoanType, Role


class Command(BaseCommand):
    help = 'Create default roles and loan types'

    def handle(self, *args, **options):
        for name in ('Admin', 'Loan Officer', 'Cashier', 'Client'):
            Role.objects.get_or_create(role_name=name)
        defaults = [
            ('Salary Loan', 18, 'Flat', 5, 3, 50000, 12),
            ('Micro Business Loan', 24, 'Diminishing', 5, 5, 100000, 24),
            ('Emergency Loan', 12, 'Flat', 3, 2, 15000, 6),
        ]
        for name, rate, method, penalty, grace, max_amount, max_term in defaults:
            LoanType.objects.get_or_create(type_name=name, defaults={
                'interest_rate': rate, 'interest_method': method, 'penalty_rate': penalty,
                'grace_period_days': grace, 'max_amount': max_amount, 'max_term_months': max_term,
            })
        self.stdout.write(self.style.SUCCESS('Roles and loan types are ready.'))
