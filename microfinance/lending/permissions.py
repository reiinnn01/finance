from rest_framework.permissions import SAFE_METHODS, BasePermission


class RolePermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_admin_role:
            return True
        if user.role_name == 'Client':
            return False
        if request.method in SAFE_METHODS:
            roles = getattr(view, 'read_roles', None)
            return roles is None or user.role_name in roles
        return user.role_name in getattr(view, 'write_roles', ())
