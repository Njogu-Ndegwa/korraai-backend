# serializers.py
from rest_framework import serializers
from .models import Conversation, Message, MessageReadStatus
from tenants.models import TenantUser
from platforms.models import SocialPlatform, TenantPlatformAccount
from customers.models import Customer
from leads.models import Lead
from tenants.models import TenantUser


class ConversationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating conversations"""
    
    class Meta:
        model = Conversation
        fields = [
            'id',
            'customer',
            'platform',
            'platform_account',
            'lead',
            'external_conversation_id',
            'conversation_type',
            'subject',
            'current_handler_type',
            'assigned_user',
            'ai_enabled',
            'status',
            'priority',
            'sentiment_score',
            'first_message_at',
            'response_due_at'
        ]
        read_only_fields = ['id']
        
    def validate_customer(self, value):
        """Ensure customer belongs to the tenant"""
        tenant = self.context['tenant']
        if value.tenant != tenant:
            raise serializers.ValidationError(
                "Customer does not belong to your organization"
            )
        return value
    
    def validate_platform_account(self, value):
        """Ensure platform account belongs to the tenant"""
        tenant = self.context['tenant']
        if value.tenant != tenant:
            raise serializers.ValidationError(
                "Platform account does not belong to your organization"
            )
        return value
    
    def validate_lead(self, value):
        """Ensure lead belongs to the tenant if provided"""
        if value:
            tenant = self.context['tenant']
            if value.tenant != tenant:
                raise serializers.ValidationError(
                    "Lead does not belong to your organization"
                )
        return value
    
    def validate_assigned_user(self, value):
        """Ensure assigned user belongs to the tenant if provided"""
        if value:
            tenant = self.context['tenant']
            if value.tenant != tenant:
                raise serializers.ValidationError(
                    "User does not belong to your organization"
                )
        return value
    
    def validate(self, data):
        """Cross-field validation"""
        # Ensure platform account matches the platform
        platform_account = data.get('platform_account')
        platform = data.get('platform')
        
        if platform_account and platform:
            if platform_account.platform != platform:
                raise serializers.ValidationError({
                    'platform_account': 'Platform account does not match the selected platform'
                })
        
        # Set default values if not provided
        if 'current_handler_type' not in data:
            data['current_handler_type'] = 'ai' if data.get('ai_enabled', True) else 'human'
            
        if 'status' not in data:
            data['status'] = 'active'
            
        if 'priority' not in data:
            data['priority'] = 'normal'
            
        return data
    
    def create(self, validated_data):
        """Create conversation with tenant from context"""
        validated_data['tenant'] = self.context['tenant']
        return super().create(validated_data)


class ConversationResponseSerializer(serializers.ModelSerializer):
    """Serializer for conversation responses"""
    
    customer_name = serializers.SerializerMethodField()
    platform_name = serializers.CharField(source='platform.display_name', read_only=True)
    assigned_user_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = [
            'id',
            'customer',
            'customer_name',
            'platform',
            'platform_name',
            'platform_account',
            'lead',
            'external_conversation_id',
            'conversation_type',
            'subject',
            'current_handler_type',
            'assigned_user',
            'assigned_user_name',
            'ai_enabled',
            'ai_paused_by_user',
            'ai_paused_at',
            'ai_pause_reason',
            'can_ai_resume',
            'handover_reason',
            'status',
            'priority',
            'sentiment_score',
            'first_message_at',
            'last_message_at',
            'last_human_response_at',
            'last_ai_response_at',
            'response_due_at',
            'resolved_at',
            'created_at',
            'updated_at'
        ]
    
    def get_customer_name(self, obj):
        """Get customer display name"""
        if obj.customer.platform_display_name:
            return obj.customer.platform_display_name
        elif obj.customer.first_name_encrypted or obj.customer.last_name_encrypted:
            # Note: You'll need to decrypt these in production
            return f"{obj.customer.first_name_encrypted or ''} {obj.customer.last_name_encrypted or ''}".strip()
        return obj.customer.platform_username or 'Unknown Customer'
    
    def get_assigned_user_name(self, obj):
        """Get assigned user full name"""
        if obj.assigned_user:
            return f"{obj.assigned_user.first_name} {obj.assigned_user.last_name}".strip()
        return None

class ConversationListSerializer(serializers.ModelSerializer):
    """Serializer for listing conversations with essential info"""
    customer_name = serializers.SerializerMethodField()
    customer_platform_username = serializers.CharField(source='customer.platform_username', read_only=True)
    platform_name = serializers.CharField(source='platform.display_name', read_only=True)
    account_name = serializers.CharField(source='platform_account.account_name', read_only=True)
    assigned_user_name = serializers.SerializerMethodField()
    ai_paused_by_name = serializers.SerializerMethodField()
    lead_title = serializers.CharField(source='lead.title', read_only=True)
    message_count = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    last_message_preview = serializers.SerializerMethodField()
    response_overdue = serializers.SerializerMethodField()
    time_since_last_message = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'external_conversation_id', 'conversation_type', 'subject',
            'current_handler_type', 'ai_enabled', 'ai_paused_at', 'ai_pause_reason',
            'can_ai_resume', 'handover_reason', 'status', 'priority', 'sentiment_score',
            'first_message_at', 'last_message_at', 'last_human_response_at',
            'last_ai_response_at', 'response_due_at', 'resolved_at',
            'customer_name', 'customer_platform_username', 'platform_name',
            'account_name', 'assigned_user_name', 'ai_paused_by_name', 'lead_title',
            'message_count', 'unread_count', 'last_message_preview', 'response_overdue',
            'time_since_last_message', 'created_at', 'updated_at'
        ]
    
    def get_customer_name(self, obj):
        """Get customer's display name"""
        if obj.customer:
            # Try to get decrypted name first, fallback to platform name
            first_name = getattr(obj.customer, 'first_name_decrypted', '') or ''
            last_name = getattr(obj.customer, 'last_name_decrypted', '') or ''
            full_name = f"{first_name} {last_name}".strip()
            return full_name or obj.customer.platform_display_name or obj.customer.platform_username
        return None
    
    def get_assigned_user_name(self, obj):
        """Get assigned user's full name"""
        if obj.assigned_user_id:
            try:
                user = TenantUser.objects.get(id=obj.assigned_user_id)
                return f"{user.first_name} {user.last_name}".strip()
            except TenantUser.DoesNotExist:
                return None
        return None
    
    def get_ai_paused_by_name(self, obj):
        """Get name of user who paused AI"""
        if obj.ai_paused_by_user_id:
            try:
                user = TenantUser.objects.get(id=obj.ai_paused_by_user_id)
                return f"{user.first_name} {user.last_name}".strip()
            except TenantUser.DoesNotExist:
                return None
        return None
    
    def get_message_count(self, obj):
        """Get total message count"""
        return getattr(obj, 'message_count', obj.messages.count())
    
    def get_unread_count(self, obj):
        """Get unread message count for current user"""
        # This would require implementing read status tracking
        # For now, return 0 as placeholder
        return 0
    
    def get_last_message_preview(self, obj):
        """Get preview of last message"""
        last_message = obj.messages.order_by('-created_at').first()
        if last_message:
            # Assuming content is encrypted and needs decryption
            content = getattr(last_message, 'content_decrypted', '') or ''
            return content[:100] + '...' if len(content) > 100 else content
        return None
    
    def get_response_overdue(self, obj):
        """Check if response is overdue"""
        if obj.response_due_at:
            from django.utils import timezone
            return timezone.now() > obj.response_due_at
        return False
    
    def get_time_since_last_message(self, obj):
        """Get time since last message in minutes"""
        if obj.last_message_at:
            from django.utils import timezone
            delta = timezone.now() - obj.last_message_at
            return int(delta.total_seconds() / 60)
        return None


class ConversationDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed conversation view"""
    customer_details = serializers.SerializerMethodField()
    platform_details = serializers.SerializerMethodField()
    account_details = serializers.SerializerMethodField()
    assigned_user_details = serializers.SerializerMethodField()
    ai_paused_by_details = serializers.SerializerMethodField()
    lead_details = serializers.SerializerMethodField()
    message_count = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()
    conversation_metrics = serializers.SerializerMethodField()
    ai_settings = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'external_conversation_id', 'conversation_type', 'subject',
            'current_handler_type', 'ai_enabled', 'ai_paused_at', 'ai_pause_reason',
            'can_ai_resume', 'handover_reason', 'status', 'priority', 'sentiment_score',
            'first_message_at', 'last_message_at', 'last_human_response_at',
            'last_ai_response_at', 'response_due_at', 'resolved_at',
            'customer_details', 'platform_details', 'account_details',
            'assigned_user_details', 'ai_paused_by_details', 'lead_details',
            'message_count', 'messages', 'conversation_metrics', 'ai_settings',
            'created_at', 'updated_at'
        ]
    
    def get_customer_details(self, obj):
        """Get comprehensive customer information"""
        if obj.customer:
            return {
                'id': obj.customer.id,
                'name': self._get_customer_name(obj.customer),
                'email': obj.customer.email_encrypted,
                'phone': obj.customer.phone_encrypted,
                'platform_username': obj.customer.platform_username,
                'platform_display_name': obj.customer.platform_display_name,
                'profile_picture_url': obj.customer.profile_picture_url,
                'engagement_score': obj.customer.engagement_score,
                'status': obj.customer.status,
                'is_typing': obj.customer.is_typing,
                'last_seen_at': obj.customer.last_seen_at,
                'tags': obj.customer.tags,
                'custom_fields': obj.customer.custom_fields
            }
        return None
    
    def get_platform_details(self, obj):
        """Get platform information"""
        if obj.platform:
            return {
                'id': obj.platform.id,
                'name': obj.platform.name,
                'display_name': obj.platform.display_name,
                'api_version': obj.platform.api_version
            }
        return None
    
    def get_account_details(self, obj):
        """Get platform account information"""
        if obj.platform_account:
            return {
                'id': obj.platform_account.id,
                'account_name': obj.platform_account.account_name,
                'platform_account_id': obj.platform_account.platform_account_id,
                'connection_status': obj.platform_account.connection_status,
                'last_sync': obj.platform_account.last_sync
            }
        return None
    
    def get_assigned_user_details(self, obj):
        """Get assigned user information"""
        if obj.assigned_user_id:
            try:
                user = TenantUser.objects.get(id=obj.assigned_user_id)
                return {
                    'id': user.id,
                    'name': f"{user.first_name} {user.last_name}".strip(),
                    'email': user.email,
                    'role': user.role,
                    'is_active': user.is_active,
                    'last_login': user.last_login
                }
            except TenantUser.DoesNotExist:
                return None
        return None
    
    def get_ai_paused_by_details(self, obj):
        """Get details of user who paused AI"""
        if obj.ai_paused_by_user_id:
            try:
                user = TenantUser.objects.get(id=obj.ai_paused_by_user_id)
                return {
                    'id': user.id,
                    'name': f"{user.first_name} {user.last_name}".strip(),
                    'email': user.email,
                    'paused_at': obj.ai_paused_at,
                    'pause_reason': obj.ai_pause_reason
                }
            except TenantUser.DoesNotExist:
                return None
        return None
    
    def get_lead_details(self, obj):
        """Get associated lead information"""
        if obj.lead:
            return {
                'id': obj.lead.id,
                'title': obj.lead.title,
                'description': obj.lead.description,
                'estimated_value': obj.lead.estimated_value,
                'probability': obj.lead.probability,
                'status': obj.lead.status,
                'stage_name': obj.lead.lead_stage.display_name if obj.lead.lead_stage else None,
                'category_name': obj.lead.lead_category.display_name if obj.lead.lead_category else None
            }
        return None
    
    def get_message_count(self, obj):
        """Get message statistics"""
        messages = obj.messages.all()
        return {
            'total': messages.count(),
            'customer': messages.filter(sender_type='customer').count(),
            'agent': messages.filter(sender_type='agent').count(),
            'ai': messages.filter(sender_type='ai').count(),
            'system': messages.filter(sender_type='system').count()
        }
    
    def get_messages(self, obj):
        """Get recent messages (limit for performance)"""
        # Only return last 50 messages to avoid performance issues
        recent_messages = obj.messages.order_by('-created_at')[:50]
        return [{
            'id': msg.id,
            'message_type': msg.message_type,
            'direction': msg.direction,
            'sender_type': msg.sender_type,
            'sender_name': msg.sender_name,
            'content': getattr(msg, 'content_decrypted', '') or '',
            'attachments': msg.attachments,
            'ai_intent': msg.ai_intent,
            'ai_sentiment': msg.ai_sentiment,
            'delivery_status': msg.delivery_status,
            'platform_timestamp': msg.platform_timestamp,
            'created_at': msg.created_at
        } for msg in reversed(recent_messages)]
    
    def get_conversation_metrics(self, obj):
        """Get conversation performance metrics"""
        # This would typically come from a related ConversationMetrics model
        return {
            'first_response_time_seconds': getattr(obj, 'first_response_time_seconds', None),
            'average_response_time_seconds': getattr(obj, 'average_response_time_seconds', None),
            'ai_handling_percentage': getattr(obj, 'ai_handling_percentage', None),
            'handover_count': getattr(obj, 'handover_count', 0)
        }
    
    def get_ai_settings(self, obj):
        """Get AI configuration for this conversation"""
        # This would come from tenant AI settings for the platform
        return {
            'enabled': obj.ai_enabled,
            'can_resume': obj.can_ai_resume,
            'paused_at': obj.ai_paused_at,
            'pause_reason': obj.ai_pause_reason,
            'confidence_threshold': None,  # Would come from tenant settings
            'auto_response_enabled': None  # Would come from tenant settings
        }
    
    def _get_customer_name(self, customer):
        """Helper method to get customer name"""
        first_name = getattr(customer, 'first_name_decrypted', '') or ''
        last_name = getattr(customer, 'last_name_decrypted', '') or ''
        full_name = f"{first_name} {last_name}".strip()
        return full_name or customer.platform_display_name or customer.platform_username


class ConversationTakeoverSerializer(serializers.Serializer):
    """Serializer for taking over conversation from AI"""
    reason = serializers.CharField(
        required=False, 
        allow_blank=True, 
        max_length=255,
        help_text="Reason for taking over the conversation"
    )
    pause_ai = serializers.BooleanField(
        default=True,
        help_text="Whether to pause AI for this conversation"
    )
    assign_to_me = serializers.BooleanField(
        default=True,
        help_text="Whether to assign the conversation to the current user"
    )


class ConversationAIControlSerializer(serializers.Serializer):
    """Serializer for enabling/disabling AI control"""
    ai_enabled = serializers.BooleanField(
        required=True,
        help_text="Whether AI should handle this conversation"
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text="Reason for enabling/disabling AI"
    )
    
    def validate(self, data):
        """Custom validation for AI control"""
        # If disabling AI, ensure there's a human to take over
        if not data.get('ai_enabled'):
            conversation = self.context.get('conversation')
            if conversation and not conversation.assigned_user_id:
                # Could auto-assign to current user or require explicit assignment
                pass
        
        return data




class MessageListSerializer(serializers.ModelSerializer):
    """Serializer for listing messages in conversation with read status"""
    sender_details = serializers.SerializerMethodField()
    is_read_by_current_user = serializers.SerializerMethodField()
    read_by_users = serializers.SerializerMethodField()
    content_decrypted = serializers.SerializerMethodField()
    time_since_sent = serializers.SerializerMethodField()
    delivery_info = serializers.SerializerMethodField()
    
    class Meta:
        model = Message
        fields = [
            'id', 'external_message_id', 'message_type', 'direction',
            'sender_type', 'sender_id', 'sender_name', 'content_decrypted',
            'content_hash', 'raw_content', 'attachments', 'ai_processed',
            'ai_intent', 'ai_entities', 'ai_sentiment', 'ai_confidence',
            'delivery_status', 'is_deleted', 'deleted_at', 'platform_timestamp',
            'processed_at', 'sender_details', 'is_read_by_current_user',
            'read_by_users', 'time_since_sent', 'delivery_info', 'created_at'
        ]
    
    def get_sender_details(self, obj):
        """Get detailed sender information"""
        if obj.sender_type == 'customer' and obj.sender_id:
            try:
                from .models import Customer
                customer = Customer.objects.get(id=obj.sender_id)
                return {
                    'type': 'customer',
                    'id': customer.id,
                    'name': self._get_customer_name(customer),
                    'username': customer.platform_username,
                    'display_name': customer.platform_display_name,
                    'profile_picture': customer.profile_picture_url,
                    'engagement_score': customer.engagement_score
                }
            except Customer.DoesNotExist:
                pass
        
        elif obj.sender_type in ['agent', 'human'] and obj.sender_id:
            try:
                user = TenantUser.objects.get(id=obj.sender_id)
                return {
                    'type': 'agent',
                    'id': user.id,
                    'name': f"{user.first_name} {user.last_name}".strip(),
                    'email': user.email,
                    'role': user.role
                }
            except TenantUser.DoesNotExist:
                pass
        
        elif obj.sender_type == 'ai':
            return {
                'type': 'ai',
                'name': 'AI Assistant',
                'confidence': obj.ai_confidence
            }
        
        elif obj.sender_type == 'system':
            return {
                'type': 'system',
                'name': 'System'
            }
        
        # Fallback to sender_name from message
        return {
            'type': obj.sender_type,
            'name': obj.sender_name or 'Unknown'
        }
    
    def get_is_read_by_current_user(self, obj):
        """Check if current user has read this message"""
        current_user_id = self.context.get('current_user_id')
        if current_user_id:
            return MessageReadStatus.objects.filter(
                message_id=obj.id,
                user_id=current_user_id
            ).exists()
        return False
    
    def get_read_by_users(self, obj):
        """Get list of users who have read this message"""
        read_statuses = MessageReadStatus.objects.filter(
            message_id=obj.id
        ).select_related('user').order_by('read_at')
        
        return [{
            'user_id': status.user_id,
            'user_name': f"{status.user.first_name} {status.user.last_name}".strip(),
            'read_at': status.read_at
        } for status in read_statuses]
    
    def get_content_decrypted(self, obj):
        """Get decrypted message content"""
        # Assuming your model has a method to decrypt content
        return getattr(obj, 'content_decrypted', '') or ''
    
    def get_time_since_sent(self, obj):
        """Get time since message was sent in minutes"""
        if obj.created_at:
            delta = timezone.now() - obj.created_at
            return int(delta.total_seconds() / 60)
        return None
    
    def get_delivery_info(self, obj):
        """Get message delivery information"""
        return {
            'status': obj.delivery_status,
            'platform_timestamp': obj.platform_timestamp,
            'processed_at': obj.processed_at,
            'external_id': obj.external_message_id
        }
    
    def _get_customer_name(self, customer):
        """Helper method to get customer display name"""
        first_name = getattr(customer, 'first_name_decrypted', '') or ''
        last_name = getattr(customer, 'last_name_decrypted', '') or ''
        full_name = f"{first_name} {last_name}".strip()
        return full_name or customer.platform_display_name or customer.platform_username


class MessageDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed message view"""
    sender_details = serializers.SerializerMethodField()
    conversation_details = serializers.SerializerMethodField()
    read_status_details = serializers.SerializerMethodField()
    content_decrypted = serializers.SerializerMethodField()
    ai_analysis = serializers.SerializerMethodField()
    delivery_timeline = serializers.SerializerMethodField()
    related_messages = serializers.SerializerMethodField()
    
    class Meta:
        model = Message
        fields = [
            'id', 'external_message_id', 'message_type', 'direction',
            'sender_type', 'sender_id', 'sender_name', 'content_decrypted',
            'content_hash', 'raw_content', 'attachments', 'ai_processed',
            'ai_intent', 'ai_entities', 'ai_sentiment', 'ai_confidence',
            'delivery_status', 'is_deleted', 'deleted_at', 'platform_timestamp',
            'processed_at', 'sender_details', 'conversation_details',
            'read_status_details', 'ai_analysis', 'delivery_timeline',
            'related_messages', 'created_at'
        ]
    
    def get_sender_details(self, obj):
        """Get comprehensive sender information"""
        # Reuse the logic from MessageListSerializer but with more detail
        sender_info = MessageListSerializer.get_sender_details(self, obj)
        
        # Add additional details for specific sender types
        if obj.sender_type == 'customer' and obj.sender_id:
            try:
                from .models import Customer
                customer = Customer.objects.get(id=obj.sender_id)
                sender_info.update({
                    'email': customer.email_encrypted,
                    'phone': customer.phone_encrypted,
                    'tags': customer.tags,
                    'last_seen_at': customer.last_seen_at,
                    'status': customer.status
                })
            except Customer.DoesNotExist:
                pass
        
        return sender_info
    
    def get_conversation_details(self, obj):
        """Get conversation context"""
        conversation = obj.conversation
        return {
            'id': conversation.id,
            'subject': conversation.subject,
            'status': conversation.status,
            'current_handler_type': conversation.current_handler_type,
            'ai_enabled': conversation.ai_enabled,
            'priority': conversation.priority
        }
    
    def get_read_status_details(self, obj):
        """Get comprehensive read status information"""
        read_statuses = MessageReadStatus.objects.filter(
            message_id=obj.id
        ).select_related('user').order_by('read_at')
        
        current_user_id = self.context.get('current_user_id')
        current_user_read = None
        
        read_by = []
        for status in read_statuses:
            read_info = {
                'user_id': status.user_id,
                'user_name': f"{status.user.first_name} {status.user.last_name}".strip(),
                'user_email': status.user.email,
                'user_role': status.user.role,
                'read_at': status.read_at
            }
            read_by.append(read_info)
            
            if status.user_id == current_user_id:
                current_user_read = status.read_at
        
        return {
            'is_read_by_current_user': current_user_read is not None,
            'current_user_read_at': current_user_read,
            'total_readers': len(read_by),
            'read_by': read_by
        }
    
    def get_content_decrypted(self, obj):
        """Get decrypted message content"""
        return getattr(obj, 'content_decrypted', '') or ''
    
    def get_ai_analysis(self, obj):
        """Get AI processing results"""
        if obj.ai_processed:
            return {
                'processed': True,
                'intent': obj.ai_intent,
                'entities': obj.ai_entities,
                'sentiment': obj.ai_sentiment,
                'confidence': obj.ai_confidence,
                'processed_at': obj.processed_at
            }
        return {
            'processed': False,
            'reason': 'Message not processed by AI'
        }
    
    def get_delivery_timeline(self, obj):
        """Get message delivery timeline"""
        timeline = []
        
        if obj.created_at:
            timeline.append({
                'event': 'message_created',
                'timestamp': obj.created_at,
                'description': 'Message created in system'
            })
        
        if obj.platform_timestamp:
            timeline.append({
                'event': 'platform_received',
                'timestamp': obj.platform_timestamp,
                'description': 'Message received from platform'
            })
        
        if obj.processed_at:
            timeline.append({
                'event': 'ai_processed',
                'timestamp': obj.processed_at,
                'description': 'Message processed by AI'
            })
        
        # Add delivery status events
        if obj.delivery_status:
            timeline.append({
                'event': 'delivery_status',
                'timestamp': obj.created_at,  # This would be more accurate with actual delivery timestamps
                'description': f'Delivery status: {obj.delivery_status}'
            })
        
        return sorted(timeline, key=lambda x: x['timestamp'])
    
    def get_related_messages(self, obj):
        """Get related messages in the conversation (previous and next)"""
        conversation = obj.conversation
        
        # Get previous message
        previous_message = Message.objects.filter(
            conversation=conversation,
            created_at__lt=obj.created_at
        ).order_by('-created_at').first()
        
        # Get next message
        next_message = Message.objects.filter(
            conversation=conversation,
            created_at__gt=obj.created_at
        ).order_by('created_at').first()
        
        result = {}
        
        if previous_message:
            result['previous'] = {
                'id': previous_message.id,
                'sender_type': previous_message.sender_type,
                'sender_name': previous_message.sender_name,
                'content_preview': (getattr(previous_message, 'content_decrypted', '') or '')[:50] + '...',
                'created_at': previous_message.created_at
            }
        
        if next_message:
            result['next'] = {
                'id': next_message.id,
                'sender_type': next_message.sender_type,
                'sender_name': next_message.sender_name,
                'content_preview': (getattr(next_message, 'content_decrypted', '') or '')[:50] + '...',
                'created_at': next_message.created_at
            }
        
        return result


class MessageCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new messages"""
    content = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=4000,
        help_text="Message content"
    )
    message_type = serializers.CharField(
        default='text',
        help_text="Type of message (text, image, file, etc.)"
    )
    attachments = serializers.JSONField(
        required=False,
        default=list,
        help_text="Message attachments"
    )
    
    class Meta:
        model = Message
        fields = [
            'content', 'message_type', 'attachments'
        ]
    
    def validate_content(self, value):
        """Validate message content"""
        if not value or not value.strip():
            raise serializers.ValidationError("Message content cannot be empty.")
        
        # Check for maximum length
        if len(value) > 4000:
            raise serializers.ValidationError("Message content is too long (maximum 4000 characters).")
        
        return value.strip()
    
    def validate_message_type(self, value):
        """Validate message type"""
        valid_types = ['text', 'image', 'file', 'audio', 'video', 'location', 'contact']
        if value not in valid_types:
            raise serializers.ValidationError(f"Invalid message type. Valid types: {', '.join(valid_types)}")
        
        return value
    
    def validate_attachments(self, value):
        """Validate attachments format"""
        if value:
            if not isinstance(value, list):
                raise serializers.ValidationError("Attachments must be a list.")
            
            for attachment in value:
                if not isinstance(attachment, dict):
                    raise serializers.ValidationError("Each attachment must be an object.")
                
                required_fields = ['type', 'url']
                for field in required_fields:
                    if field not in attachment:
                        raise serializers.ValidationError(f"Attachment missing required field: {field}")
        
        return value or []
    
    def validate(self, data):
        """Cross-field validation"""
        message_type = data.get('message_type')
        attachments = data.get('attachments', [])
        content = data.get('content', '')
        
        # If message type is not text, ensure there are attachments or special content
        if message_type != 'text' and not attachments and not content:
            raise serializers.ValidationError(
                f"Messages of type '{message_type}' must have either content or attachments."
            )
        
        return data


class MessageReadStatusSerializer(serializers.Serializer):
    """Serializer for marking messages as read"""
    read_at = serializers.DateTimeField(
        required=False,
        help_text="When the message was read (defaults to current time)"
    )
    
    def validate_read_at(self, value):
        """Validate read timestamp"""
        if value and value > timezone.now():
            raise serializers.ValidationError("Read timestamp cannot be in the future.")
        
        return value or timezone.now()