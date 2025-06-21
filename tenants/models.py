# tenants/models.py
import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
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


class TenantUserManager(BaseUserManager):
    """Custom user manager for TenantUser"""
    
    def create_user(self, email, tenant, password=None, **extra_fields):
        """Create and return a regular user"""
        if not email:
            raise ValueError('The Email field must be set')
        if not tenant:
            raise ValueError('The Tenant field must be set')
        
        email = self.normalize_email(email)
        user = self.model(email=email, tenant=tenant, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and return a superuser"""
        # For superuser, create a special system tenant or use existing one
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        extra_fields.setdefault('first_name', 'Super')
        extra_fields.setdefault('last_name', 'Admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        # Get or create a system tenant for superuser
        system_tenant, created = Tenant.objects.get_or_create(
            business_email='system@admin.com',
            defaults={
                'business_name': 'System Administration',
                'business_phone': '',
                'subscription_tier': 'unlimited',
                'encryption_key_hash': str(uuid.uuid4()),
                'status': 'active'
            }
        )

        return self.create_user(email, system_tenant, password, **extra_fields)


class TenantUser(AbstractBaseUser):
    """Custom user model that integrates with Django's auth system"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='users')
    email = models.EmailField(unique=True)  # Must be globally unique for Django auth
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    role = models.CharField(max_length=50, default='user')
    permissions = models.JSONField(default=dict)  # Your custom permissions
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # Required for Django admin access
    is_superuser = models.BooleanField(default=False)  # Add this manually
    created_at = models.DateTimeField(auto_now_add=True)
    
    objects = TenantUserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    
    class Meta:
        db_table = 'tenant_users'
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    @property
    def is_admin(self):
        return self.role == 'admin'
    
    @property
    def is_tenant_staff(self):
        """Check if user has staff-level access in their tenant"""
        return self.role in ['admin', 'manager']
    
    def has_perm(self, perm, obj=None):
        """Required for Django admin - implement your custom logic"""
        if self.is_superuser:
            return True
        # Add your custom permission logic here
        return self.is_admin
    
    def has_module_perms(self, app_label):
        """Required for Django admin"""
        if self.is_superuser:
            return True
        return self.is_admin
    
    def save(self, *args, **kwargs):
        # Automatically set is_staff for admin users
        if self.role == 'admin':
            self.is_staff = True
        super().save(*args, **kwargs)


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