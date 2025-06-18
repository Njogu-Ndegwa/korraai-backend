# customers/models.py
import uuid
from django.db import models
from django.contrib.postgres.fields import ArrayField
from tenants.models import Tenant
from platforms.models import SocialPlatform, TenantPlatformAccount


class Customer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='customers')
    external_id = models.CharField(max_length=255)
    platform = models.ForeignKey(SocialPlatform, on_delete=models.CASCADE, related_name='customers')
    platform_account = models.ForeignKey(TenantPlatformAccount, on_delete=models.CASCADE, related_name='customers')
    first_name_encrypted = models.TextField(blank=True)
    last_name_encrypted = models.TextField(blank=True)
    email_encrypted = models.TextField(blank=True)
    phone_encrypted = models.TextField(blank=True)
    profile_picture_url = models.URLField(blank=True)
    platform_username = models.CharField(max_length=255, blank=True)
    platform_display_name = models.CharField(max_length=255, blank=True)
    platform_profile_data = models.JSONField(default=dict)
    tags = ArrayField(models.CharField(max_length=50), default=list, blank=True)
    custom_fields = models.JSONField(default=dict)
    acquisition_source = models.CharField(max_length=100, blank=True)
    customer_lifetime_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    first_contact_at = models.DateTimeField(null=True, blank=True)
    last_contact_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'customers'
        unique_together = ['tenant', 'platform', 'external_id']

    def __str__(self):
        return f"{self.platform_display_name or self.platform_username} ({self.platform.name})"