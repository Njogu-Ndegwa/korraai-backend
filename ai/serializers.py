# ai_settings/serializers.py
from rest_framework import serializers
from .models import TenantAISetting
from platforms.models import SocialPlatform

class TenantAISettingSerializer(serializers.ModelSerializer):
    platform_name = serializers.CharField(source='platform.name', read_only=True)
    
    class Meta:
        model = TenantAISetting
        fields = [
            'id', 'platform', 'platform_name', 'system_prompt',
            'auto_response_enabled', 'response_delay_seconds', 'confidence_threshold',
            'knowledge_base_enabled', 'max_knowledge_chunks', 'similarity_threshold',
            'business_hours', 'escalation_keywords', 'blocked_topics',
            'handover_triggers', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class TenantAISettingCreateSerializer(serializers.ModelSerializer):
    platform_id = serializers.UUIDField(write_only=True)
    
    class Meta:
        model = TenantAISetting
        fields = [
            'platform_id', 'system_prompt', 'auto_response_enabled',
            'response_delay_seconds', 'confidence_threshold', 'knowledge_base_enabled',
            'max_knowledge_chunks', 'similarity_threshold', 'business_hours',
            'escalation_keywords', 'blocked_topics', 'handover_triggers'
        ]
    
    def validate_platform_id(self, value):
        try:
            SocialPlatform.objects.get(id=value, is_active=True)
        except SocialPlatform.DoesNotExist:
            raise serializers.ValidationError("Invalid or inactive platform")
        return value
    
    def create(self, validated_data):
        tenant_id = self.context['tenant_id']
        platform_id = validated_data.pop('platform_id')
        return TenantAISetting.objects.create(
            tenant_id=tenant_id,
            platform_id=platform_id,
            **validated_data
        )