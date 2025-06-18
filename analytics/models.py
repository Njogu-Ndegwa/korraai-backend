# analytics/models.py
import uuid
from django.db import models
from tenants.models import Tenant
from platforms.models import SocialPlatform
from conversations.models import Conversation


class ConversationMetrics(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='conversation_metrics')
    conversation = models.OneToOneField(Conversation, on_delete=models.CASCADE, related_name='metrics')
    first_response_time_seconds = models.IntegerField(null=True, blank=True)
    average_response_time_seconds = models.IntegerField(null=True, blank=True)
    resolution_time_seconds = models.IntegerField(null=True, blank=True)
    total_messages = models.IntegerField(default=0)
    customer_messages = models.IntegerField(default=0)
    agent_messages = models.IntegerField(default=0)
    ai_messages = models.IntegerField(default=0)
    handover_count = models.IntegerField(default=0)
    ai_handling_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    customer_satisfaction_score = models.IntegerField(null=True, blank=True)  # 1-5 scale
    resolution_status = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'conversation_metrics'
        verbose_name_plural = 'Conversation Metrics'

    def __str__(self):
        return f"{self.tenant.business_name} - Conversation {self.conversation.id}"


class DailyAnalytics(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='daily_analytics')
    platform = models.ForeignKey(SocialPlatform, on_delete=models.CASCADE, related_name='daily_analytics')
    analytics_date = models.DateField()
    total_conversations = models.IntegerField(default=0)
    new_conversations = models.IntegerField(default=0)
    resolved_conversations = models.IntegerField(default=0)
    total_messages = models.IntegerField(default=0)
    new_leads = models.IntegerField(default=0)
    qualified_leads = models.IntegerField(default=0)
    converted_leads = models.IntegerField(default=0)
    ai_handled_conversations = models.IntegerField(default=0)
    ai_tokens_used = models.IntegerField(default=0)
    ai_accuracy_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    avg_first_response_time_seconds = models.IntegerField(null=True, blank=True)
    avg_resolution_time_seconds = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'daily_analytics'
        unique_together = ['tenant', 'platform', 'analytics_date']
        verbose_name_plural = 'Daily Analytics'

    def __str__(self):
        return f"{self.tenant.business_name} - {self.platform.name} - {self.analytics_date}"