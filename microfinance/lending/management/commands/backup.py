from django.core.management.base import BaseCommand

from lending import services
from lending.models import BackupLog


class Command(BaseCommand):
    help = 'Create a scheduled database backup'

    def handle(self, *args, **options):
        log = services.run_backup(None, BackupLog.Kind.SCHEDULED)
        self.stdout.write(f'{log.status}: {log.file_name}')