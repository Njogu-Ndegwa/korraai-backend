# platforms/serializers.py
from rest_framework import serializers
from .models import SocialPlatform, TenantPlatformAccount
from tenants.models import Tenant
import json


class SocialPlatformSerializer(serializers.ModelSerializer):
    """Serializer for social media platforms"""
    
    class Meta:
        model = SocialPlatform
        fields = [
            'id', 'name', 'display_name', 'api_version', 
            'webhook_config', 'rate_limits', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class SocialPlatformDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for platform with connection requirements"""
    connection_requirements = serializers.SerializerMethodField()
    supported_features = serializers.SerializerMethodField()
    
    class Meta:
        model = SocialPlatform
        fields = [
            'id', 'name', 'display_name', 'api_version', 
            'webhook_config', 'rate_limits', 'is_active', 
            'connection_requirements', 'supported_features', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_connection_requirements(self, obj):
        """Return platform-specific connection requirements"""
        requirements_map = {
            'facebook': {
                'required_fields': ['app_id', 'app_secret', 'page_id', 'access_token'],
                'scopes': ['pages_messaging', 'pages_read_engagement'],
                'webhook_fields': ['messages', 'messaging_postbacks', 'messaging_optins']
            },
            'whatsapp': {
                'required_fields': ['phone_number_id', 'access_token', 'webhook_verify_token'],
                'scopes': ['whatsapp_business_messaging'],
                'webhook_fields': ['messages', 'message_status']
            },
            'instagram': {
                'required_fields': ['instagram_account_id', 'access_token'],
                'scopes': ['instagram_basic', 'instagram_messaging'],
                'webhook_fields': ['messages', 'messaging_postbacks']
            },
            'telegram': {
                'required_fields': ['bot_token', 'webhook_url'],
                'scopes': [],
                'webhook_fields': ['message', 'callback_query']
            },
            'tiktok': {
                'required_fields': ['app_id', 'app_secret', 'access_token'],
                'scopes': ['user.info.basic', 'video.list'],
                'webhook_fields': ['comments', 'mentions']
            }
        }
        return requirements_map.get(obj.name, {})
    
    def get_supported_features(self, obj):
        """Return platform-specific supported features"""
        features_map = {
            'facebook': ['messaging', 'comments', 'posts', 'stories'],
            'whatsapp': ['messaging', 'media_sharing', 'templates'],
            'instagram': ['messaging', 'comments', 'stories'],
            'telegram': ['messaging', 'inline_keyboards', 'media_sharing'],
            'tiktok': ['comments', 'mentions', 'direct_messages']
        }
        return features_map.get(obj.name, [])


class TenantPlatformAccountSerializer(serializers.ModelSerializer):
    """Serializer for tenant platform accounts"""
    platform_name = serializers.CharField(source='platform.display_name', read_only=True)
    platform_icon = serializers.SerializerMethodField()
    
    class Meta:
        model = TenantPlatformAccount
        fields = [
            'id', 'platform', 'platform_name', 'platform_icon', 'account_name',
            'platform_account_id', 'account_settings', 'connection_status',
            'last_sync', 'created_at'
        ]
        read_only_fields = [
            'id', 'platform_name', 'platform_icon', 'connection_status', 
            'last_sync', 'created_at'
        ]
        extra_kwargs = {
            'access_token_encrypted': {'write_only': True},
            'refresh_token_encrypted': {'write_only': True},
            'webhook_secret_encrypted': {'write_only': True}
        }
    
    def get_platform_icon(self, obj):
        """Return platform icon URL or identifier"""
        icon_map = {
            'facebook': 'facebook-icon.svg',
            'whatsapp': 'whatsapp-icon.svg',
            'instagram': 'instagram-icon.svg',
            'telegram': 'telegram-icon.svg',
            'tiktok': 'tiktok-icon.svg'
        }
        return icon_map.get(obj.platform.name, 'default-platform-icon.svg')


class TenantPlatformAccountCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new platform account connections"""
    platform_credentials = serializers.JSONField(write_only=True)
    
    class Meta:
        model = TenantPlatformAccount
        fields = [
            'platform', 'account_name', 'platform_account_id',
            'platform_credentials', 'account_settings'
        ]
        extra_kwargs = {
            'account_settings': {'default': dict}
        }
    
    def validate_platform_credentials(self, value):
        """Validate platform-specific credentials"""
        platform_id = self.initial_data.get('platform')
        if not platform_id:
            raise serializers.ValidationError("Platform is required")
        
        try:
            platform = SocialPlatform.objects.get(id=platform_id)
        except SocialPlatform.DoesNotExist:
            raise serializers.ValidationError("Invalid platform")
        
        # Platform-specific validation
        required_fields = {
            'facebook': ['app_id', 'app_secret', 'page_id', 'access_token'],
            'whatsapp': ['phone_number_id', 'access_token', 'webhook_verify_token'],
            'instagram': ['instagram_account_id', 'access_token'],
            'telegram': ['bot_token'],
            'tiktok': ['app_id', 'app_secret', 'access_token']
        }
        
        required = required_fields.get(platform.name, [])
        missing_fields = [field for field in required if field not in value]
        
        if missing_fields:
            raise serializers.ValidationError(
                f"Missing required fields for {platform.display_name}: {', '.join(missing_fields)}"
            )
        
        return value
    
    def create(self, validated_data):
        tenant = self.context['request'].user.tenant
        platform_credentials = validated_data.pop('platform_credentials')
        
        # TODO: Encrypt credentials before storing
        account = TenantPlatformAccount.objects.create(
            tenant=tenant,
            access_token_encrypted=platform_credentials.get('access_token', ''),
            refresh_token_encrypted=platform_credentials.get('refresh_token', ''),
            webhook_secret_encrypted=platform_credentials.get('webhook_verify_token', ''),
            connection_status='pending',
            **validated_data
        )
        
        return account


class TenantPlatformAccountUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating platform account settings"""
    update_credentials = serializers.JSONField(write_only=True, required=False)
    
    class Meta:
        model = TenantPlatformAccount
        fields = [
            'account_name', 'account_settings', 'update_credentials'
        ]
    
    def update(self, instance, validated_data):
        update_credentials = validated_data.pop('update_credentials', None)
        
        if update_credentials:
            # TODO: Encrypt and update credentials
            if 'access_token' in update_credentials:
                instance.access_token_encrypted = update_credentials['access_token']
            if 'refresh_token' in update_credentials:
                instance.refresh_token_encrypted = update_credentials['refresh_token']
            if 'webhook_verify_token' in update_credentials:
                instance.webhook_secret_encrypted = update_credentials['webhook_verify_token']
        
        return super().update(instance, validated_data)


class ConnectionTestSerializer(serializers.Serializer):
    """Serializer for connection test results"""
    success = serializers.BooleanField()
    message = serializers.CharField()
    details = serializers.JSONField(required=False)
    last_tested = serializers.DateTimeField(read_only=True)


class SyncStatusSerializer(serializers.Serializer):
    """Serializer for sync operation status"""
    sync_started = serializers.BooleanField()
    message = serializers.CharField()
    sync_id = serializers.CharField(required=False)
    estimated_duration = serializers.IntegerField(required=False, help_text="Estimated duration in seconds")


class WebhookVerificationSerializer(serializers.Serializer):
    """Serializer for webhook verification"""
    challenge = serializers.CharField(required=False)
    verify_token = serializers.CharField(required=False)
    mode = serializers.CharField(required=False)
    
    def validate(self, attrs):
        # Facebook/WhatsApp webhook verification
        if 'challenge' in attrs and 'verify_token' in attrs:
            # TODO: Validate verify_token against stored token
            pass
        return attrs


class WebhookPayloadSerializer(serializers.Serializer):
    """Base serializer for webhook payloads"""
    object = serializers.CharField(required=False)
    entry = serializers.ListField(required=False)
    
    def validate(self, attrs):
        # Basic webhook payload validation
        # Platform-specific validation will be handled in views
        return attrs


class FacebookWebhookSerializer(WebhookPayloadSerializer):
    """Serializer for Facebook webhook payloads"""
    pass


class WhatsAppWebhookSerializer(WebhookPayloadSerializer):
    """Serializer for WhatsApp webhook payloads"""
    pass


class InstagramWebhookSerializer(WebhookPayloadSerializer):
    """Serializer for Instagram webhook payloads"""
    pass


class TelegramWebhookSerializer(serializers.Serializer):
    """Serializer for Telegram webhook payloads"""
    update_id = serializers.IntegerField()
    message = serializers.JSONField(required=False)
    edited_message = serializers.JSONField(required=False)
    callback_query = serializers.JSONField(required=False)


class TikTokWebhookSerializer(serializers.Serializer):
    """Serializer for TikTok webhook payloads"""
    event = serializers.CharField()
    timestamp = serializers.IntegerField()
    data = serializers.JSONField()