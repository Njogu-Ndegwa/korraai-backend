# leads/models.py
import uuid
from django.db import models
from tenants.models import Tenant, TenantUser
from customers.models import Customer
from platforms.models import SocialPlatform


class LeadCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='lead_categories')
    name = models.CharField(max_length=100)
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    color_code = models.CharField(max_length=7)  # Hex color code
    priority_score = models.IntegerField(default=0)
    auto_assignment_rules = models.JSONField(default=dict)
    is_system_defined = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'lead_categories'
        unique_together = ['tenant', 'name']
        verbose_name_plural = 'Lead Categories'

    def __str__(self):
        return f"{self.tenant.business_name} - {self.display_name}"


class LeadStage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='lead_stages')
    name = models.CharField(max_length=100)
    display_name = models.CharField(max_length=100)
    stage_order = models.IntegerField()
    conversion_probability = models.DecimalField(max_digits=5, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'lead_stages'
        unique_together = ['tenant', 'name']
        ordering = ['stage_order']

    def __str__(self):
        return f"{self.tenant.business_name} - {self.display_name}"


class Lead(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='leads')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='leads')
    lead_category = models.ForeignKey(LeadCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='leads')
    lead_stage = models.ForeignKey(LeadStage, on_delete=models.SET_NULL, null=True, blank=True, related_name='leads')
    assigned_user = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_leads')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    estimated_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    probability = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    expected_close_date = models.DateField(null=True, blank=True)
    source_platform = models.ForeignKey(SocialPlatform, on_delete=models.SET_NULL, null=True, blank=True, related_name='sourced_leads')
    source_campaign = models.CharField(max_length=255, blank=True)
    source_medium = models.CharField(max_length=100, blank=True)
    ai_confidence_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ai_classification_reason = models.TextField(blank=True)
    last_ai_update = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=50)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'leads'

    def __str__(self):
        return f"{self.title} - {self.customer}"