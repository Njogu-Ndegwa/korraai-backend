# urls.py
from django.urls import path
from . import views

app_name = 'ai_settings'

urlpatterns = [
    # General AI settings
    path('ai/settings/', views.ai_settings, name='ai-settings'),

     # Create AI settings for a specific platform
    path('ai/settings/platform/<uuid:platform_id>/', views.ai_settings_create, name='ai-settings-create'),
    
    # Bulk create AI settings for multiple platforms
    path('ai/settings/bulk/', views.ai_settings_bulk_create, name='ai-settings-bulk-create'),
    
    # Platform-specific AI settings
    path('ai/settings/platform/<uuid:platform_id>/', views.platform_ai_settings, name='platform-ai-settings'),
    
    # AI configuration testing
    path('ai/settings/test/', views.test_ai_settings, name='test-ai-settings'),

     # Intent category management
    path('ai/intents/', views.intent_list_create, name='intent-list-create'),

    path('ai/intents/<uuid:intent_id>/', views.intent_detail, name='intent-detail'),
    
    # Intent analytics
    path('ai/intents/analytics/', views.intent_analytics, name='intent-analytics'),
    
    # Intent auto-actions configuration
    path('ai/intents/<uuid:intent_id>/actions/', views.intent_auto_actions, name='intent-auto-actions'),

    path('ai/intents/', views.intent_list_create, name='intent-list-create'),
    
    path('ai/intents/<uuid:intent_id>/', views.intent_detail, name='intent-detail'),
    
    # Intent analytics
    path('ai/intents/analytics/', views.intent_analytics, name='intent-analytics'),
    
    # Intent auto-actions configuration
    path('ai/intents/<uuid:intent_id>/actions/', views.intent_auto_actions, name='intent-auto-actions'),
]