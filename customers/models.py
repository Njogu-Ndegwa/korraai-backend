# customers/models.py
import uuid
from django.db import models
from django.contrib.postgres.fields import ArrayField
from tenants.models import Tenant, TenantUser
from platforms.models import SocialPlatform, TenantPlatformAccount


class Customer(models.Model):
    STATUS_CHOICES = [
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('away', 'Away'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='customers')
    external_id = models.CharField(max_length=255)
    platform = models.ForeignKey(SocialPlatform, on_delete=models.CASCADE, related_name='customers')
    platform_account = models.ForeignKey(TenantPlatformAccount, on_delete=models.CASCADE, related_name='customers')
    
    # Personal Information (Encrypted)
    first_name_encrypted = models.TextField(blank=True)
    last_name_encrypted = models.TextField(blank=True)
    email_encrypted = models.TextField(blank=True)
    phone_encrypted = models.TextField(blank=True)
    
    # Platform Information
    profile_picture_url = models.URLField(blank=True)
    platform_username = models.CharField(max_length=255, blank=True)
    platform_display_name = models.CharField(max_length=255, blank=True)
    platform_profile_data = models.JSONField(default=dict)
    
    # CRM Fields
    tags = ArrayField(models.CharField(max_length=50), default=list, blank=True)
    custom_fields = models.JSONField(default=dict)
    acquisition_source = models.CharField(max_length=100, blank=True)
    customer_lifetime_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    first_contact_at = models.DateTimeField(null=True, blank=True)
    last_contact_at = models.DateTimeField(null=True, blank=True)
    
    # Contact/Messaging Features
    is_archived = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    pin_order = models.IntegerField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offline')
    is_typing = models.BooleanField(default=False)
    typing_in_conversation_id = models.UUIDField(null=True, blank=True)
    engagement_score = models.DecimalField(max_digits=3, decimal_places=1, default=0.0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'customers'
        unique_together = ['tenant', 'platform', 'external_id']
        indexes = [
            models.Index(fields=['tenant', 'is_archived', 'is_pinned']),
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'engagement_score']),
            models.Index(fields=['tenant', 'last_contact_at']),
            models.Index(fields=['pin_order'], condition=models.Q(is_pinned=True), name='customers_pinned_order_idx'),
        ]

    def __str__(self):
        return f"{self.platform_display_name or self.platform_username} ({self.platform.name})"

    @property
    def display_name(self):
        """Get the best available display name for the customer"""
        return (
            self.platform_display_name or 
            self.platform_username or 
            f"Customer {self.external_id[:8]}"
        )

    def pin(self, order=None):
        """Pin customer to top of contacts list"""
        if order is None:
            # Get the highest pin order and add 1
            max_order = Customer.objects.filter(
                tenant=self.tenant, 
                is_pinned=True
            ).aggregate(
                max_order=models.Max('pin_order')
            )['max_order'] or 0
            order = max_order + 1
        
        self.is_pinned = True
        self.pin_order = order
        self.save(update_fields=['is_pinned', 'pin_order'])

    def unpin(self):
        """Remove customer from pinned contacts"""
        self.is_pinned = False
        self.pin_order = None
        self.save(update_fields=['is_pinned', 'pin_order'])

    def archive(self):
        """Archive customer (hide from main contacts list)"""
        self.is_archived = True
        self.save(update_fields=['is_archived'])

    def unarchive(self):
        """Unarchive customer"""
        self.is_archived = False
        self.save(update_fields=['is_archived'])

    def update_status(self, status):
        """Update customer online status"""
        if status in dict(self.STATUS_CHOICES):
            self.status = status
            if status == 'online':
                self.last_seen_at = models.functions.Now()
            self.save(update_fields=['status', 'last_seen_at'])

    def set_typing(self, conversation_id=None, is_typing=True):
        """Set customer typing status"""
        self.is_typing = is_typing
        self.typing_in_conversation_id = conversation_id if is_typing else None
        self.save(update_fields=['is_typing', 'typing_in_conversation_id'])


class ContactLabel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='contact_labels')
    name = models.CharField(max_length=100)
    color_code = models.CharField(max_length=7, blank=True)  # Hex color code
    description = models.TextField(blank=True)
    is_system_defined = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contact_labels'
        unique_together = ['tenant', 'name']
        indexes = [
            models.Index(fields=['tenant', 'is_system_defined']),
        ]

    def __str__(self):
        return f"{self.name} ({self.tenant.business_name})"


class CustomerLabel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='customer_labels')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='labels')
    label = models.ForeignKey(ContactLabel, on_delete=models.CASCADE, related_name='customer_assignments')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'customer_labels'
        unique_together = ['customer', 'label']
        indexes = [
            models.Index(fields=['tenant', 'label']),
            models.Index(fields=['customer']),
        ]

    def __str__(self):
        return f"{self.customer.display_name} - {self.label.name}"


class ContactInsight(models.Model):
    SENTIMENT_CHOICES = [
        ('positive', 'Positive'),
        ('neutral', 'Neutral'),
        ('negative', 'Negative'),
    ]

    TREND_CHOICES = [
        ('increasing', 'Increasing'),
        ('stable', 'Stable'),
        ('decreasing', 'Decreasing'),
    ]

    DAY_CHOICES = [
        ('monday', 'Monday'),
        ('tuesday', 'Tuesday'),
        ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'),
        ('friday', 'Friday'),
        ('saturday', 'Saturday'),
        ('sunday', 'Sunday'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='contact_insights')
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name='insights')
    
    # Communication Statistics
    total_messages = models.IntegerField(default=0)
    messages_sent = models.IntegerField(default=0)  # Messages from customer
    messages_received = models.IntegerField(default=0)  # Messages to customer
    avg_response_time_seconds = models.IntegerField(null=True, blank=True)
    
    # Sentiment Analysis
    sentiment_trend = models.CharField(max_length=20, choices=SENTIMENT_CHOICES, default='neutral')
    
    # Behavioral Patterns
    preferred_contact_hours = models.JSONField(default=list)  # e.g., ["09:00-12:00", "14:00-17:00"]
    most_active_day = models.CharField(max_length=10, choices=DAY_CHOICES, blank=True)
    
    # Metadata
    last_engagement_score_update = models.DateTimeField(null=True, blank=True)
    insights_generated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contact_insights'
        indexes = [
            models.Index(fields=['tenant', 'sentiment_trend']),
            models.Index(fields=['tenant', 'most_active_day']),
            models.Index(fields=['insights_generated_at']),
        ]

    def __str__(self):
        return f"Insights for {self.customer.display_name}"

    def calculate_engagement_score(self):
        """Calculate engagement score based on various factors"""
        score = 0.0
        
        # Base score from message count (up to 3 points)
        if self.total_messages > 0:
            score += min(3.0, self.total_messages / 50)
        
        # Response time factor (up to 2 points)
        if self.avg_response_time_seconds:
            if self.avg_response_time_seconds <= 300:  # 5 minutes
                score += 2.0
            elif self.avg_response_time_seconds <= 1800:  # 30 minutes
                score += 1.5
            elif self.avg_response_time_seconds <= 3600:  # 1 hour
                score += 1.0
            else:
                score += 0.5
        
        # Sentiment factor (up to 2 points)
        sentiment_scores = {
            'positive': 2.0,
            'neutral': 1.0,
            'negative': 0.0
        }
        score += sentiment_scores.get(self.sentiment_trend, 1.0)
        
        # Recent activity factor (up to 3 points)
        if self.customer.last_contact_at:
            from django.utils import timezone
            from datetime import timedelta
            
            days_since_contact = (timezone.now() - self.customer.last_contact_at).days
            if days_since_contact <= 1:
                score += 3.0
            elif days_since_contact <= 7:
                score += 2.0
            elif days_since_contact <= 30:
                score += 1.0
            else:
                score += 0.0
        
        # Cap at 10.0
        return min(10.0, score)

    def update_engagement_score(self):
        """Update the customer's engagement score"""
        new_score = self.calculate_engagement_score()
        self.customer.engagement_score = new_score
        self.customer.save(update_fields=['engagement_score'])
        
        self.last_engagement_score_update = models.functions.Now()
        self.save(update_fields=['last_engagement_score_update'])
        
        return new_score