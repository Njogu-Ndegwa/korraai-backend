# tenants/models.py
import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import ArrayField


class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business_name = models.CharField(max_length=255)
    business_email = models.EmailField(unique=True)
    business_phone = models.CharField(max_length=50)
    subscription_tier = models.CharField(max_length=50)
    encryption_key_hash = models.CharField(max_length=255)
    status = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tenants'

    def __str__(self):
        return self.business_name


class TenantUser(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='users')
    email = models.EmailField()
    password_hash = models.CharField(max_length=255)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    role = models.CharField(max_length=50)
    permissions = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tenant_users'
        unique_together = ['tenant', 'email']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"


class SubscriptionPlan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan_name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=100)
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2)
    yearly_price = models.DecimalField(max_digits=10, decimal_places=2)
    max_conversations_per_month = models.IntegerField()
    max_ai_messages_per_month = models.IntegerField()
    max_platform_connections = models.IntegerField()
    max_users = models.IntegerField()
    features = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'subscription_plans'

    def __str__(self):
        return self.display_name


class TenantSubscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE)
    billing_cycle = models.CharField(max_length=20)
    status = models.CharField(max_length=50)
    current_period_start = models.DateField()
    current_period_end = models.DateField()
    trial_end = models.DateField(null=True, blank=True)
    next_billing_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tenant_subscriptions'

    def __str__(self):
        return f"{self.tenant.business_name} - {self.plan.plan_name}"


class UsageTracking(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='usage_tracking')
    tracking_month = models.DateField()
    conversations_count = models.IntegerField(default=0)
    ai_messages_count = models.IntegerField(default=0)
    platform_connections_count = models.IntegerField(default=0)
    users_count = models.IntegerField(default=0)
    overage_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'usage_tracking'
        unique_together = ['tenant', 'tracking_month']

    def __str__(self):
        return f"{self.tenant.business_name} - {self.tracking_month}"


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='audit_logs')
    user = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True)
    action_type = models.CharField(max_length=100)
    resource_type = models.CharField(max_length=100)
    resource_id = models.UUIDField()
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    session_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_logs'

    def __str__(self):
        return f"{self.action_type} on {self.resource_type} by {self.user}"