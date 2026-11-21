from django.shortcuts import redirect

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
