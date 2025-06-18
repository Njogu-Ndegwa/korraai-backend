# tenants/urls.py
from django.urls import path
from .views import (
    # Authentication views
    TenantRegistrationView, LoginView, LogoutView, RefreshTokenView,
    ForgotPasswordView, ResetPasswordView, VerifyEmailView,
    
    # Tenant management views
    TenantProfileView, TenantSettingsView, TenantAccountDeleteView,
    
    # User management views
    TenantUserListCreateView, TenantUserDetailView, TenantUserRoleUpdateView,
    TenantUserResendInviteView, TenantUserActivationView
)

app_name = 'tenants'

urlpatterns = [
    # Authentication endpoints
    path('auth/register/', TenantRegistrationView.as_view(), name='register'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/refresh/', RefreshTokenView.as_view(), name='refresh'),
    path('auth/forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('auth/reset-password/', ResetPasswordView.as_view(), name='reset-password'),
    path('auth/verify-email/', VerifyEmailView.as_view(), name='verify-email'),
    
    # Tenant management endpoints
    path('tenant/profile/', TenantProfileView.as_view(), name='tenant-profile'),
    path('tenant/settings/', TenantSettingsView.as_view(), name='tenant-settings'),
    path('tenant/account/', TenantAccountDeleteView.as_view(), name='tenant-delete'),
    
    # User management endpoints
    path('users/', TenantUserListCreateView.as_view(), name='user-list-create'),
    path('users/<uuid:pk>/', TenantUserDetailView.as_view(), name='user-detail'),
    path('users/<uuid:user_id>/role/', TenantUserRoleUpdateView.as_view(), name='user-role-update'),
    path('users/<uuid:user_id>/resend-invite/', TenantUserResendInviteView.as_view(), name='user-resend-invite'),
    path('users/<uuid:user_id>/activate/', TenantUserActivationView.as_view(), name='user-activation'),
]