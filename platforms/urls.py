from django.urls import path
from . import views

app_name = 'platforms'

urlpatterns = [
    # List and create platforms
    path('platforms/', views.platforms, name='plat,m forms'),
    
    # Platform detail operations
    path('platforms/<uuid:platform_id>/', views.platform_detail, name='platform-detail'),

     # List tenant's connected accounts
    path('platform-accounts/', views.platform_accounts, name='platform-accounts'),
    
    # Connect new platform account
    path('platform-accounts/connect/', views.platform_accounts_connect, name='platform-accounts-connect'),
    
    # Platform account detail operations
    path('platform-accounts/<uuid:account_id>/', views.platform_account_detail, name='platform-account-detail'),
]