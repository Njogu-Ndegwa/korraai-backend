# tenants/views.py
from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import logout
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import Tenant, TenantUser
from .serializers import (
    TenantRegistrationSerializer, LoginSerializer, PasswordResetRequestSerializer,
    PasswordResetSerializer, EmailVerificationSerializer, TenantProfileSerializer,
    TenantSettingsSerializer, TenantUserSerializer, TenantUserCreateSerializer,
    TenantUserUpdateSerializer, TenantUserRoleSerializer, TenantUserActivationSerializer
)
from .permissions import IsTenantOwner, IsTenantMember, IsTenantAdmin


# Authentication Views
class TenantRegistrationView(APIView):
    """Register new tenant account"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = TenantRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            with transaction.atomic():
                tenant = serializer.save()
                # Get the created admin user
                admin_user = tenant.users.filter(role='admin').first()
                
                # Generate JWT tokens
                refresh = RefreshToken.for_user(admin_user)
                
                return Response({
                    'message': 'Tenant registered successfully',
                    'tenant': TenantProfileSerializer(tenant).data,
                    'user': TenantUserSerializer(admin_user).data,
                    'tokens': {
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                    }
                }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """Login user"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            # Update last login
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            
            return Response({
                'message': 'Login successful',
                'user': TenantUserSerializer(user).data,
                'tenant': TenantProfileSerializer(user.tenant).data,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    """Logout user"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh_token")
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            logout(request)
            return Response({
                'message': 'Successfully logged out'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'error': 'Invalid token'
            }, status=status.HTTP_400_BAD_REQUEST)


class RefreshTokenView(APIView):
    """Refresh JWT token"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                refresh = RefreshToken(refresh_token)
                return Response({
                    'access': str(refresh.access_token)
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'error': 'Refresh token is required'
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'error': 'Invalid refresh token'
            }, status=status.HTTP_400_BAD_REQUEST)


class ForgotPasswordView(APIView):
    """Send password reset email"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            # TODO: Generate reset token and send email
            # For now, just return success
            return Response({
                'message': 'Password reset email sent successfully'
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ResetPasswordView(APIView):
    """Reset password with token"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        if serializer.is_valid():
            # TODO: Verify token and update password
            return Response({
                'message': 'Password reset successfully'
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyEmailView(APIView):
    """Verify email address"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = EmailVerificationSerializer(data=request.data)
        if serializer.is_valid():
            # TODO: Verify email token and mark email as verified
            return Response({
                'message': 'Email verified successfully'
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Tenant Management Views
class TenantProfileView(APIView):
    """Get and update tenant business profile"""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]
    
    def get(self, request):
        tenant = request.user.tenant
        serializer = TenantProfileSerializer(tenant)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def put(self, request):
        tenant = request.user.tenant
        serializer = TenantProfileSerializer(tenant, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TenantSettingsView(APIView):
    """Get and update tenant configuration settings"""
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]
    
    def get(self, request):
        tenant = request.user.tenant
        serializer = TenantSettingsSerializer(tenant)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def put(self, request):
        tenant = request.user.tenant
        serializer = TenantSettingsSerializer(tenant, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TenantAccountDeleteView(APIView):
    """Delete tenant account"""
    permission_classes = [permissions.IsAuthenticated, IsTenantOwner]
    
    def delete(self, request):
        tenant = request.user.tenant
        with transaction.atomic():
            # TODO: Add cleanup logic for related data
            tenant.delete()
        return Response({
            'message': 'Tenant account deleted successfully'
        }, status=status.HTTP_204_NO_CONTENT)


# User Management Views
class TenantUserListCreateView(generics.ListCreateAPIView):
    """List all users in tenant and create new user"""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return TenantUserCreateSerializer
        return TenantUserSerializer
    
    def get_queryset(self):
        return TenantUser.objects.filter(tenant=self.request.user.tenant)
    
    def perform_create(self, serializer):
        # Additional permission check for creation
        if not (self.request.user.role in ['admin', 'owner']):
            raise permissions.PermissionDenied("Only admins and owners can invite new users")
        serializer.save()


class TenantUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update, or delete specific user"""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return TenantUserUpdateSerializer
        return TenantUserSerializer
    
    def get_queryset(self):
        return TenantUser.objects.filter(tenant=self.request.user.tenant)
    
    def perform_update(self, serializer):
        # Check permissions for user updates
        target_user = self.get_object()
        current_user = self.request.user
        
        if target_user.id != current_user.id and current_user.role not in ['admin', 'owner']:
            raise permissions.PermissionDenied("You can only update your own profile")
        
        serializer.save()
    
    def perform_destroy(self, instance):
        # Check permissions for user deletion
        if self.request.user.role not in ['admin', 'owner']:
            raise permissions.PermissionDenied("Only admins and owners can remove users")
        
        if instance.role == 'owner':
            raise permissions.PermissionDenied("Cannot delete the tenant owner")
        
        instance.delete()


class TenantUserRoleUpdateView(APIView):
    """Update user role and permissions"""
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]
    
    def put(self, request, user_id):
        user = get_object_or_404(TenantUser, id=user_id, tenant=request.user.tenant)
        
        # Prevent changing owner role
        if user.role == 'owner':
            return Response({
                'error': 'Cannot change owner role'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = TenantUserRoleSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TenantUserResendInviteView(APIView):
    """Resend invitation email"""
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]
    
    def post(self, request, user_id):
        user = get_object_or_404(TenantUser, id=user_id, tenant=request.user.tenant)
        
        if user.is_active:
            return Response({
                'error': 'User is already active'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # TODO: Resend invitation email logic
        return Response({
            'message': 'Invitation email sent successfully'
        }, status=status.HTTP_200_OK)


class TenantUserActivationView(APIView):
    """Activate/deactivate user"""
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]
    
    def put(self, request, user_id):
        user = get_object_or_404(TenantUser, id=user_id, tenant=request.user.tenant)
        
        # Prevent deactivating owner
        if user.role == 'owner':
            return Response({
                'error': 'Cannot deactivate the tenant owner'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = TenantUserActivationSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            action = 'activated' if serializer.validated_data['is_active'] else 'deactivated'
            return Response({
                'message': f'User {action} successfully',
                'user': TenantUserSerializer(user).data
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)