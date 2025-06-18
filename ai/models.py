# ai/models.py
import uuid
from django.db import models
from django.contrib.postgres.fields import ArrayField
from tenants.models import Tenant
from platforms.models import SocialPlatform
from conversations.models import Conversation, Message


class TenantAISetting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ai_settings')
    platform = models.ForeignKey(SocialPlatform, on_delete=models.CASCADE, related_name='ai_settings')
    system_prompt = models.TextField(blank=True)
    auto_response_enabled = models.BooleanField(default=True)
    response_delay_seconds = models.IntegerField(default=0)
    confidence_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=0.7)
    knowledge_base_enabled = models.BooleanField(default=True)
    max_knowledge_chunks = models.IntegerField(default=5)
    similarity_threshold = models.DecimalField(max_digits=5, decimal_places=4, default=0.7500)
    business_hours = models.JSONField(default=dict)
    escalation_keywords = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    blocked_topics = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    handover_triggers = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tenant_ai_settings'
        unique_together = ['tenant', 'platform']

    def __str__(self):
        return f"{self.tenant.business_name} - {self.platform.name} AI Settings"


class AIIntentCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ai_intent_categories')
    intent_key = models.CharField(max_length=50)
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    color_code = models.CharField(max_length=7)
    priority_score = models.IntegerField(default=0)
    auto_actions = models.JSONField(default=dict)
    is_system_defined = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_intent_categories'
        unique_together = ['tenant', 'intent_key']
        verbose_name_plural = 'AI Intent Categories'

    def __str__(self):
        return f"{self.tenant.business_name} - {self.display_name}"


class AISentimentRange(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ai_sentiment_ranges')
    range_key = models.CharField(max_length=50)
    display_name = models.CharField(max_length=100)
    min_value = models.DecimalField(max_digits=3, decimal_places=2)
    max_value = models.DecimalField(max_digits=3, decimal_places=2)
    color_code = models.CharField(max_length=7)
    alert_threshold = models.BooleanField(default=False)
    is_system_defined = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_sentiment_ranges'
        unique_together = ['tenant', 'range_key']

    def __str__(self):
        return f"{self.tenant.business_name} - {self.display_name}"


class AIUsageLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ai_usage_logs')
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='ai_usage_logs')
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='ai_usage_logs')
    usage_date = models.DateField()
    tokens_used = models.IntegerField()
    processing_time_ms = models.IntegerField()
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2)
    knowledge_chunks_used = models.IntegerField(default=0)
    handover_triggered = models.BooleanField(default=False)
    handover_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_usage_logs'

    def __str__(self):
        return f"{self.tenant.business_name} - {self.usage_date} - {self.tokens_used} tokens"