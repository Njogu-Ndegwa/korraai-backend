# tenants/serializers.py
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import Tenant, TenantUser
import uuid


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ['id', 'business_name', 'business_email', 'business_phone', 'subscription_tier', 'status', 'created_at']
        read_only_fields = ['id', 'created_at']


class TenantCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new tenant (business organization)"""
    class Meta:
        model = Tenant
        fields = [
            'business_name', 'business_email', 'business_phone', 
            'subscription_tier'
        ]
        extra_kwargs = {
            'business_name': {'required': True},
            'business_email': {'required': True},
            'subscription_tier': {'default': 'basic'},
        }

    def validate_business_email(self, value):
        if Tenant.objects.filter(business_email=value).exists():
            raise serializers.ValidationError("A business with this email already exists")
        return value

    def create(self, validated_data):
        # Set default values for required fields
        validated_data['encryption_key_hash'] = str(uuid.uuid4())
        validated_data['status'] = 'active'
        return super().create(validated_data)


class TenantUserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for registering a new user to an EXISTING tenant"""
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    tenant_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = TenantUser
        fields = [
            'email', 'password', 'password_confirm', 'first_name', 'last_name',
            'tenant_id', 'role'
        ]
        extra_kwargs = {
            'email': {'required': True},
            'first_name': {'required': True},
            'last_name': {'required': True},
            'role': {'default': 'user'},
        }

    def validate(self, attrs):
        # Check password confirmation
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        
        # Validate password strength
        try:
            validate_password(attrs['password'])
        except ValidationError as e:
            raise serializers.ValidationError({'password': list(e.messages)})
        
        # Check if tenant exists
        tenant_id = attrs['tenant_id']
        try:
            tenant = Tenant.objects.get(id=tenant_id, status='active')
            attrs['tenant'] = tenant
        except Tenant.DoesNotExist:
            raise serializers.ValidationError({'tenant_id': 'Invalid or inactive tenant'})
        
        # Check if user email already exists in this tenant
        if TenantUser.objects.filter(tenant=tenant, email=attrs['email']).exists():
            raise serializers.ValidationError({
                'email': 'A user with this email already exists in this tenant'
            })
        
        return attrs

    def create(self, validated_data):
        # Remove password confirmation and tenant_id
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        tenant = validated_data.pop('tenant')
        validated_data.pop('tenant_id')
        
        # Create user
        user = TenantUser.objects.create(
            tenant=tenant,
            **validated_data
        )
        user.set_password(password)
        user.save()
        
        return user


class TenantOwnerRegistrationSerializer(serializers.Serializer):
    """
    Serializer for creating a new tenant AND its first admin user in one step
    This is for the initial business registration
    """
    # Tenant fields
    business_name = serializers.CharField(max_length=255)
    business_email = serializers.EmailField()
    business_phone = serializers.CharField(max_length=50, required=False, allow_blank=True)
    subscription_tier = serializers.CharField(max_length=50, default='basic')
    
    # User fields
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)

    def validate(self, attrs):
        # Check password confirmation
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        
        # Validate password strength
        try:
            validate_password(attrs['password'])
        except ValidationError as e:
            raise serializers.ValidationError({'password': list(e.messages)})
        
        # Check if tenant email already exists
        if Tenant.objects.filter(business_email=attrs['business_email']).exists():
            raise serializers.ValidationError({
                'business_email': 'A business with this email already exists'
            })
        
        return attrs

    def create(self, validated_data):
        # Extract user data
        user_data = {
            'email': validated_data.pop('email'),
            'first_name': validated_data.pop('first_name'),
            'last_name': validated_data.pop('last_name'),
        }
        password = validated_data.pop('password')
        validated_data.pop('password_confirm')
        
        # Create tenant first
        validated_data['encryption_key_hash'] = str(uuid.uuid4())
        validated_data['status'] = 'active'
        tenant = Tenant.objects.create(**validated_data)
        
        # Create admin user for the tenant
        user = TenantUser.objects.create(
            tenant=tenant,
            role='admin',  # First user is always admin
            **user_data
        )
        user.set_password(password)
        user.save()
        
        return user


class TenantUserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    tenant_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        tenant_id = attrs.get('tenant_id')

        if not email or not password:
            raise serializers.ValidationError('Email and password are required')

        # Build query
        user_query = TenantUser.objects.filter(email=email, is_active=True)
        
        if tenant_id:
            user_query = user_query.filter(tenant_id=tenant_id)
        
        try:
            user = user_query.get()
        except TenantUser.DoesNotExist:
            raise serializers.ValidationError('Invalid credentials')
        except TenantUser.MultipleObjectsReturned:
            # If multiple users with same email exist across tenants
            raise serializers.ValidationError('Multiple accounts found. Please specify tenant_id')

        if not user.check_password(password):
            raise serializers.ValidationError('Invalid credentials')

        if user.tenant.status != 'active':
            raise serializers.ValidationError('Account is suspended')

        attrs['user'] = user
        return attrs


class TenantUserDetailSerializer(serializers.ModelSerializer):
    tenant = TenantSerializer(read_only=True)
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = TenantUser
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'permissions', 'is_active', 'last_login', 
            'created_at', 'tenant'
        ]
        read_only_fields = ['id', 'created_at', 'last_login']


class TenantUserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantUser
        fields = ['first_name', 'last_name', 'role', 'permissions']

    def validate_role(self, value):
        # Add role validation logic here
        valid_roles = ['admin', 'manager', 'agent', 'user']
        if value not in valid_roles:
            raise serializers.ValidationError(f'Role must be one of: {", ".join(valid_roles)}')
        return value


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError("New passwords don't match")
        
        try:
            validate_password(attrs['new_password'])
        except ValidationError as e:
            raise serializers.ValidationError({'new_password': list(e.messages)})
        
        return attrs

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect')
        return value


class TenantListSerializer(serializers.ModelSerializer):
    """Serializer for listing tenants (admin use)"""
    users_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Tenant
        fields = [
            'id', 'business_name', 'business_email', 'business_phone',
            'subscription_tier', 'status', 'users_count', 'created_at', 'updated_at'
        ]