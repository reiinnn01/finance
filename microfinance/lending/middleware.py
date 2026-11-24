from django.shortcuts import redirect
from datetime import datetime, time
from django.conf import settings
from django.utils import timezone

ALLOWED = {
    'portal_home', 'portal_apply', 'loan_detail', 'payment_receipt',
    'notification_list', 'notification_action', 'logout', 'api_estimate',
}


class ClientAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = request.user
        if user.is_authenticated and not user.is_superuser and user.role_name == 'Client':
            match = request.resolver_match
            if match and match.url_name not in ALLOWED:
                return redirect('portal_home')
        return None

_last_run = {'day': None}


class DailyTasksMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        today = timezone.localdate()
        if _last_run['day'] != today:
            _last_run['day'] = today
            self.run_daily(today)
        return self.get_response(request)

    def run_daily(self, today):
        try:
            from . import services
            from .models import BackupLog
            services.apply_penalties(today)
            services.send_due_reminders(today)
            if settings.DATABASES['default']['ENGINE'].endswith('sqlite3'):
                return
            start = timezone.make_aware(datetime.combine(today, time.min))
            done = BackupLog.objects.filter(backup_type=BackupLog.Kind.SCHEDULED, created_at__gte=start).exists()
            if not done:
                services.run_backup(None, BackupLog.Kind.SCHEDULED)
        except Exception:
            pass

    def process_exception(self, request, exception):
        try:
            from . import services
            from .models import Notification
            message = f'System error on {request.path}: {type(exception).__name__}'
            if not Notification.objects.filter(type=Notification.Kind.SYSTEM, message=message, is_read=False).exists():
                services.notify_admins(message, Notification.Kind.SYSTEM)
        except Exception:
            pass
        return None