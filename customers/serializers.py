# serializers.py
from rest_framework import serializers
from .models import Customer, ContactInsights, Conversation, Message, SocialPlatform, TenantPlatformAccount


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
        model = ContactInsights
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
    
    class Meta:
        model = Customer
        fields = [
            'external_id', 'platform_id', 'platform_account_id',
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
        return data


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
