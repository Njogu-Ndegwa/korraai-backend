# ai/urls.py
from django.urls import path
from . import views

app_name = 'ai'  # Add this line

urlpatterns = [
    path('ai-settings/', views.ai_settings_list_create, name='ai-settings-list-create'),
    path('ai-settings/<uuid:setting_id>/', views.ai_settings_detail, name='ai-settings-detail'),
]