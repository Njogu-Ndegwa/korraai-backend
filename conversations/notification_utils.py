# conversations/notification_utils.py
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone
from typing import List, Dict, Any

channel_layer = get_channel_layer()

class DashboardNotifier:
    """Utility class for sending dashboard notifications"""
    
    @staticmethod
    def notify_new_message(message, conversation):
        """Notify dashboard of new message"""
        message_data = {
            'id': str(message.id),
            'conversation_id': str(conversation.id),
            'content': message.content_encrypted,
            'sender_type': message.sender_type,
            'sender_name': message.sender_name,
            'direction': message.direction,
            'created_at': message.created_at.isoformat(),
            'customer_name': conversation.customer.display_name,
            'platform': conversation.platform.display_name,
            'conversation_status': conversation.status,
            'priority': conversation.priority
        }
        
        async_to_sync(channel_layer.group_send)(
            f"dashboard_{conversation.tenant.id}",
            {
                'type': 'new_message_notification',
                'conversation_id': str(conversation.id),
                'message': message_data,
                'timestamp': timezone.now().isoformat()
            }
        )
    
    @staticmethod
    def notify_conversation_assigned(conversation, assigned_user, assigned_by_user):
        """Notify when conversation is assigned to user"""
        async_to_sync(channel_layer.group_send)(
            f"dashboard_{conversation.tenant.id}",
            {
                'type': 'conversation_assigned',
                'conversation_id': str(conversation.id),
                'assigned_to': assigned_user.email,
                'assigned_by': assigned_by_user.email,
                'customer_name': conversation.customer.display_name,
                'timestamp': timezone.now().isoformat()
            }
        )
        
        # Send personal notification to assigned user
        async_to_sync(channel_layer.group_send)(
            f"user_{assigned_user.id}_dashboard",
            {
                'type': 'conversation_assigned_to_me',
                'conversation_id': str(conversation.id),
                'customer_name': conversation.customer.display_name,
                'platform': conversation.platform.display_name,
                'assigned_by': assigned_by_user.first_name + ' ' + assigned_by_user.last_name,
                'timestamp': timezone.now().isoformat()
            }
        )
    
    @staticmethod
    def notify_ai_handover(conversation, reason):
        """Notify when conversation is handed over from AI to human"""
        async_to_sync(channel_layer.group_send)(
            f"dashboard_{conversation.tenant.id}",
            {
                'type': 'ai_handover_required',
                'conversation_id': str(conversation.id),
                'customer_name': conversation.customer.display_name,
                'platform': conversation.platform.display_name,
                'reason': reason,
                'priority': 'high',
                'timestamp': timezone.now().isoformat()
            }
        )
    
    @staticmethod
    def notify_customer_typing(conversation, is_typing=True):
        """Notify when customer starts/stops typing"""
        async_to_sync(channel_layer.group_send)(
            f"conversation_{conversation.id}",
            {
                'type': 'customer_typing',
                'conversation_id': str(conversation.id),
                'customer_name': conversation.customer.display_name,
                'is_typing': is_typing,
                'timestamp': timezone.now().isoformat()
            }
        )
        
        # Also notify dashboard for typing indicators
        async_to_sync(channel_layer.group_send)(
            f"dashboard_{conversation.tenant.id}",
            {
                'type': 'customer_typing_status',
                'conversation_id': str(conversation.id),
                'is_typing': is_typing,
                'timestamp': timezone.now().isoformat()
            }
        )
    
    @staticmethod
    def notify_bulk_read_status(conversation, message_ids: List[str], user, read_at):
        """Notify bulk message read status update"""
        async_to_sync(channel_layer.group_send)(
            f"dashboard_{conversation.tenant.id}",
            {
                'type': 'messages_read_update',
                'conversation_id': str(conversation.id),
                'message_ids': message_ids,
                'read_by_user': user.email,
                'read_at': read_at.isoformat(),
                'count': len(message_ids)
            }
        )