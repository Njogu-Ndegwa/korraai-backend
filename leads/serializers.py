# serializers.py
from rest_framework import serializers
from .models import Lead, LeadCategory, LeadStage
from customers.models import Customer
from platforms.models import SocialPlatform
from tenants.models import TenantUser

class LeadStageListSerializer(serializers.ModelSerializer):
    """Serializer for listing lead stages"""
    leads_count = serializers.SerializerMethodField()
    
    class Meta:
        model = LeadStage
        fields = [
            'id', 'name', 'display_name', 'stage_order',
            'conversion_probability', 'is_active', 'leads_count',
            'created_at'
        ]
    
    def get_leads_count(self, obj):
        """Get count of leads in this stage"""
        return obj.leads.filter(status='active').count()


class LeadStageDetailSerializer(serializers.ModelSerializer):
    """Serializer for lead stage details"""
    leads_count = serializers.SerializerMethodField()
    active_leads_count = serializers.SerializerMethodField()
    conversion_rate = serializers.SerializerMethodField()
    
    class Meta:
        model = LeadStage
        fields = [
            'id', 'name', 'display_name', 'stage_order',
            'conversion_probability', 'is_active', 'leads_count',
            'active_leads_count', 'conversion_rate', 'created_at'
        ]
    
    def get_leads_count(self, obj):
        """Get total count of leads in this stage"""
        return obj.leads.count()
    
    def get_active_leads_count(self, obj):
        """Get count of active leads in this stage"""
        return obj.leads.filter(status='active').count()
    
    def get_conversion_rate(self, obj):
        """Calculate actual conversion rate for this stage"""
        total_leads = obj.leads.count()
        if total_leads == 0:
            return 0.0
        
        converted_leads = obj.leads.filter(status='converted').count()
        return round((converted_leads / total_leads) * 100, 2)


class LeadStageCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating lead stages"""
    
    class Meta:
        model = LeadStage
        fields = [
            'name', 'display_name', 'stage_order',
            'conversion_probability', 'is_active'
        ]
    
    def validate_name(self, value):
        """Validate stage name uniqueness within tenant"""
        tenant_id = self.context.get('tenant_id')
        instance = getattr(self, 'instance', None)
        
        queryset = LeadStage.objects.filter(
            tenant_id=tenant_id,
            name=value
        )
        
        if instance:
            queryset = queryset.exclude(id=instance.id)
        
        if queryset.exists():
            raise serializers.ValidationError("Lead stage with this name already exists.")
        
        return value
    
    def validate_stage_order(self, value):
        """Validate stage order is positive"""
        if value < 1:
            raise serializers.ValidationError("Stage order must be greater than 0.")
        return value
    
    def validate_conversion_probability(self, value):
        """Validate conversion probability is between 0 and 100"""
        if not (0 <= value <= 100):
            raise serializers.ValidationError("Conversion probability must be between 0 and 100.")
        return value
    
    def validate(self, data):
        """Custom validation for lead stage data"""
        tenant_id = self.context.get('tenant_id')
        instance = getattr(self, 'instance', None)
        stage_order = data.get('stage_order')
        
        if stage_order:
            # Check if stage_order already exists for this tenant
            queryset = LeadStage.objects.filter(
                tenant_id=tenant_id,
                stage_order=stage_order
            )
            
            if instance:
                queryset = queryset.exclude(id=instance.id)
            
            if queryset.exists():
                raise serializers.ValidationError({
                    'stage_order': 'A lead stage with this order already exists.'
                })
        
        return data


class LeadCategoryListSerializer(serializers.ModelSerializer):
    """Serializer for listing lead categories"""
    leads_count = serializers.SerializerMethodField()
    active_leads_count = serializers.SerializerMethodField()
    
    class Meta:
        model = LeadCategory
        fields = [
            'id', 'name', 'display_name', 'description', 'color_code',
            'priority_score', 'is_system_defined', 'is_active',
            'leads_count', 'active_leads_count', 'created_at'
        ]
    
    def get_leads_count(self, obj):
        """Get total count of leads in this category"""
        return obj.leads.count()
    
    def get_active_leads_count(self, obj):
        """Get count of active leads in this category"""
        return obj.leads.filter(status='active').count()


class LeadCategoryDetailSerializer(serializers.ModelSerializer):
    """Serializer for lead category details"""
    leads_count = serializers.SerializerMethodField()
    active_leads_count = serializers.SerializerMethodField()
    converted_leads_count = serializers.SerializerMethodField()
    conversion_rate = serializers.SerializerMethodField()
    total_estimated_value = serializers.SerializerMethodField()
    auto_assignment_rules_count = serializers.SerializerMethodField()
    
    class Meta:
        model = LeadCategory
        fields = [
            'id', 'name', 'display_name', 'description', 'color_code',
            'priority_score', 'auto_assignment_rules', 'is_system_defined',
            'is_active', 'leads_count', 'active_leads_count',
            'converted_leads_count', 'conversion_rate', 'total_estimated_value',
            'auto_assignment_rules_count', 'created_at'
        ]
    
    def get_leads_count(self, obj):
        """Get total count of leads in this category"""
        return obj.leads.count()
    
    def get_active_leads_count(self, obj):
        """Get count of active leads in this category"""
        return obj.leads.filter(status='active').count()
    
    def get_converted_leads_count(self, obj):
        """Get count of converted leads in this category"""
        return obj.leads.filter(status='converted').count()
    
    def get_conversion_rate(self, obj):
        """Calculate conversion rate for this category"""
        total_leads = obj.leads.count()
        if total_leads == 0:
            return 0.0
        
        converted_leads = obj.leads.filter(status='converted').count()
        return round((converted_leads / total_leads) * 100, 2)
    
    def get_total_estimated_value(self, obj):
        """Get total estimated value of all leads in this category"""
        from django.db.models import Sum
        result = obj.leads.filter(status='active').aggregate(
            total=Sum('estimated_value')
        )
        return float(result['total'] or 0)
    
    def get_auto_assignment_rules_count(self, obj):
        """Get count of auto assignment rules"""
        if obj.auto_assignment_rules:
            return len(obj.auto_assignment_rules)
        return 0


class LeadCategoryCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating lead categories"""
    
    class Meta:
        model = LeadCategory
        fields = [
            'name', 'display_name', 'description', 'color_code',
            'priority_score', 'auto_assignment_rules', 'is_active'
        ]
    
    def validate_name(self, value):
        """Validate category name uniqueness within tenant"""
        tenant_id = self.context.get('tenant_id')
        instance = getattr(self, 'instance', None)
        
        queryset = LeadCategory.objects.filter(
            tenant_id=tenant_id,
            name=value
        )
        
        if instance:
            queryset = queryset.exclude(id=instance.id)
        
        if queryset.exists():
            raise serializers.ValidationError("Lead category with this name already exists.")
        
        return value
    
    def validate_color_code(self, value):
        """Validate color code format"""
        import re
        if value and not re.match(r'^#[0-9A-Fa-f]{6}$', value):
            raise serializers.ValidationError("Color code must be in format #RRGGBB")
        return value
    
    def validate_priority_score(self, value):
        """Validate priority score is within reasonable range"""
        if value is not None and not (0 <= value <= 100):
            raise serializers.ValidationError("Priority score must be between 0 and 100.")
        return value
    
    def validate_auto_assignment_rules(self, value):
        """Validate auto assignment rules structure"""
        if value:
            # Basic validation for JSON structure
            if not isinstance(value, dict):
                raise serializers.ValidationError("Auto assignment rules must be a valid JSON object.")
            
            # You can add more specific validation based on your rules structure
            valid_keys = ['keywords', 'platforms', 'users', 'conditions']
            for key in value.keys():
                if key not in valid_keys:
                    raise serializers.ValidationError(f"Invalid auto assignment rule key: {key}")
        
        return value
    
    def validate(self, data):
        """Custom validation for lead category data"""
        # Ensure display_name is set if not provided
        if not data.get('display_name') and data.get('name'):
            data['display_name'] = data['name'].title()
        
        return data


class LeadListSerializer(serializers.ModelSerializer):
    """Serializer for listing leads with basic info"""
    customer_name = serializers.SerializerMethodField()
    customer_email = serializers.CharField(source='customer.email_encrypted', read_only=True)
    category_name = serializers.CharField(source='lead_category.display_name', read_only=True)
    category_color = serializers.CharField(source='lead_category.color_code', read_only=True)
    stage_name = serializers.CharField(source='lead_stage.display_name', read_only=True)
    stage_order = serializers.IntegerField(source='lead_stage.stage_order', read_only=True)
    assigned_user_name = serializers.SerializerMethodField()
    platform_name = serializers.CharField(source='source_platform.display_name', read_only=True)
    days_since_created = serializers.SerializerMethodField()
    
    class Meta:
        model = Lead
        fields = [
            'id', 'title', 'description', 'estimated_value', 'probability',
            'expected_close_date', 'source_campaign', 'source_medium',
            'ai_confidence_score', 'status', 'last_activity_at',
            'customer_name', 'customer_email', 'category_name', 'category_color',
            'stage_name', 'stage_order', 'assigned_user_name', 'platform_name',
            'days_since_created', 'created_at', 'updated_at'
        ]
    
    def get_customer_name(self, obj):
        """Get customer's full name"""
        if obj.customer:
            # Assuming encrypted fields are decrypted in the model's properties
            first_name = getattr(obj.customer, 'first_name_decrypted', '') or ''
            last_name = getattr(obj.customer, 'last_name_decrypted', '') or ''
            return f"{first_name} {last_name}".strip() or obj.customer.platform_display_name
        return None
    
    def get_assigned_user_name(self, obj):
        """Get assigned user's full name"""
        if obj.assigned_user_id:
            try:
                user = TenantUser.objects.get(id=obj.assigned_user_id)
                return f"{user.first_name} {user.last_name}".strip()
            except TenantUser.DoesNotExist:
                return None
        return None
    
    def get_days_since_created(self, obj):
        """Calculate days since lead was created"""
        from django.utils import timezone
        delta = timezone.now().date() - obj.created_at.date()
        return delta.days


class LeadDetailSerializer(serializers.ModelSerializer):
    """Serializer for lead details with full information"""
    customer_details = serializers.SerializerMethodField()
    category_details = serializers.SerializerMethodField()
    stage_details = serializers.SerializerMethodField()
    assigned_user_details = serializers.SerializerMethodField()
    platform_details = serializers.SerializerMethodField()
    conversation_count = serializers.SerializerMethodField()
    days_in_current_stage = serializers.SerializerMethodField()
    conversion_probability_stage = serializers.DecimalField(
        source='lead_stage.conversion_probability', 
        max_digits=5, 
        decimal_places=2, 
        read_only=True
    )
    
    class Meta:
        model = Lead
        fields = [
            'id', 'title', 'description', 'estimated_value', 'probability',
            'expected_close_date', 'source_campaign', 'source_medium',
            'ai_confidence_score', 'ai_classification_reason', 'last_ai_update',
            'status', 'last_activity_at', 'customer_details', 'category_details',
            'stage_details', 'assigned_user_details', 'platform_details',
            'conversation_count', 'days_in_current_stage', 'conversion_probability_stage',
            'created_at', 'updated_at'
        ]
    
    def get_customer_details(self, obj):
        """Get customer information"""
        if obj.customer:
            return {
                'id': obj.customer.id,
                'name': self.get_customer_name(obj),
                'email': obj.customer.email_encrypted,
                'platform_username': obj.customer.platform_username,
                'platform_display_name': obj.customer.platform_display_name,
                'engagement_score': obj.customer.engagement_score,
                'last_contact_at': obj.customer.last_contact_at
            }
        return None
    
    def get_customer_name(self, obj):
        """Get customer's full name"""
        if obj.customer:
            first_name = getattr(obj.customer, 'first_name_decrypted', '') or ''
            last_name = getattr(obj.customer, 'last_name_decrypted', '') or ''
            return f"{first_name} {last_name}".strip() or obj.customer.platform_display_name
        return None
    
    def get_category_details(self, obj):
        """Get lead category information"""
        if obj.lead_category:
            return {
                'id': obj.lead_category.id,
                'name': obj.lead_category.name,
                'display_name': obj.lead_category.display_name,
                'color_code': obj.lead_category.color_code,
                'priority_score': obj.lead_category.priority_score
            }
        return None
    
    def get_stage_details(self, obj):
        """Get lead stage information"""
        if obj.lead_stage:
            return {
                'id': obj.lead_stage.id,
                'name': obj.lead_stage.name,
                'display_name': obj.lead_stage.display_name,
                'stage_order': obj.lead_stage.stage_order,
                'conversion_probability': obj.lead_stage.conversion_probability
            }
        return None
    
    def get_assigned_user_details(self, obj):
        """Get assigned user information"""
        if obj.assigned_user_id:
            try:
                user = TenantUser.objects.get(id=obj.assigned_user_id)
                return {
                    'id': user.id,
                    'name': f"{user.first_name} {user.last_name}".strip(),
                    'email': user.email,
                    'role': user.role
                }
            except TenantUser.DoesNotExist:
                return None
        return None
    
    def get_platform_details(self, obj):
        """Get source platform information"""
        if obj.source_platform:
            return {
                'id': obj.source_platform.id,
                'name': obj.source_platform.name,
                'display_name': obj.source_platform.display_name
            }
        return None
    
    def get_conversation_count(self, obj):
        """Get count of conversations related to this lead"""
        return obj.conversations.count()
    
    def get_days_in_current_stage(self, obj):
        """Calculate days since lead entered current stage"""
        from django.utils import timezone
        # This would need to be tracked via stage change history
        # For now, using updated_at as approximation
        delta = timezone.now().date() - obj.updated_at.date()
        return delta.days


class LeadCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating leads"""
    
    class Meta:
        model = Lead
        fields = [
            'customer_id', 'lead_category_id', 'lead_stage_id', 'assigned_user_id',
            'title', 'description', 'estimated_value', 'probability',
            'expected_close_date', 'source_platform_id', 'source_campaign',
            'source_medium', 'status'
        ]
    
    def validate_customer_id(self, value):
        """Validate customer belongs to tenant"""
        tenant_id = self.context.get('tenant_id')
        if value:
            try:
                Customer.objects.get(id=value, tenant_id=tenant_id)
            except Customer.DoesNotExist:
                raise serializers.ValidationError("Customer not found or doesn't belong to your organization.")
        return value
    
    def validate_lead_category_id(self, value):
        """Validate lead category belongs to tenant and is active"""
        tenant_id = self.context.get('tenant_id')
        if value:
            try:
                category = LeadCategory.objects.get(id=value, tenant_id=tenant_id)
                if not category.is_active:
                    raise serializers.ValidationError("Selected lead category is not active.")
            except LeadCategory.DoesNotExist:
                raise serializers.ValidationError("Lead category not found or doesn't belong to your organization.")
        return value
    
    def validate_lead_stage_id(self, value):
        """Validate lead stage belongs to tenant and is active"""
        tenant_id = self.context.get('tenant_id')
        if value:
            try:
                stage = LeadStage.objects.get(id=value, tenant_id=tenant_id)
                if not stage.is_active:
                    raise serializers.ValidationError("Selected lead stage is not active.")
            except LeadStage.DoesNotExist:
                raise serializers.ValidationError("Lead stage not found or doesn't belong to your organization.")
        return value
    
    def validate_assigned_user_id(self, value):
        """Validate assigned user belongs to tenant"""
        tenant_id = self.context.get('tenant_id')
        if value:
            try:
                TenantUser.objects.get(id=value, tenant_id=tenant_id)
            except TenantUser.DoesNotExist:
                raise serializers.ValidationError("Assigned user not found or doesn't belong to your organization.")
        return value
    
    def validate_probability(self, value):
        """Validate probability is between 0 and 100"""
        if value is not None and not (0 <= value <= 100):
            raise serializers.ValidationError("Probability must be between 0 and 100.")
        return value
    
    def validate_estimated_value(self, value):
        """Validate estimated value is positive"""
        if value is not None and value < 0:
            raise serializers.ValidationError("Estimated value must be positive.")
        return value
    
    def validate(self, data):
        """Custom validation for lead data"""
        # Set default status if not provided
        if 'status' not in data:
            data['status'] = 'active'
        
        return data


class LeadStageUpdateSerializer(serializers.Serializer):
    """Serializer for updating lead stage"""
    lead_stage_id = serializers.UUIDField(required=True)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
    
    def validate_lead_stage_id(self, value):
        """Validate lead stage belongs to tenant and is active"""
        tenant_id = self.context.get('tenant_id')
        try:
            stage = LeadStage.objects.get(id=value, tenant_id=tenant_id)
            if not stage.is_active:
                raise serializers.ValidationError("Selected lead stage is not active.")
            return value
        except LeadStage.DoesNotExist:
            raise serializers.ValidationError("Lead stage not found or doesn't belong to your organization.")

