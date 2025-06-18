# platforms/models.py
import uuid
from django.db import models
from tenants.models import Tenant


class SocialPlatform(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=100)
    api_version = models.CharField(max_length=20)
    webhook_config = models.JSONField(default=dict)
    rate_limits = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'social_platforms'

    def __str__(self):
        return self.display_name


class TenantPlatformAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='platform_accounts')
    platform = models.ForeignKey(SocialPlatform, on_delete=models.CASCADE, related_name='tenant_accounts')
    account_name = models.CharField(max_length=255)
    platform_account_id = models.CharField(max_length=255)
    access_token_encrypted = models.TextField()
    refresh_token_encrypted = models.TextField(blank=True)
    webhook_secret_encrypted = models.TextField(blank=True)
    account_settings = models.JSONField(default=dict)
    connection_status = models.CharField(max_length=20)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tenant_platform_accounts'
        unique_together = ['tenant', 'platform', 'platform_account_id']

    def __str__(self):
        return f"{self.tenant.business_name} - {self.platform.name} - {self.account_name}"