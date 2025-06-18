# tenants/serializers.py
from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import Tenant, TenantUser


class TenantRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for tenant registration"""
    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    user_email = serializers.EmailField()

    class Meta:
        model = Tenant
        fields = [
            'business_name', 'business_email', 'business_phone', 
            'subscription_tier', 'first_name', 'last_name', 
            'user_email', 'password', 'confirm_password'
        ]
        extra_kwargs = {
            'subscription_tier': {'required': False, 'default': 'free'},
        }

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError("Password and confirm password do not match.")
        
        # Check if business email is unique
        if Tenant.objects.filter(business_email=attrs['business_email']).exists():
            raise serializers.ValidationError("A tenant with this business email already exists.")
        
        return attrs

    def create(self, validated_data):
        # Remove non-tenant fields
        password = validated_data.pop('password')
        validated_data.pop('confirm_password')
        first_name = validated_data.pop('first_name')
        last_name = validated_data.pop('last_name')
        user_email = validated_data.pop('user_email')
        
        # Create tenant
        tenant = Tenant.objects.create(
            status='active',
            **validated_data
        )
        
        # Create admin user for tenant
        TenantUser.objects.create(
            tenant=tenant,
            email=user_email,
            first_name=first_name,
            last_name=last_name,
            role='admin',
            is_active=True,
            password_hash=password  # In production, hash this properly
        )
        
        return tenant


class LoginSerializer(serializers.Serializer):
    """Serializer for user login"""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            # Custom authentication logic for TenantUser
            try:
                user = TenantUser.objects.get(email=email, is_active=True)
                # In production, use proper password verification
                if user.password_hash == password:
                    attrs['user'] = user
                else:
                    raise serializers.ValidationError('Invalid credentials.')
            except TenantUser.DoesNotExist:
                raise serializers.ValidationError('Invalid credentials.')
        else:
            raise serializers.ValidationError('Email and password are required.')
        
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for password reset request"""
    email = serializers.EmailField()
    
    def validate_email(self, value):
        if not TenantUser.objects.filter(email=value, is_active=True).exists():
            raise serializers.ValidationError("No active user found with this email address.")
        return value


class PasswordResetSerializer(serializers.Serializer):
    """Serializer for password reset confirmation"""
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError("Password and confirm password do not match.")
        return attrs


class EmailVerificationSerializer(serializers.Serializer):
    """Serializer for email verification"""
    token = serializers.CharField()
    email = serializers.EmailField()


class TenantProfileSerializer(serializers.ModelSerializer):
    """Serializer for tenant business profile"""
    
    class Meta:
        model = Tenant
        fields = [
            'id', 'business_name', 'business_email', 'business_phone',
            'subscription_tier', 'status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'subscription_tier', 'status', 'created_at', 'updated_at']


class TenantSettingsSerializer(serializers.ModelSerializer):
    """Serializer for tenant configuration settings"""
    
    class Meta:
        model = Tenant
        fields = ['encryption_key_hash', 'status']
        read_only_fields = ['encryption_key_hash']


class TenantUserSerializer(serializers.ModelSerializer):
    """Serializer for tenant users"""
    
    class Meta:
        model = TenantUser
        fields = [
            'id', 'email', 'first_name', 'last_name', 'role', 
            'permissions', 'is_active', 'last_login', 'created_at'
        ]
        read_only_fields = ['id', 'last_login', 'created_at']
        extra_kwargs = {
            'password_hash': {'write_only': True}
        }


class TenantUserCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new tenant users (invites)"""
    password = serializers.CharField(write_only=True, required=False)
    send_invite = serializers.BooleanField(default=True, write_only=True)
    
    class Meta:
        model = TenantUser
        fields = [
            'email', 'first_name', 'last_name', 'role', 
            'permissions', 'password', 'send_invite'
        ]
        extra_kwargs = {
            'role': {'default': 'agent'},
            'permissions': {'default': dict}
        }
    
    def validate_email(self, value):
        tenant = self.context['request'].user.tenant
        if TenantUser.objects.filter(tenant=tenant, email=value).exists():
            raise serializers.ValidationError("A user with this email already exists in your organization.")
        return value
    
    def create(self, validated_data):
        tenant = self.context['request'].user.tenant
        send_invite = validated_data.pop('send_invite', True)
        password = validated_data.pop('password', None)
        
        user = TenantUser.objects.create(
            tenant=tenant,
            is_active=False if send_invite else True,
            password_hash=password if password else '',
            **validated_data
        )
        
        # TODO: Send invitation email if send_invite is True
        
        return user


class TenantUserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating tenant users"""
    
    class Meta:
        model = TenantUser
        fields = ['first_name', 'last_name', 'role', 'permissions']


class TenantUserRoleSerializer(serializers.ModelSerializer):
    """Serializer for updating user role and permissions"""
    
    class Meta:
        model = TenantUser
        fields = ['role', 'permissions']


class TenantUserActivationSerializer(serializers.ModelSerializer):
    """Serializer for activating/deactivating users"""
    
    class Meta:
        model = TenantUser
        fields = ['is_active']