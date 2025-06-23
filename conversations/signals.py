# conversations/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone

from .models import Message, Conversation, MessageReadStatus

channel_layer = get_channel_layer()

@receiver(post_save, sender=Message)
def handle_new_message(sender, instance, created, **kwargs):
    """
    Handle new message creation - send real-time notifications
    """
    if not created:
        return
    
    message = instance
    conversation = message.conversation
    tenant = message.tenant
    
    # Prepare message data for broadcast
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
        'is_new_conversation': _is_first_message_in_conversation(message)
    }
    
    # Broadcast to dashboard (all agents in tenant)
    async_to_sync(channel_layer.group_send)(
        f"dashboard_{tenant.id}",
        {
            'type': 'new_message_notification',
            'conversation_id': str(conversation.id),
            'message': message_data,
            'timestamp': timezone.now().isoformat()
        }
    )
    
    # Broadcast to conversation monitors
    async_to_sync(channel_layer.group_send)(
        f"conversation_{conversation.id}",
        {
            'type': 'new_message',
            'message': message_data
        }
    )
    
    # If customer message, update conversation stats
    if message.sender_type == 'customer':
        _update_conversation_for_customer_message(conversation)


@receiver(post_save, sender=Conversation)
def handle_conversation_update(sender, instance, created, **kwargs):
    """
    Handle conversation updates - notify dashboard of status changes
    """
    conversation = instance
    tenant = conversation.tenant
    
    # Prepare conversation update data
    update_data = {
        'id': str(conversation.id),
        'status': conversation.status,
        'current_handler_type': conversation.current_handler_type,
        'ai_enabled': conversation.ai_enabled,
        'priority': conversation.priority,
        'assigned_user': conversation.assigned_user.email if conversation.assigned_user else None,
        'updated_at': conversation.updated_at.isoformat()
    }
    
    if created:
        # New conversation created
        async_to_sync(channel_layer.group_send)(
            f"dashboard_{tenant.id}",
            {
                'type': 'conversation_created',
                'conversation': update_data,
                'customer_name': conversation.customer.display_name,
                'platform': conversation.platform.display_name,
                'timestamp': timezone.now().isoformat()
            }
        )
    else:
        # Existing conversation updated
        async_to_sync(channel_layer.group_send)(
            f"dashboard_{tenant.id}",
            {
                'type': 'conversation_updated',
                'conversation_id': str(conversation.id),
                'updates': update_data,
                'timestamp': timezone.now().isoformat()
            }
        )


@receiver(post_save, sender=MessageReadStatus)
def handle_message_read(sender, instance, created, **kwargs):
    """
    Handle message read status changes
    """
    if not created:
        return
    
    read_status = instance
    message = read_status.message
    conversation = message.conversation
    tenant = read_status.tenant
    user = read_status.user
    
    # Broadcast read status update to other agents
    async_to_sync(channel_layer.group_send)(
        f"dashboard_{tenant.id}",
        {
            'type': 'messages_read_update',
            'conversation_id': str(conversation.id),
            'message_ids': [str(message.id)],
            'read_by_user': user.email,
            'read_at': read_status.read_at.isoformat()
        }
    )


def _is_first_message_in_conversation(message):
    """Check if this is the first message in the conversation"""
    return not Message.objects.filter(
        conversation=message.conversation,
        created_at__lt=message.created_at
    ).exists()


def _update_conversation_for_customer_message(conversation):
    """Update conversation metadata when customer sends message"""
    # Update last message timestamp
    conversation.last_message_at = timezone.now()
    
    # If AI is enabled and no human assigned, ensure AI handling
    if conversation.ai_enabled and not conversation.assigned_user_id:
        conversation.current_handler_type = 'ai'
    
    conversation.save(update_fields=['last_message_at', 'current_handler_type'])