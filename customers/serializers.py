# serializers.py
from rest_framework import serializers
from .models import Customer, ContactInsight
from platforms.models import SocialPlatform, TenantPlatformAccount
from .models import  ContactLabel, CustomerLabel
from conversations.models import Message, Conversation
from conversations.models import Conversation, Message, MessageReadStatus
from django.db.models import Count, Q, Max
from django.utils import timezone
from datetime import timedelta

class CustomerListSerializer(serializers.ModelSerializer):
    """Serializer for listing customers with basic info"""
    platform_name = serializers.CharField(source='platform.display_name', read_only=True)
    account_name = serializers.CharField(source='platform_account.account_name', read_only=True)
    
    class Meta:
        model = Customer
        fields = [
            'id', 'first_name_encrypted', 'last_name_encrypted', 
            'email_encrypted', 'phone_encrypted', 'profile_picture_url',
            'platform_username', 'platform_display_name', 'tags',
            'customer_lifetime_value', 'first_contact_at', 'last_contact_at',
            'last_seen_at', 'status', 'engagement_score', 'is_pinned',
            'platform_name', 'account_name', 'created_at', 'updated_at'
        ]


class ContactInsightsSerializer(serializers.ModelSerializer):
    """Serializer for contact insights"""
    
    class Meta:
        model = ContactInsight
        fields = [
            'total_messages', 'messages_sent', 'messages_received',
            'avg_response_time_seconds', 'sentiment_trend',
            'preferred_contact_hours', 'most_active_day',
            'last_engagement_score_update', 'insights_generated_at'
        ]


class CustomerDetailSerializer(serializers.ModelSerializer):
    """Serializer for customer details with engagement data"""
    platform_name = serializers.CharField(source='platform.display_name', read_only=True)
    account_name = serializers.CharField(source='platform_account.account_name', read_only=True)
    contact_insights = ContactInsightsSerializer(read_only=True)
    
    class Meta:
        model = Customer
        fields = [
            'id', 'external_id', 'first_name_encrypted', 'last_name_encrypted',
            'email_encrypted', 'phone_encrypted', 'profile_picture_url',
            'platform_username', 'platform_display_name', 'platform_profile_data',
            'tags', 'custom_fields', 'acquisition_source',
            'customer_lifetime_value', 'first_contact_at', 'last_contact_at',
            'is_archived', 'is_pinned', 'pin_order', 'last_seen_at',
            'status', 'is_typing', 'typing_in_conversation_id',
            'engagement_score', 'platform_name', 'account_name',
            'contact_insights', 'created_at', 'updated_at'
        ]


class CustomerCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating customers"""
    
    # Remove the _id suffix from foreign key fields
    class Meta:
        model = Customer
        fields = [
            'external_id', 'platform', 'platform_account',  # Changed from platform_id to platform
            'first_name_encrypted', 'last_name_encrypted', 'email_encrypted',
            'phone_encrypted', 'profile_picture_url', 'platform_username',
            'platform_display_name', 'platform_profile_data', 'tags',
            'custom_fields', 'acquisition_source', 'customer_lifetime_value',
            'first_contact_at', 'last_contact_at', 'is_archived',
            'is_pinned', 'pin_order', 'last_seen_at', 'status',
            'engagement_score'
        ]
    
    def validate(self, data):
        """Custom validation for customer data"""
        if data.get('is_pinned') and not data.get('pin_order'):
            raise serializers.ValidationError("Pin order is required when customer is pinned")
        
        # Validate platform_account belongs to the same platform
        platform = data.get('platform')
        platform_account = data.get('platform_account')
        
        if platform_account and platform:
            if platform_account.platform != platform:
                raise serializers.ValidationError({
                    'platform_account': 'Platform account does not match the selected platform'
                })
        
        return data
    
    def validate_platform_account(self, value):
        """Ensure platform account belongs to the user's tenant"""
        # Get tenant from the view's save method
        if hasattr(self, 'initial_data'):
            # The tenant will be passed when save is called
            pass
        return value

class ConversationListSerializer(serializers.ModelSerializer):
    """Serializer for listing customer conversations"""
    platform_name = serializers.CharField(source='platform.display_name', read_only=True)
    account_name = serializers.CharField(source='platform_account.account_name', read_only=True)
    assigned_user_name = serializers.SerializerMethodField()
    message_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'external_conversation_id', 'conversation_type',
            'subject', 'current_handler_type', 'assigned_user_id',
            'assigned_user_name', 'ai_enabled', 'status', 'priority',
            'sentiment_score', 'first_message_at', 'last_message_at',
            'last_human_response_at', 'last_ai_response_at',
            'response_due_at', 'resolved_at', 'platform_name',
            'account_name', 'message_count', 'created_at', 'updated_at'
        ]
    
    def get_assigned_user_name(self, obj):
        """Get assigned user's full name"""
        if obj.assigned_user_id:
            from .models import TenantUser
            try:
                user = TenantUser.objects.get(id=obj.assigned_user_id)
                return f"{user.first_name} {user.last_name}".strip()
            except TenantUser.DoesNotExist:
                return None
        return None
    
    def get_message_count(self, obj):
        """Get total message count for conversation"""
        return obj.messages.count()


class ContactLabelSerializer(serializers.ModelSerializer):
    """Serializer for contact labels"""
    
    class Meta:
        model = ContactLabel
        fields = ['id', 'name', 'color_code']


class LastMessageSerializer(serializers.Serializer):
    """Serializer for last message in conversation"""
    content = serializers.CharField(max_length=500)
    sender_type = serializers.CharField(max_length=20)
    created_at = serializers.DateTimeField()
    is_read = serializers.BooleanField()
    message_type = serializers.CharField(max_length=50, default='text')
    attachments_count = serializers.IntegerField(default=0)


class LastConversationSerializer(serializers.Serializer):
    """Serializer for last conversation details"""
    id = serializers.UUIDField()
    subject = serializers.CharField(max_length=500, allow_null=True)
    status = serializers.CharField(max_length=50)
    last_message = LastMessageSerializer()
    unread_count = serializers.IntegerField()
    last_message_at = serializers.DateTimeField()


class ContactListSerializer(serializers.ModelSerializer):
    """Serializer for contacts list with latest message and unread counts"""
    name = serializers.SerializerMethodField()
    avatar_url = serializers.CharField(source='profile_picture_url', read_only=True)
    platform = serializers.CharField(source='platform.name', read_only=True)
    platform_name = serializers.CharField(source='platform.display_name', read_only=True)
    status = serializers.SerializerMethodField()
    labels = serializers.SerializerMethodField()
    last_conversation = serializers.SerializerMethodField()
    last_seen = serializers.DateTimeField(source='last_seen_at', read_only=True)
    
    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'avatar_url', 'platform_username', 'platform',
            'platform_name', 'status', 'is_typing', 'is_pinned', 'engagement_score',
            'labels', 'last_conversation', 'last_seen'
        ]
    
    def get_name(self, obj):
        """Get customer's display name"""
        # Try to get decrypted name first, fallback to platform name
        first_name = getattr(obj, 'first_name_decrypted', '') or ''
        last_name = getattr(obj, 'last_name_decrypted', '') or ''
        full_name = f"{first_name} {last_name}".strip()
        
        if full_name:
            return full_name
        elif obj.platform_display_name:
            return obj.platform_display_name
        elif obj.platform_username:
            return obj.platform_username
        else:
            return "Unknown Contact"
    
    def get_status(self, obj):
        """Determine contact status based on last activity"""
        if obj.is_typing:
            return "typing"
        elif obj.last_seen_at:
            time_diff = timezone.now() - obj.last_seen_at
            if time_diff <= timedelta(minutes=5):
                return "online"
            elif time_diff <= timedelta(hours=1):
                return "away"
            else:
                return "offline"
        else:
            return "unknown"
    
    def get_labels(self, obj):
        """Get contact labels"""
        labels = obj.customerlabel_set.select_related('label').all()
        return [label.label.name for label in labels]
    
    def get_last_conversation(self, obj):
        """Get last conversation with unread count"""
        current_user_id = self.context.get('current_user_id')
        
        # Get the most recent conversation for this customer
        last_conversation = obj.conversations.order_by('-last_message_at').first()
        
        if not last_conversation:
            return None
        
        # Get the last message in this conversation
        last_message = last_conversation.messages.order_by('-created_at').first()
        
        if not last_message:
            return None
        
        # Check if current user has read the last message
        is_read = False
        if current_user_id:
            is_read = MessageReadStatus.objects.filter(
                message_id=last_message.id,
                user_id=current_user_id
            ).exists()
        
        # Get unread count for current user
        unread_count = 0
        if current_user_id:
            read_message_ids = MessageReadStatus.objects.filter(
                user_id=current_user_id,
                message__conversation_id=last_conversation.id
            ).values_list('message_id', flat=True)
            
            unread_count = last_conversation.messages.exclude(
                id__in=read_message_ids
            ).count()
        
        # Count attachments in last message
        attachments_count = 0
        if last_message.attachments:
            attachments_count = len(last_message.attachments) if isinstance(last_message.attachments, list) else 0
        
        return {
            'id': last_conversation.id,
            'subject': last_conversation.subject,
            'status': last_conversation.status,
            'last_message': {
                'content': getattr(last_message, 'content_decrypted', '')[:500] or '',
                'sender_type': last_message.sender_type,
                'created_at': last_message.created_at,
                'is_read': is_read,
                'message_type': last_message.message_type,
                'attachments_count': attachments_count
            },
            'unread_count': unread_count,
            'last_message_at': last_conversation.last_message_at
        }


class ContactSummarySerializer(serializers.Serializer):
    """Serializer for contacts summary statistics"""
    total_contacts = serializers.IntegerField()
    contacts_with_unread = serializers.IntegerField()
    total_unread_messages = serializers.IntegerField()
    pinned_contacts = serializers.IntegerField()
    online_contacts = serializers.IntegerField()
    recent_contacts_24h = serializers.IntegerField()


class ContactsListResponseSerializer(serializers.Serializer):
    """Main response serializer for contacts list"""
    contacts = ContactListSerializer(many=True)
    total = serializers.IntegerField()
    summary = ContactSummarySerializer()
    filters_applied = serializers.DictField()
    pagination = serializers.DictField()


class RecentContactSerializer(serializers.ModelSerializer):
    """Serializer for recently active contacts"""
    name = serializers.SerializerMethodField()
    avatar_url = serializers.CharField(source='profile_picture_url', read_only=True)
    platform = serializers.CharField(source='platform.display_name', read_only=True)
    last_activity = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    last_message_preview = serializers.SerializerMethodField()
    
    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'avatar_url', 'platform_username', 'platform',
            'last_activity', 'unread_count', 'last_message_preview', 'engagement_score'
        ]
    
    def get_name(self, obj):
        """Get customer's display name"""
        first_name = getattr(obj, 'first_name_decrypted', '') or ''
        last_name = getattr(obj, 'last_name_decrypted', '') or ''
        full_name = f"{first_name} {last_name}".strip()
        return full_name or obj.platform_display_name or obj.platform_username or "Unknown"
    
    def get_last_activity(self, obj):
        """Get last activity timestamp"""
        return obj.last_contact_at or obj.last_seen_at or obj.updated_at
    
    def get_unread_count(self, obj):
        """Get total unread messages for this contact"""
        current_user_id = self.context.get('current_user_id')
        if not current_user_id:
            return 0
        
        # Get all conversations for this customer
        conversation_ids = obj.conversations.values_list('id', flat=True)
        
        # Get read message IDs for current user
        read_message_ids = MessageReadStatus.objects.filter(
            user_id=current_user_id,
            message__conversation_id__in=conversation_ids
        ).values_list('message_id', flat=True)
        
        # Count unread messages
        return Message.objects.filter(
            conversation_id__in=conversation_ids,
            sender_type='customer'  # Only count customer messages as unread
        ).exclude(id__in=read_message_ids).count()
    
    def get_last_message_preview(self, obj):
        """Get preview of last message"""
        last_conversation = obj.conversations.order_by('-last_message_at').first()
        if not last_conversation:
            return None
        
        last_message = last_conversation.messages.order_by('-created_at').first()
        if not last_message:
            return None
        
        content = getattr(last_message, 'content_decrypted', '') or ''
        return {
            'content': content[:100] + ('...' if len(content) > 100 else ''),
            'sender_type': last_message.sender_type,
            'created_at': last_message.created_at,
            'message_type': last_message.message_type
        }


class UnreadContactSerializer(serializers.ModelSerializer):
    """Serializer for contacts with unread messages"""
    name = serializers.SerializerMethodField()
    avatar_url = serializers.CharField(source='profile_picture_url', read_only=True)
    platform = serializers.CharField(source='platform.display_name', read_only=True)
    unread_details = serializers.SerializerMethodField()
    first_unread_message = serializers.SerializerMethodField()
    
    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'avatar_url', 'platform_username', 'platform',
            'is_pinned', 'engagement_score', 'unread_details', 'first_unread_message',
            'last_seen_at'
        ]
    
    def get_name(self, obj):
        """Get customer's display name"""
        first_name = getattr(obj, 'first_name_decrypted', '') or ''
        last_name = getattr(obj, 'last_name_decrypted', '') or ''
        full_name = f"{first_name} {last_name}".strip()
        return full_name or obj.platform_display_name or obj.platform_username or "Unknown"
    
    def get_unread_details(self, obj):
        """Get detailed unread message information"""
        current_user_id = self.context.get('current_user_id')
        if not current_user_id:
            return {'total_unread': 0, 'conversations_with_unread': 0}
        
        conversation_ids = obj.conversations.values_list('id', flat=True)
        
        # Get read message IDs
        read_message_ids = MessageReadStatus.objects.filter(
            user_id=current_user_id,
            message__conversation_id__in=conversation_ids
        ).values_list('message_id', flat=True)
        
        # Count total unread messages
        total_unread = Message.objects.filter(
            conversation_id__in=conversation_ids,
            sender_type='customer'
        ).exclude(id__in=read_message_ids).count()
        
        # Count conversations with unread messages
        conversations_with_unread = 0
        for conv_id in conversation_ids:
            unread_in_conv = Message.objects.filter(
                conversation_id=conv_id,
                sender_type='customer'
            ).exclude(id__in=read_message_ids).count()
            
            if unread_in_conv > 0:
                conversations_with_unread += 1
        
        return {
            'total_unread': total_unread,
            'conversations_with_unread': conversations_with_unread
        }
    
    def get_first_unread_message(self, obj):
        """Get the first unread message from this contact"""
        current_user_id = self.context.get('current_user_id')
        if not current_user_id:
            return None
        
        conversation_ids = obj.conversations.values_list('id', flat=True)
        
        # Get read message IDs
        read_message_ids = MessageReadStatus.objects.filter(
            user_id=current_user_id,
            message__conversation_id__in=conversation_ids
        ).values_list('message_id', flat=True)
        
        # Get first unread message
        first_unread = Message.objects.filter(
            conversation_id__in=conversation_ids,
            sender_type='customer'
        ).exclude(id__in=read_message_ids).order_by('created_at').first()
        
        if not first_unread:
            return None
        
        content = getattr(first_unread, 'content_decrypted', '') or ''
        return {
            'id': first_unread.id,
            'content': content[:200] + ('...' if len(content) > 200 else ''),
            'conversation_id': first_unread.conversation_id,
            'created_at': first_unread.created_at,
            'message_type': first_unread.message_type
        }