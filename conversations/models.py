# conversations/models.py
import uuid
from django.db import models
from tenants.models import Tenant, TenantUser
from customers.models import Customer
from platforms.models import SocialPlatform, TenantPlatformAccount
from leads.models import Lead


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='conversations')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='conversations')
    platform = models.ForeignKey(SocialPlatform, on_delete=models.CASCADE, related_name='conversations')
    platform_account = models.ForeignKey(TenantPlatformAccount, on_delete=models.CASCADE, related_name='conversations')
    lead = models.ForeignKey(Lead, on_delete=models.SET_NULL, null=True, blank=True, related_name='conversations')
    external_conversation_id = models.CharField(max_length=255)
    conversation_type = models.CharField(max_length=50)
    subject = models.CharField(max_length=500, blank=True)
    current_handler_type = models.CharField(max_length=10)  # AI, HUMAN
    assigned_user = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_conversations')
    ai_enabled = models.BooleanField(default=True)
    ai_paused_by_user = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_paused_conversations')
    ai_paused_at = models.DateTimeField(null=True, blank=True)
    ai_pause_reason = models.CharField(max_length=255, blank=True)
    can_ai_resume = models.BooleanField(default=True)
    handover_reason = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=50)
    priority = models.CharField(max_length=20)
    sentiment_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    first_message_at = models.DateTimeField(null=True, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    last_human_response_at = models.DateTimeField(null=True, blank=True)
    last_ai_response_at = models.DateTimeField(null=True, blank=True)
    response_due_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'conversations'
        unique_together = ['tenant', 'platform', 'external_conversation_id']

    def __str__(self):
        return f"{self.customer} - {self.platform.name} - {self.conversation_type}"


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='messages')
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    external_message_id = models.CharField(max_length=255)
    message_type = models.CharField(max_length=50)
    direction = models.CharField(max_length=20)  # INBOUND, OUTBOUND
    sender_type = models.CharField(max_length=20)  # CUSTOMER, AGENT, AI
    sender_id = models.UUIDField(null=True, blank=True)  # Could reference customer or user
    sender_name = models.CharField(max_length=255, blank=True)
    content_encrypted = models.TextField()
    content_hash = models.CharField(max_length=64)
    raw_content = models.JSONField(default=dict)
    attachments = models.JSONField(default=list)
    ai_processed = models.BooleanField(default=False)
    ai_intent = models.CharField(max_length=100, blank=True)
    ai_entities = models.JSONField(default=dict)
    ai_sentiment = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ai_confidence = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    delivery_status = models.CharField(max_length=50, blank=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    platform_timestamp = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'messages'
        unique_together = ['tenant', 'conversation', 'external_message_id']

    def __str__(self):
        return f"{self.sender_name} - {self.message_type} - {self.created_at}"


# Add this to your conversations/models.py file

class MessageReadStatus(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='message_read_statuses')
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='read_statuses')
    user = models.ForeignKey(TenantUser, on_delete=models.CASCADE, related_name='message_read_statuses')
    read_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'message_read_status'
        unique_together = ['message', 'user']
        indexes = [
            models.Index(fields=['tenant', 'user', 'read_at']),
            models.Index(fields=['message', 'user']),
        ]

    def __str__(self):
        return f"{self.user.email} read message {self.message.id} at {self.read_at}"