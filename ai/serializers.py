# serializers.py
from rest_framework import serializers
from .models import TenantAISettings, AIIntentCategory
from platforms.models import SocialPlatform, TenantPlatformAccount
from django.core.validators import MinValueValidator, MaxValueValidator
import json
from conversations.models import Message, Conversation
from django.db.models import Count, Avg, Q
from django.utils import timezone
from datetime import timedelta


class AISettingsListSerializer(serializers.ModelSerializer):
    """Serializer for listing AI settings across all platforms"""
    platform_name = serializers.CharField(source='platform.display_name', read_only=True)
    platform_icon = serializers.CharField(source='platform.name', read_only=True)
    is_active = serializers.BooleanField(source='platform.is_active', read_only=True)
    total_conversations = serializers.SerializerMethodField()
    ai_handled_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = TenantAISettings
        fields = [
            'id', 'platform_id', 'platform_name', 'platform_icon', 'is_active',
            'auto_response_enabled', 'response_delay_seconds', 'confidence_threshold',
            'knowledge_base_enabled', 'business_hours', 'total_conversations',
            'ai_handled_percentage', 'created_at', 'updated_at'
        ]
    
    def get_total_conversations(self, obj):
        """Get total conversations for this platform"""
        # This would typically come from analytics
        return getattr(obj, 'total_conversations', 0)
    
    def get_ai_handled_percentage(self, obj):
        """Get percentage of conversations handled by AI"""
        # This would typically come from analytics
        return getattr(obj, 'ai_handled_percentage', 0.0)


class AISettingsDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed AI settings view"""
    platform_details = serializers.SerializerMethodField()
    knowledge_base_stats = serializers.SerializerMethodField()
    performance_metrics = serializers.SerializerMethodField()
    recent_activity = serializers.SerializerMethodField()
    
    class Meta:
        model = TenantAISettings
        fields = [
            'id', 'platform_id', 'system_prompt', 'auto_response_enabled',
            'response_delay_seconds', 'confidence_threshold', 'knowledge_base_enabled',
            'max_knowledge_chunks', 'similarity_threshold', 'business_hours',
            'escalation_keywords', 'blocked_topics', 'handover_triggers',
            'platform_details', 'knowledge_base_stats', 'performance_metrics',
            'recent_activity', 'created_at', 'updated_at'
        ]
    
    def get_platform_details(self, obj):
        """Get platform information"""
        if obj.platform:
            return {
                'id': obj.platform.id,
                'name': obj.platform.name,
                'display_name': obj.platform.display_name,
                'api_version': obj.platform.api_version,
                'is_active': obj.platform.is_active,
                'rate_limits': obj.platform.rate_limits,
                'webhook_config': obj.platform.webhook_config
            }
        return None
    
    def get_knowledge_base_stats(self, obj):
        """Get knowledge base statistics"""
        if obj.knowledge_base_enabled:
            # This would typically come from actual knowledge base queries
            return {
                'total_documents': 0,  # Would be calculated from related documents
                'total_chunks': 0,
                'last_updated': None,
                'average_similarity_score': obj.similarity_threshold,
                'most_used_documents': []
            }
        return None
    
    def get_performance_metrics(self, obj):
        """Get AI performance metrics"""
        # This would typically come from analytics/metrics tables
        return {
            'total_messages_processed': 0,
            'average_confidence_score': 0.0,
            'successful_resolutions': 0,
            'handover_rate': 0.0,
            'customer_satisfaction': 0.0,
            'response_time_avg_seconds': obj.response_delay_seconds
        }
    
    def get_recent_activity(self, obj):
        """Get recent AI activity"""
        # This would typically come from AI usage logs
        return {
            'last_message_processed': None,
            'messages_today': 0,
            'errors_today': 0,
            'last_knowledge_retrieval': None
        }


class AISettingsUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating AI settings"""
    
    class Meta:
        model = TenantAISettings
        fields = [
            'system_prompt', 'auto_response_enabled', 'response_delay_seconds',
            'confidence_threshold', 'knowledge_base_enabled', 'max_knowledge_chunks',
            'similarity_threshold', 'business_hours', 'escalation_keywords',
            'blocked_topics', 'handover_triggers'
        ]
    
    def validate_system_prompt(self, value):
        """Validate system prompt"""
        if value and len(value) > 4000:
            raise serializers.ValidationError("System prompt cannot exceed 4000 characters.")
        
        if value and len(value.strip()) < 10:
            raise serializers.ValidationError("System prompt must be at least 10 characters long.")
        
        return value
    
    def validate_response_delay_seconds(self, value):
        """Validate response delay"""
        if value is not None:
            if value < 0:
                raise serializers.ValidationError("Response delay cannot be negative.")
            if value > 300:  # 5 minutes max
                raise serializers.ValidationError("Response delay cannot exceed 300 seconds.")
        
        return value
    
    def validate_confidence_threshold(self, value):
        """Validate confidence threshold"""
        if value is not None:
            if not (0.0 <= value <= 1.0):
                raise serializers.ValidationError("Confidence threshold must be between 0.0 and 1.0.")
        
        return value
    
    def validate_max_knowledge_chunks(self, value):
        """Validate max knowledge chunks"""
        if value is not None:
            if value < 1:
                raise serializers.ValidationError("Max knowledge chunks must be at least 1.")
            if value > 20:
                raise serializers.ValidationError("Max knowledge chunks cannot exceed 20.")
        
        return value
    
    def validate_similarity_threshold(self, value):
        """Validate similarity threshold"""
        if value is not None:
            if not (0.0 <= value <= 1.0):
                raise serializers.ValidationError("Similarity threshold must be between 0.0 and 1.0.")
        
        return value
    
    def validate_business_hours(self, value):
        """Validate business hours format"""
        if value:
            required_keys = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            
            if not isinstance(value, dict):
                raise serializers.ValidationError("Business hours must be an object.")
            
            for day in required_keys:
                if day not in value:
                    raise serializers.ValidationError(f"Missing business hours for {day}.")
                
                day_config = value[day]
                if not isinstance(day_config, dict):
                    raise serializers.ValidationError(f"Business hours for {day} must be an object.")
                
                if 'enabled' not in day_config:
                    raise serializers.ValidationError(f"Missing 'enabled' field for {day}.")
                
                if day_config.get('enabled') and ('start' not in day_config or 'end' not in day_config):
                    raise serializers.ValidationError(f"Missing start/end times for {day}.")
                
                # Validate time format (HH:MM)
                if day_config.get('enabled'):
                    import re
                    time_pattern = r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$'
                    
                    if not re.match(time_pattern, day_config.get('start', '')):
                        raise serializers.ValidationError(f"Invalid start time format for {day}. Use HH:MM format.")
                    
                    if not re.match(time_pattern, day_config.get('end', '')):
                        raise serializers.ValidationError(f"Invalid end time format for {day}. Use HH:MM format.")
        
        return value
    
    def validate_escalation_keywords(self, value):
        """Validate escalation keywords"""
        if value:
            if not isinstance(value, list):
                raise serializers.ValidationError("Escalation keywords must be a list.")
            
            for keyword in value:
                if not isinstance(keyword, str):
                    raise serializers.ValidationError("Each escalation keyword must be a string.")
                
                if len(keyword.strip()) < 2:
                    raise serializers.ValidationError("Escalation keywords must be at least 2 characters long.")
        
        return value or []
    
    def validate_blocked_topics(self, value):
        """Validate blocked topics"""
        if value:
            if not isinstance(value, list):
                raise serializers.ValidationError("Blocked topics must be a list.")
            
            for topic in value:
                if not isinstance(topic, str):
                    raise serializers.ValidationError("Each blocked topic must be a string.")
                
                if len(topic.strip()) < 2:
                    raise serializers.ValidationError("Blocked topics must be at least 2 characters long.")
        
        return value or []
    
    def validate_handover_triggers(self, value):
        """Validate handover triggers"""
        if value:
            if not isinstance(value, dict):
                raise serializers.ValidationError("Handover triggers must be an object.")
            
            valid_triggers = [
                'low_confidence', 'escalation_keywords', 'negative_sentiment',
                'multiple_questions', 'custom_rules'
            ]
            
            for trigger_type, config in value.items():
                if trigger_type not in valid_triggers:
                    raise serializers.ValidationError(f"Invalid handover trigger: {trigger_type}")
                
                if not isinstance(config, dict):
                    raise serializers.ValidationError(f"Handover trigger '{trigger_type}' must have an object configuration.")
                
                if 'enabled' not in config:
                    raise serializers.ValidationError(f"Missing 'enabled' field for handover trigger '{trigger_type}'.")
        
        return value or {}


class AISettingsTestSerializer(serializers.Serializer):
    """Serializer for testing AI configuration"""
    test_message = serializers.CharField(
        required=True,
        max_length=1000,
        help_text="Test message to process with AI"
    )
    include_knowledge_base = serializers.BooleanField(
        default=True,
        help_text="Whether to include knowledge base in test"
    )
    test_type = serializers.ChoiceField(
        choices=[
            ('intent_detection', 'Intent Detection'),
            ('sentiment_analysis', 'Sentiment Analysis'),
            ('knowledge_retrieval', 'Knowledge Retrieval'),
            ('full_response', 'Full Response Generation'),
        ],
        default='full_response',
        help_text="Type of AI test to perform"
    )
    platform_id = serializers.UUIDField(
        required=False,
        help_text="Platform ID for platform-specific testing"
    )
    
    def validate_test_message(self, value):
        """Validate test message"""
        if not value or not value.strip():
            raise serializers.ValidationError("Test message cannot be empty.")
        
        if len(value.strip()) < 5:
            raise serializers.ValidationError("Test message must be at least 5 characters long.")
        
        return value.strip()
    
    def validate_platform_id(self, value):
        """Validate platform exists if provided"""
        if value:
            tenant_id = self.context.get('tenant_id')
            try:
                SocialPlatform.objects.get(id=value)
                # Also check if tenant has settings for this platform
                TenantAISettings.objects.get(tenant_id=tenant_id, platform_id=value)
            except (SocialPlatform.DoesNotExist, TenantAISettings.DoesNotExist):
                raise serializers.ValidationError("Platform not found or no AI settings configured for this platform.")
        
        return value


class PlatformAISettingsSerializer(serializers.ModelSerializer):
    """Serializer specifically for platform-specific AI settings"""
    platform_name = serializers.CharField(source='platform.display_name', read_only=True)
    platform_capabilities = serializers.SerializerMethodField()
    connection_status = serializers.SerializerMethodField()
    
    class Meta:
        model = TenantAISettings
        fields = [
            'id', 'platform_id', 'platform_name', 'platform_capabilities',
            'connection_status', 'system_prompt', 'auto_response_enabled',
            'response_delay_seconds', 'confidence_threshold', 'knowledge_base_enabled',
            'max_knowledge_chunks', 'similarity_threshold', 'business_hours',
            'escalation_keywords', 'blocked_topics', 'handover_triggers',
            'created_at', 'updated_at'
        ]
    
    def get_platform_capabilities(self, obj):
        """Get platform-specific capabilities"""
        if obj.platform:
            return {
                'supports_images': True,  # Would be based on platform config
                'supports_files': True,
                'supports_reactions': False,
                'supports_threads': False,
                'max_message_length': 4000,
                'supported_media_types': ['image', 'document', 'audio']
            }
        return {}
    
    def get_connection_status(self, obj):
        """Get platform connection status"""
        # This would check the actual platform account connection
        try:
            account = TenantPlatformAccount.objects.get(
                tenant_id=obj.tenant_id,
                platform_id=obj.platform_id
            )
            return {
                'connected': account.connection_status == 'active',
                'status': account.connection_status,
                'last_sync': account.last_sync,
                'account_name': account.account_name
            }
        except TenantPlatformAccount.DoesNotExist:
            return {
                'connected': False,
                'status': 'not_connected',
                'last_sync': None,
                'account_name': None
            }


class IntentCategoryListSerializer(serializers.ModelSerializer):
    """Serializer for listing intent categories"""
    usage_count = serializers.SerializerMethodField()
    detection_rate = serializers.SerializerMethodField()
    avg_confidence = serializers.SerializerMethodField()
    last_detected = serializers.SerializerMethodField()
    has_auto_actions = serializers.SerializerMethodField()
    
    class Meta:
        model = AIIntentCategory
        fields = [
            'id', 'intent_key', 'display_name', 'description', 'color_code',
            'priority_score', 'is_system_defined', 'is_active', 'usage_count',
            'detection_rate', 'avg_confidence', 'last_detected', 'has_auto_actions',
            'created_at', 'updated_at'
        ]
    
    def get_usage_count(self, obj):
        """Get count of messages with this intent in last 30 days"""
        thirty_days_ago = timezone.now() - timedelta(days=30)
        return Message.objects.filter(
            tenant_id=obj.tenant_id,
            ai_intent=obj.intent_key,
            created_at__gte=thirty_days_ago
        ).count()
    
    def get_detection_rate(self, obj):
        """Get detection rate percentage in last 30 days"""
        thirty_days_ago = timezone.now() - timedelta(days=30)
        total_messages = Message.objects.filter(
            tenant_id=obj.tenant_id,
            ai_processed=True,
            created_at__gte=thirty_days_ago
        ).count()
        
        intent_messages = Message.objects.filter(
            tenant_id=obj.tenant_id,
            ai_intent=obj.intent_key,
            created_at__gte=thirty_days_ago
        ).count()
        
        if total_messages > 0:
            return round((intent_messages / total_messages) * 100, 2)
        return 0.0
    
    def get_avg_confidence(self, obj):
        """Get average confidence score for this intent"""
        thirty_days_ago = timezone.now() - timedelta(days=30)
        avg_confidence = Message.objects.filter(
            tenant_id=obj.tenant_id,
            ai_intent=obj.intent_key,
            created_at__gte=thirty_days_ago
        ).aggregate(avg=Avg('ai_confidence'))['avg']
        
        return round(avg_confidence, 3) if avg_confidence else 0.0
    
    def get_last_detected(self, obj):
        """Get timestamp of last detection"""
        last_message = Message.objects.filter(
            tenant_id=obj.tenant_id,
            ai_intent=obj.intent_key
        ).order_by('-created_at').first()
        
        return last_message.created_at if last_message else None
    
    def get_has_auto_actions(self, obj):
        """Check if intent has auto-actions configured"""
        return bool(obj.auto_actions and len(obj.auto_actions) > 0)


class IntentCategoryDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed intent category view"""
    usage_statistics = serializers.SerializerMethodField()
    performance_metrics = serializers.SerializerMethodField()
    recent_detections = serializers.SerializerMethodField()
    auto_actions_summary = serializers.SerializerMethodField()
    similar_intents = serializers.SerializerMethodField()
    
    class Meta:
        model = AIIntentCategory
        fields = [
            'id', 'intent_key', 'display_name', 'description', 'color_code',
            'priority_score', 'auto_actions', 'is_system_defined', 'is_active',
            'usage_statistics', 'performance_metrics', 'recent_detections',
            'auto_actions_summary', 'similar_intents', 'created_at', 'updated_at'
        ]
    
    def get_usage_statistics(self, obj):
        """Get comprehensive usage statistics"""
        thirty_days_ago = timezone.now() - timedelta(days=30)
        seven_days_ago = timezone.now() - timedelta(days=7)
        today = timezone.now().date()
        
        # Get usage over different periods
        usage_30d = Message.objects.filter(
            tenant_id=obj.tenant_id,
            ai_intent=obj.intent_key,
            created_at__gte=thirty_days_ago
        ).count()
        
        usage_7d = Message.objects.filter(
            tenant_id=obj.tenant_id,
            ai_intent=obj.intent_key,
            created_at__gte=seven_days_ago
        ).count()
        
        usage_today = Message.objects.filter(
            tenant_id=obj.tenant_id,
            ai_intent=obj.intent_key,
            created_at__date=today
        ).count()
        
        # Calculate trend
        prev_7d = Message.objects.filter(
            tenant_id=obj.tenant_id,
            ai_intent=obj.intent_key,
            created_at__gte=thirty_days_ago - timedelta(days=7),
            created_at__lt=seven_days_ago
        ).count()
        
        trend = 'stable'
        if usage_7d > prev_7d:
            trend = 'increasing'
        elif usage_7d < prev_7d:
            trend = 'decreasing'
        
        return {
            'last_30_days': usage_30d,
            'last_7_days': usage_7d,
            'today': usage_today,
            'trend': trend,
            'daily_average': round(usage_30d / 30, 1)
        }
    
    def get_performance_metrics(self, obj):
        """Get performance metrics for this intent"""
        thirty_days_ago = timezone.now() - timedelta(days=30)
        
        messages = Message.objects.filter(
            tenant_id=obj.tenant_id,
            ai_intent=obj.intent_key,
            created_at__gte=thirty_days_ago
        )
        
        if not messages.exists():
            return {
                'avg_confidence': 0.0,
                'min_confidence': 0.0,
                'max_confidence': 0.0,
                'confidence_distribution': {},
                'successful_resolutions': 0,
                'handover_rate': 0.0
            }
        
        confidences = list(messages.values_list('ai_confidence', flat=True))
        
        # Calculate confidence distribution
        distribution = {'high': 0, 'medium': 0, 'low': 0}
        for conf in confidences:
            if conf >= 0.8:
                distribution['high'] += 1
            elif conf >= 0.6:
                distribution['medium'] += 1
            else:
                distribution['low'] += 1
        
        # Calculate resolution metrics
        conversation_ids = messages.values_list('conversation_id', flat=True).distinct()
        resolved_conversations = Conversation.objects.filter(
            id__in=conversation_ids,
            status='resolved'
        ).count()
        
        handover_conversations = Conversation.objects.filter(
            id__in=conversation_ids,
            current_handler_type='human'
        ).count()
        
        total_conversations = len(set(conversation_ids))
        
        return {
            'avg_confidence': round(sum(confidences) / len(confidences), 3),
            'min_confidence': round(min(confidences), 3),
            'max_confidence': round(max(confidences), 3),
            'confidence_distribution': distribution,
            'successful_resolutions': resolved_conversations,
            'handover_rate': round((handover_conversations / total_conversations) * 100, 2) if total_conversations > 0 else 0.0,
            'total_conversations': total_conversations
        }
    
    def get_recent_detections(self, obj):
        """Get recent message detections for this intent"""
        recent_messages = Message.objects.filter(
            tenant_id=obj.tenant_id,
            ai_intent=obj.intent_key
        ).select_related('conversation', 'conversation__customer').order_by('-created_at')[:10]
        
        return [{
            'message_id': msg.id,
            'content_preview': (getattr(msg, 'content_decrypted', '') or '')[:100] + '...',
            'confidence': msg.ai_confidence,
            'conversation_id': msg.conversation_id,
            'customer_name': self._get_customer_name(msg.conversation.customer) if msg.conversation.customer else 'Unknown',
            'detected_at': msg.created_at,
            'platform': msg.conversation.platform.display_name if msg.conversation.platform else None
        } for msg in recent_messages]
    
    def get_auto_actions_summary(self, obj):
        """Get summary of configured auto-actions"""
        if not obj.auto_actions:
            return {
                'total_actions': 0,
                'enabled_actions': 0,
                'action_types': []
            }
        
        enabled_count = 0
        action_types = []
        
        for action_key, action_config in obj.auto_actions.items():
            action_types.append(action_key)
            if action_config.get('enabled', False):
                enabled_count += 1
        
        return {
            'total_actions': len(obj.auto_actions),
            'enabled_actions': enabled_count,
            'action_types': action_types
        }
    
    def get_similar_intents(self, obj):
        """Get similar intent categories"""
        # This would typically use ML similarity, for now using simple logic
        similar = AIIntentCategory.objects.filter(
            tenant_id=obj.tenant_id,
            is_active=True
        ).exclude(id=obj.id).order_by('display_name')[:5]
        
        return [{
            'id': intent.id,
            'intent_key': intent.intent_key,
            'display_name': intent.display_name,
            'similarity_score': 0.75  # Placeholder similarity score
        } for intent in similar]
    
    def _get_customer_name(self, customer):
        """Helper to get customer display name"""
        if not customer:
            return 'Unknown'
        
        first_name = getattr(customer, 'first_name_decrypted', '') or ''
        last_name = getattr(customer, 'last_name_decrypted', '') or ''
        full_name = f"{first_name} {last_name}".strip()
        return full_name or customer.platform_display_name or customer.platform_username


class IntentCategoryCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating intent categories"""
    
    class Meta:
        model = AIIntentCategory
        fields = [
            'intent_key', 'display_name', 'description', 'color_code',
            'priority_score', 'auto_actions', 'is_active'
        ]
    
    def validate_intent_key(self, value):
        """Validate intent key uniqueness and format"""
        if not value:
            raise serializers.ValidationError("Intent key is required.")
        
        # Check format (alphanumeric and underscores only)
        import re
        if not re.match(r'^[a-z0-9_]+$', value):
            raise serializers.ValidationError("Intent key must contain only lowercase letters, numbers, and underscores.")
        
        if len(value) < 3:
            raise serializers.ValidationError("Intent key must be at least 3 characters long.")
        
        if len(value) > 50:
            raise serializers.ValidationError("Intent key cannot exceed 50 characters.")
        
        # Check uniqueness within tenant
        tenant_id = self.context.get('tenant_id')
        instance = getattr(self, 'instance', None)
        
        queryset = AIIntentCategory.objects.filter(
            tenant_id=tenant_id,
            intent_key=value
        )
        
        if instance:
            queryset = queryset.exclude(id=instance.id)
        
        if queryset.exists():
            raise serializers.ValidationError("Intent key already exists.")
        
        return value
    
    def validate_display_name(self, value):
        """Validate display name"""
        if not value or not value.strip():
            raise serializers.ValidationError("Display name is required.")
        
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Display name must be at least 3 characters long.")
        
        if len(value) > 100:
            raise serializers.ValidationError("Display name cannot exceed 100 characters.")
        
        return value.strip()
    
    def validate_color_code(self, value):
        """Validate color code format"""
        if value:
            import re
            if not re.match(r'^#[0-9A-Fa-f]{6}$', value):
                raise serializers.ValidationError("Color code must be in format #RRGGBB")
        return value
    
    def validate_priority_score(self, value):
        """Validate priority score"""
        if value is not None:
            if not (0 <= value <= 100):
                raise serializers.ValidationError("Priority score must be between 0 and 100.")
        return value
    
    def validate_auto_actions(self, value):
        """Validate auto-actions configuration"""
        if value:
            if not isinstance(value, dict):
                raise serializers.ValidationError("Auto actions must be a valid JSON object.")
            
            valid_action_types = [
                'assign_agent', 'set_priority', 'add_tag', 'send_template',
                'create_lead', 'update_status', 'escalate', 'set_category'
            ]
            
            for action_key, action_config in value.items():
                if action_key not in valid_action_types:
                    raise serializers.ValidationError(f"Invalid auto action type: {action_key}")
                
                if not isinstance(action_config, dict):
                    raise serializers.ValidationError(f"Auto action '{action_key}' must have an object configuration.")
                
                if 'enabled' not in action_config:
                    raise serializers.ValidationError(f"Auto action '{action_key}' missing 'enabled' field.")
                
                # Validate specific action configurations
                if action_key == 'assign_agent' and action_config.get('enabled'):
                    if 'agent_id' not in action_config:
                        raise serializers.ValidationError("assign_agent action requires 'agent_id' field.")
                
                elif action_key == 'set_priority' and action_config.get('enabled'):
                    if 'priority' not in action_config:
                        raise serializers.ValidationError("set_priority action requires 'priority' field.")
                    
                    valid_priorities = ['low', 'medium', 'high', 'urgent']
                    if action_config['priority'] not in valid_priorities:
                        raise serializers.ValidationError(f"Invalid priority value. Must be one of: {valid_priorities}")
        
        return value or {}


class IntentAnalyticsSerializer(serializers.Serializer):
    """Serializer for intent analytics data"""
    def to_representation(self, data):
        """Custom representation for analytics data"""
        return data


class IntentAutoActionsSerializer(serializers.Serializer):
    """Serializer for configuring intent auto-actions"""
    auto_actions = serializers.JSONField(required=True)
    
    def validate_auto_actions(self, value):
        """Validate auto-actions configuration"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Auto actions must be a valid JSON object.")
        
        valid_action_types = [
            'assign_agent', 'set_priority', 'add_tag', 'send_template',
            'create_lead', 'update_status', 'escalate', 'set_category'
        ]
        
        for action_key, action_config in value.items():
            if action_key not in valid_action_types:
                raise serializers.ValidationError(f"Invalid auto action type: {action_key}")
            
            if not isinstance(action_config, dict):
                raise serializers.ValidationError(f"Auto action '{action_key}' must have an object configuration.")
            
            required_fields = ['enabled']
            for field in required_fields:
                if field not in action_config:
                    raise serializers.ValidationError(f"Auto action '{action_key}' missing required field: {field}")
            
            # Validate action-specific configurations
            if action_config.get('enabled'):
                if action_key == 'assign_agent':
                    if 'agent_id' not in action_config:
                        raise serializers.ValidationError(f"assign_agent action requires 'agent_id' field.")
                
                elif action_key == 'set_priority':
                    if 'priority' not in action_config:
                        raise serializers.ValidationError(f"set_priority action requires 'priority' field.")
                    
                    valid_priorities = ['low', 'medium', 'high', 'urgent']
                    if action_config['priority'] not in valid_priorities:
                        raise serializers.ValidationError(f"Invalid priority. Must be one of: {valid_priorities}")
                
                elif action_key == 'add_tag':
                    if 'tags' not in action_config or not action_config['tags']:
                        raise serializers.ValidationError(f"add_tag action requires 'tags' field with at least one tag.")
                
                elif action_key == 'send_template':
                    if 'template_id' not in action_config:
                        raise serializers.ValidationError(f"send_template action requires 'template_id' field.")
                
                elif action_key == 'create_lead':
                    required_lead_fields = ['category_id', 'stage_id']
                    for field in required_lead_fields:
                        if field not in action_config:
                            raise serializers.ValidationError(f"create_lead action requires '{field}' field.")
                
                elif action_key == 'set_category':
                    if 'category_id' not in action_config:
                        raise serializers.ValidationError(f"set_category action requires 'category_id' field.")
        
        return value