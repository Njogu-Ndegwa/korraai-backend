from rest_framework import serializers
from django.core.validators import RegexValidator
from .models import SocialPlatform, TenantPlatformAccount
from django.core.validators import URLValidator
from django.utils import timezone

class SocialPlatformSerializer(serializers.ModelSerializer):
    """Main serializer for Social Platform model"""
    
    webhook_config = serializers.JSONField(default=dict)
    rate_limits = serializers.JSONField(default=dict)
    
    class Meta:
        model = SocialPlatform
        fields = [
            'id',
            'name',
            'display_name',
            'api_version',
            'webhook_config',
            'rate_limits',
            'is_active',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def validate_name(self, value):
        """Validate platform name format"""
        if not value:
            raise serializers.ValidationError("Platform name is required")
        
        # Platform name should be lowercase, alphanumeric with underscores
        if not value.replace('_', '').replace('-', '').isalnum():
            raise serializers.ValidationError(
                "Platform name should contain only letters, numbers, hyphens, and underscores"
            )
        
        return value.lower()
    
    def validate_webhook_config(self, value):
        """Validate webhook configuration structure"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Webhook config must be a valid JSON object")
        
        # Expected webhook config structure
        expected_fields = ['endpoint_url', 'supported_events', 'retry_policy', 'security']
        
        # Validate webhook endpoint URL if provided
        if 'endpoint_url' in value and value['endpoint_url']:
            endpoint = value['endpoint_url']
            if not (endpoint.startswith('http://') or endpoint.startswith('https://')):
                raise serializers.ValidationError("Webhook endpoint must be a valid HTTP/HTTPS URL")
        
        # Validate supported events
        if 'supported_events' in value:
            if not isinstance(value['supported_events'], list):
                raise serializers.ValidationError("Supported events must be a list")
        
        return value
    
    def validate_rate_limits(self, value):
        """Validate rate limits configuration"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Rate limits must be a valid JSON object")
        
        # Expected rate limits structure
        valid_keys = [
            'requests_per_minute',
            'requests_per_hour', 
            'requests_per_day',
            'burst_limit',
            'concurrent_connections'
        ]
        
        for key, limit in value.items():
            if key not in valid_keys:
                raise serializers.ValidationError(f"Invalid rate limit key: {key}")
            
            if not isinstance(limit, int) or limit < 0:
                raise serializers.ValidationError(f"Rate limit values must be positive integers: {key}")
        
        return value


class SocialPlatformCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new social platforms"""
    
    name = serializers.CharField(
        max_length=50,
        validators=[
            RegexValidator(
                regex=r'^[a-zA-Z0-9_-]+$',
                message="Platform name can only contain letters, numbers, hyphens, and underscores"
            )
        ]
    )
    webhook_config = serializers.JSONField(default=dict)
    rate_limits = serializers.JSONField(default=dict)
    
    class Meta:
        model = SocialPlatform
        fields = [
            'name',
            'display_name',
            'api_version',
            'webhook_config',
            'rate_limits',
            'is_active'
        ]
    
    def validate_name(self, value):
        """Validate platform name uniqueness and format"""
        name = value.lower()
        
        # Check if platform with this name already exists
        if SocialPlatform.objects.filter(name=name).exists():
            raise serializers.ValidationError("A platform with this name already exists")
        
        return name
    
    def validate(self, attrs):
        """Cross-field validation"""
        # Set default webhook config if not provided
        if not attrs.get('webhook_config'):
            attrs['webhook_config'] = {
                'endpoint_url': '',
                'supported_events': [],
                'retry_policy': {
                    'max_retries': 3,
                    'retry_delay_seconds': 60
                },
                'security': {
                    'verify_ssl': True,
                    'signature_validation': True
                }
            }
        
        # Set default rate limits if not provided
        if not attrs.get('rate_limits'):
            attrs['rate_limits'] = {
                'requests_per_minute': 100,
                'requests_per_hour': 1000,
                'requests_per_day': 10000,
                'burst_limit': 200,
                'concurrent_connections': 50
            }
        
        return attrs


class SocialPlatformUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating social platforms"""
    
    name = serializers.CharField(read_only=True)  # Don't allow name changes
    webhook_config = serializers.JSONField()
    rate_limits = serializers.JSONField()
    
    class Meta:
        model = SocialPlatform
        fields = [
            'name',
            'display_name',
            'api_version',
            'webhook_config',
            'rate_limits',
            'is_active'
        ]
        read_only_fields = ['name']
    
    def validate_webhook_config(self, value):
        """Validate webhook configuration updates"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Webhook config must be a valid JSON object")
        
        # Ensure critical fields are present
        required_fields = ['endpoint_url', 'supported_events']
        for field in required_fields:
            if field not in value:
                raise serializers.ValidationError(f"Required webhook config field missing: {field}")
        
        return value


class SocialPlatformListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing platforms"""
    
    connected_accounts_count = serializers.SerializerMethodField()
    
    class Meta:
        model = SocialPlatform
        fields = [
            'id',
            'name',
            'display_name',
            'api_version',
            'is_active',
            'connected_accounts_count',
            'created_at'
        ]
    
    def get_connected_accounts_count(self, obj):
        """Get count of tenant accounts connected to this platform"""
        # This would be filtered by tenant in the view if needed
        return getattr(obj, 'connected_accounts_count', 0)


class SocialPlatformDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for single platform view"""
    
    connected_accounts_count = serializers.SerializerMethodField()
    latest_api_version = serializers.SerializerMethodField()
    
    class Meta:
        model = SocialPlatform
        fields = [
            'id',
            'name',
            'display_name',
            'api_version',
            'latest_api_version',
            'webhook_config',
            'rate_limits',
            'is_active',
            'connected_accounts_count',
            'created_at'
        ]
    
    def get_connected_accounts_count(self, obj):
        """Get count of accounts connected to this platform"""
        return obj.tenant_accounts.filter(connection_status='active').count()
    
    def get_latest_api_version(self, obj):
        """Get the latest API version for this platform"""
        # This could be fetched from a mapping or external service
        api_versions = {
            'facebook': 'v18.0',
            'instagram': 'v18.0',
            'whatsapp': 'v18.0',
            'twitter': 'v2.0',
            'linkedin': 'v2.0'
        }
        return api_versions.get(obj.name, obj.api_version)



class TenantPlatformAccountSerializer(serializers.ModelSerializer):
    """Main serializer for Tenant Platform Account model"""
    
    platform_name = serializers.CharField(source='platform.name', read_only=True)
    platform_display_name = serializers.CharField(source='platform.display_name', read_only=True)
    platform_api_version = serializers.CharField(source='platform.api_version', read_only=True)
    account_settings = serializers.JSONField(default=dict)
    days_since_last_sync = serializers.SerializerMethodField()
    
    class Meta:
        model = TenantPlatformAccount
        fields = [
            'id',
            'platform',
            'platform_name',
            'platform_display_name',
            'platform_api_version',
            'account_name',
            'platform_account_id',
            'account_settings',
            'connection_status',
            'last_sync',
            'days_since_last_sync',
            'created_at'
        ]
        read_only_fields = [
            'id',
            'platform_name',
            'platform_display_name',
            'platform_api_version',
            'days_since_last_sync',
            'created_at'
        ]
    
    def get_days_since_last_sync(self, obj):
        """Calculate days since last sync"""
        if obj.last_sync:
            return (timezone.now() - obj.last_sync).days
        return None


class TenantPlatformAccountListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing platform accounts"""
    
    platform_name = serializers.CharField(source='platform.name', read_only=True)
    platform_display_name = serializers.CharField(source='platform.display_name', read_only=True)
    is_token_valid = serializers.SerializerMethodField()
    last_activity = serializers.SerializerMethodField()
    
    class Meta:
        model = TenantPlatformAccount
        fields = [
            'id',
            'platform',
            'platform_name',
            'platform_display_name',
            'account_name',
            'platform_account_id',
            'connection_status',
            'is_token_valid',
            'last_sync',
            'last_activity',
            'created_at'
        ]
    
    def get_is_token_valid(self, obj):
        """Check if tokens are likely valid based on connection status"""
        return obj.connection_status == 'active'
    
    def get_last_activity(self, obj):
        """Get last meaningful activity timestamp"""
        return obj.last_sync or obj.created_at


class TenantPlatformAccountCreateSerializer(serializers.ModelSerializer):
    """Serializer for connecting new platform accounts"""
    
    platform_id = serializers.UUIDField(write_only=True)
    access_token = serializers.CharField(write_only=True, max_length=1000)
    refresh_token = serializers.CharField(write_only=True, max_length=1000, required=False, allow_blank=True)
    webhook_secret = serializers.CharField(write_only=True, max_length=500, required=False, allow_blank=True)
    account_settings = serializers.JSONField(default=dict)
    
    class Meta:
        model = TenantPlatformAccount
        fields = [
            'platform_id',
            'account_name',
            'platform_account_id',
            'access_token',
            'refresh_token',
            'webhook_secret',
            'account_settings',
            'connection_status'
        ]
    
    def validate_platform_id(self, value):
        """Validate that the platform exists and is active"""
        try:
            platform = SocialPlatform.objects.get(id=value, is_active=True)
        except SocialPlatform.DoesNotExist:
            raise serializers.ValidationError("Invalid or inactive platform")
        return value
    
    def validate_platform_account_id(self, value):
        """Validate platform account ID format"""
        if not value or not value.strip():
            raise serializers.ValidationError("Platform account ID is required")
        return value.strip()
    
    def validate_access_token(self, value):
        """Validate access token"""
        if not value or len(value.strip()) < 10:
            raise serializers.ValidationError("Valid access token is required")
        return value.strip()
    
    def validate_account_settings(self, value):
        """Validate account settings structure"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Account settings must be a valid JSON object")
        
        # Validate common settings fields
        if 'webhook_url' in value:
            url_validator = URLValidator()
            try:
                url_validator(value['webhook_url'])
            except:
                raise serializers.ValidationError("Invalid webhook URL in account settings")
        
        return value
    
    def validate(self, attrs):
        """Cross-field validation"""
        tenant_id = self.context['request'].user.tenant_id
        platform_id = attrs['platform_id']
        platform_account_id = attrs['platform_account_id']
        
        # Check if this platform account is already connected to this tenant
        existing_account = TenantPlatformAccount.objects.filter(
            tenant_id=tenant_id,
            platform_id=platform_id,
            platform_account_id=platform_account_id
        ).first()
        
        if existing_account:
            if existing_account.connection_status == 'active':
                raise serializers.ValidationError(
                    "This platform account is already connected and active"
                )
            elif existing_account.connection_status in ['disconnected', 'error']:
                # Allow reconnection of previously disconnected accounts
                attrs['_existing_account_id'] = existing_account.id
        
        return attrs
    
    def create(self, validated_data):
        """Create or update platform account connection"""
        tenant_id = self.context['request'].user.tenant_id
        platform_id = validated_data.pop('platform_id')
        access_token = validated_data.pop('access_token')
        refresh_token = validated_data.pop('refresh_token', '')
        webhook_secret = validated_data.pop('webhook_secret', '')
        existing_account_id = validated_data.pop('_existing_account_id', None)
        
        # Encrypt tokens (you'll need to implement encryption)
        validated_data.update({
            'tenant_id': tenant_id,
            'platform_id': platform_id,
            'access_token_encrypted': self._encrypt_token(access_token),
            'refresh_token_encrypted': self._encrypt_token(refresh_token) if refresh_token else '',
            'webhook_secret_encrypted': self._encrypt_token(webhook_secret) if webhook_secret else '',
            'connection_status': 'active',
            'last_sync': timezone.now()
        })
        
        if existing_account_id:
            # Update existing account
            TenantPlatformAccount.objects.filter(id=existing_account_id).update(**validated_data)
            return TenantPlatformAccount.objects.get(id=existing_account_id)
        else:
            # Create new account
            return TenantPlatformAccount.objects.create(**validated_data)
    
    def _encrypt_token(self, token):
        """Encrypt token - implement your encryption logic here"""
        # This is a placeholder - implement actual encryption
        import base64
        return base64.b64encode(token.encode()).decode() if token else ''


class TenantPlatformAccountUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating platform account settings"""
    
    account_settings = serializers.JSONField()
    
    class Meta:
        model = TenantPlatformAccount
        fields = [
            'account_name',
            'account_settings',
            'connection_status'
        ]
    
    def validate_account_settings(self, value):
        """Validate account settings updates"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Account settings must be a valid JSON object")
        
        # Validate webhook URL if present
        if 'webhook_url' in value and value['webhook_url']:
            url_validator = URLValidator()
            try:
                url_validator(value['webhook_url'])
            except:
                raise serializers.ValidationError("Invalid webhook URL in account settings")
        
        # Validate notification settings
        if 'notifications' in value:
            notifications = value['notifications']
            if not isinstance(notifications, dict):
                raise serializers.ValidationError("Notifications settings must be an object")
            
            valid_notification_types = ['messages', 'mentions', 'reactions', 'follows']
            for notif_type in notifications.keys():
                if notif_type not in valid_notification_types:
                    raise serializers.ValidationError(f"Invalid notification type: {notif_type}")
        
        # Validate sync settings
        if 'sync_frequency' in value:
            valid_frequencies = ['realtime', 'hourly', 'daily', 'manual']
            if value['sync_frequency'] not in valid_frequencies:
                raise serializers.ValidationError("Invalid sync frequency")
        
        return value
    
    def validate_connection_status(self, value):
        """Validate connection status transitions"""
        if value not in ['active', 'paused', 'disconnected']:
            raise serializers.ValidationError("Invalid connection status")
        return value


class TenantPlatformAccountDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for single platform account view"""
    
    platform_name = serializers.CharField(source='platform.name', read_only=True)
    platform_display_name = serializers.CharField(source='platform.display_name', read_only=True)
    platform_api_version = serializers.CharField(source='platform.api_version', read_only=True)
    platform_rate_limits = serializers.JSONField(source='platform.rate_limits', read_only=True)
    days_since_last_sync = serializers.SerializerMethodField()
    token_status = serializers.SerializerMethodField()
    usage_stats = serializers.SerializerMethodField()
    
    class Meta:
        model = TenantPlatformAccount
        fields = [
            'id',
            'platform',
            'platform_name',
            'platform_display_name',
            'platform_api_version',
            'platform_rate_limits',
            'account_name',
            'platform_account_id',
            'account_settings',
            'connection_status',
            'token_status',
            'last_sync',
            'days_since_last_sync',
            'usage_stats',
            'created_at'
        ]
    
    def get_days_since_last_sync(self, obj):
        """Calculate days since last sync"""
        if obj.last_sync:
            return (timezone.now() - obj.last_sync).days
        return None
    
    def get_token_status(self, obj):
        """Get token status information"""
        return {
            'has_access_token': bool(obj.access_token_encrypted),
            'has_refresh_token': bool(obj.refresh_token_encrypted),
            'has_webhook_secret': bool(obj.webhook_secret_encrypted),
            'connection_status': obj.connection_status,
            'last_validated': obj.last_sync
        }
    
    def get_usage_stats(self, obj):
        """Get usage statistics for this account"""
        # This would typically come from your analytics/usage tracking
        # Placeholder implementation
        return {
            'total_conversations': 0,
            'messages_this_month': 0,
            'api_calls_today': 0,
            'last_activity': obj.last_sync
        }