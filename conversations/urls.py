# urls.py
from django.urls import path
from . import views

app_name = 'conversations'

urlpatterns = [
    # Conversation listing and details
    path('create-conversation', views.create_conversation, name='create_conversation'),
    path('conversations/', views.conversation_list, name='conversation-list'),
    path('conversations/<uuid:conversation_id>/', views.conversation_detail, name='conversation-detail'),
    path('conversations/<uuid:conversation_id>/takeover/', views.conversation_takeover, name='conversation-takeover'),
    path('conversations/<uuid:conversation_id>/ai-control/', views.conversation_ai_control, name='conversation-ai-control'),
    path('conversations/<uuid:conversation_id>/messages/', views.conversation_messages, name='conversation-messages'),
    path('messages/<uuid:message_id>/', views.message_detail, name='message-detail'),
    path('messages/<uuid:message_id>/mark-read/', views.message_mark_read, name='message-mark-read'),
    path('<uuid:conversation_id>/typing/', views.update_typing_status, name='update_typing_status'),
    path('<uuid:conversation_id>/assign/', views.assign_conversation, name='assign_conversation'),
    path('unread-counts/', views.unread_counts, name='unread_counts'),
]