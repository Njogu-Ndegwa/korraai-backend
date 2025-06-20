# urls.py
from django.urls import path
from . import views

app_name = 'customers'

urlpatterns = [
    # Customer management endpoints
    path('customers/', views.customer_list_create, name='customer-list-create'),
    path('customers/<uuid:customer_id>/', views.customer_detail, name='customer-detail'),
    path('customers/<uuid:customer_id>/conversations/', views.customer_conversations, name='customer-conversations'),
    path('contacts/', views.contacts_list, name='contacts-list'),
    path('contacts/recent/', views.contacts_recent, name='contacts-recent'),
    path('contacts/unread/', views.contacts_unread, name='contacts-unread'),
]