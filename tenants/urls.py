# tenants/urls.py
from django.urls import path
from . import views

app_name = 'tenants'

urlpatterns = [
    # Tenant management
    path('tenants/', views.tenants, name='tenants'),
    
    # Authentication endpoints
    path('auth/register-business/', views.register_business, name='register_business'),
    path('auth/register-user/', views.register_user, name='register_user'),
    path('auth/login/', views.login, name='login'),
    path('auth/logout/', views.logout, name='logout'),
    path('auth/token/refresh/', views.token_refresh, name='token_refresh'),  # New JWT refresh endpoint
    path('auth/profile/', views.profile, name='profile'),
    path('auth/profile/update/', views.update_profile, name='update_profile'),
    path('auth/change-password/', views.change_password, name='change_password'),
    path('auth/verify/', views.verify_token, name='verify_token'),
    path('auth/users/', views.users, name='users'),
]