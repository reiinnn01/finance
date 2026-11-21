from django.db.models import Q

from .models import Notification

ADMIN = 'Admin'
OFFICER = 'Loan Officer'
CASHIER = 'Cashier'

NAV = [
    ('Home', 'home', ('home',), None),
    ('Clients', 'client_list', ('client',), None),
    ('Loan Applications', 'application_list', ('application', 'loan_list', 'loan_detail'), (ADMIN, OFFICER)),
    ('Payments', 'payment_list', ('payment',), (ADMIN, CASHIER)),
    ('Interest & Penalties', 'penalty_list', ('penalty', 'loantype'), (ADMIN, OFFICER)),
    ('Reports', 'report', ('report',), (ADMIN, OFFICER)),
    ('Notifications', 'notification_list', ('notification',), None),
    ('User Accounts', 'user_list', ('user',), (ADMIN,)),
    ('Backup & Recovery', 'backup', ('backup',), (ADMIN,)),
]


def navigation(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    role = user.role_name
    current = request.resolver_match.url_name if request.resolver_match else ''
    unread = Notification.objects.filter(is_read=False)
    if role == 'Client':
        unread = unread.filter(Q(client__user=user) | Q(user=user))
        pages = [('Home', 'portal_home', ('portal_home', 'loan_detail', 'payment_receipt')),
                 ('Apply for a loan', 'portal_apply', ('portal_apply',)),
                 ('Notifications', 'notification_list', ('notification',))]
        current = request.resolver_match.url_name if request.resolver_match else ''
        return {'nav_items': [{'label': l, 'url': u, 'active': bool(current) and current.startswith(p),
                               'badge': unread.count() if u == 'notification_list' else 0} for l, u, p in pages]}
    unread = unread if user.is_admin_role else unread.filter(user=user)
    items = []
    for label, url, prefixes, roles in NAV:
        if roles and not user.is_admin_role and role not in roles:
            continue
        items.append({
            'label': label,
            'url': url,
            'active': bool(current) and current.startswith(prefixes),
            'badge': unread.count() if url == 'notification_list' else 0,
        })
    return {'nav_items': items}
