from django.core.management.base import BaseCommand

from lending import services


class Command(BaseCommand):
    help = 'Compute late penalties and create due-date reminders'

    def handle(self, *args, **options):
        penalties = services.apply_penalties()
        reminders = services.send_due_reminders()
        self.stdout.write(self.style.SUCCESS(f'{penalties} new penalties, {reminders} new reminders.'))
