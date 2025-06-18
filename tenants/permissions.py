# tenants/permissions.py
from rest_framework import permissions


class IsTenantMember(permissions.BasePermission):
    """
    Permission to check if user belongs to a tenant
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        return hasattr(request.user, 'tenant') and request.user.tenant is not None


class IsTenantAdmin(permissions.BasePermission):
    """
    Permission to check if user is admin or owner of the tenant
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if not hasattr(request.user, 'tenant') or request.user.tenant is None:
            return False
        
        return request.user.role in ['admin', 'owner']


class IsTenantOwner(permissions.BasePermission):
    """
    Permission to check if user is the owner of the tenant
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if not hasattr(request.user, 'tenant') or request.user.tenant is None:
            return False
        
        return request.user.role == 'owner'


class CanManageUsers(permissions.BasePermission):
    """
    Permission to check if user can manage other users
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if not hasattr(request.user, 'tenant') or request.user.tenant is None:
            return False
        
        # Check if user has user management permissions
        user_permissions = request.user.permissions or {}
        return (
            request.user.role in ['admin', 'owner'] or 
            user_permissions.get('manage_users', False)
        )


class CanViewAnalytics(permissions.BasePermission):
    """
    Permission to check if user can view analytics
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if not hasattr(request.user, 'tenant') or request.user.tenant is None:
            return False
        
        user_permissions = request.user.permissions or {}
        return (
            request.user.role in ['admin', 'owner'] or 
            user_permissions.get('view_analytics', False)
        )