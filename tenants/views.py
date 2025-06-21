# tenants/views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.db import transaction, IntegrityError
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Q, Count
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .models import Tenant, TenantUser, AuditLog
from .authentication import get_tokens_for_user
from .serializers import (
    TenantCreateSerializer,
    TenantUserRegistrationSerializer,
    TenantOwnerRegistrationSerializer,
    TenantUserLoginSerializer,
    TenantUserDetailSerializer,
    TenantUserUpdateSerializer,
    ChangePasswordSerializer,
    TenantListSerializer,
    TenantSerializer
)


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def tenants(request):
    """
    GET /api/tenants/ - List all tenants (for admin purposes)
    POST /api/tenants/ - Create a new tenant (business organization)
    """
    
    if request.method == 'GET':
        # List tenants (usually for admin or public directory)
        queryset = Tenant.objects.all()
        
        # Filter by status
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Search by name or email
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(business_name__icontains=search) | 
                Q(business_email__icontains=search)
            )
        
        # Annotate with user count
        queryset = queryset.annotate(users_count=Count('users'))
        queryset = queryset.order_by('business_name')
        
        serializer = TenantListSerializer(queryset, many=True)
        
        return Response({
            'results': serializer.data,
            'summary': {
                'total_tenants': queryset.count(),
                'active_tenants': queryset.filter(status='active').count()
            }
        }, status=status.HTTP_200_OK)
    
    elif request.method == 'POST':
        # Create new tenant (business organization only)
        serializer = TenantCreateSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                tenant = serializer.save()
                
                response_serializer = TenantSerializer(tenant)
                
                return Response({
                    'message': f'Tenant "{tenant.business_name}" created successfully',
                    'tenant': response_serializer.data
                }, status=status.HTTP_201_CREATED)
                
            except IntegrityError as e:
                return Response({
                    'error': 'Failed to create tenant due to database constraint',
                    'details': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def register_business(request):
    """
    POST /api/auth/register-business/ - Register a new business (tenant) with its first admin user
    This creates both the tenant and the admin user in one step
    """
    serializer = TenantOwnerRegistrationSerializer(data=request.data)
    
    if serializer.is_valid():
        try:
            with transaction.atomic():
                # Create tenant and admin user
                user = serializer.save()
                
                # Generate JWT tokens
                tokens = get_tokens_for_user(user)
                
                # Update last login
                user.last_login = timezone.now()
                user.save(update_fields=['last_login'])
                
                # Log registration
                AuditLog.objects.create(
                    tenant=user.tenant,
                    user=user,
                    action_type='BUSINESS_REGISTRATION',
                    resource_type='TENANT',
                    resource_id=user.tenant.id,
                    new_values={
                        'business_name': user.tenant.business_name,
                        'admin_email': user.email
                    },
                    ip_address=request.META.get('REMOTE_ADDR', ''),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    session_id=request.session.session_key or ''
                )
                
                # Return user details with tokens
                user_serializer = TenantUserDetailSerializer(user)
                
                return Response({
                    'message': 'Business registration successful',
                    'access_token': tokens['access'],
                    'refresh_token': tokens['refresh'],
                    'user': user_serializer.data
                }, status=status.HTTP_201_CREATED)
                
        except IntegrityError as e:
            return Response({
                'error': 'Registration failed due to database constraint',
                'details': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'error': 'Registration failed',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def register_user(request):
    """
    POST /api/auth/register-user/ - Register a new user to an existing tenant
    Only admins can add users to their tenant
    """
    
    # Check if user is admin
    if not request.user.is_admin:
        return Response({
            'error': 'Only administrators can register new users'
        }, status=status.HTTP_403_FORBIDDEN)
    
    # Auto-set the tenant_id to the current user's tenant
    data = request.data.copy()
    data['tenant_id'] = str(request.user.tenant.id)
    
    serializer = TenantUserRegistrationSerializer(data=data)
    
    if serializer.is_valid():
        try:
            with transaction.atomic():
                user = serializer.save()
                
                # Log user creation
                AuditLog.objects.create(
                    tenant=user.tenant,
                    user=request.user,  # Who created the user
                    action_type='USER_CREATION',
                    resource_type='TENANT_USER',
                    resource_id=user.id,
                    new_values={
                        'email': user.email,
                        'role': user.role,
                        'created_by': request.user.email
                    },
                    ip_address=request.META.get('REMOTE_ADDR', ''),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    session_id=request.session.session_key or ''
                )
                
                # Return user details
                user_serializer = TenantUserDetailSerializer(user)
                
                return Response({
                    'message': 'User created successfully',
                    'user': user_serializer.data
                }, status=status.HTTP_201_CREATED)
                
        except IntegrityError as e:
            return Response({
                'error': 'User creation failed due to database constraint',
                'details': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'error': 'User creation failed',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """
    POST /api/auth/login/ - Login tenant user
    """
    serializer = TenantUserLoginSerializer(data=request.data)
    
    if serializer.is_valid():
        user = serializer.validated_data['user']
        
        try:
            # Generate JWT tokens
            tokens = get_tokens_for_user(user)
            
            # Update last login
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            
            # Log successful login
            AuditLog.objects.create(
                tenant=user.tenant,
                user=user,
                action_type='USER_LOGIN',
                resource_type='TENANT_USER',
                resource_id=user.id,
                new_values={'last_login': user.last_login.isoformat()},
                ip_address=request.META.get('REMOTE_ADDR', ''),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                session_id=request.session.session_key or ''
            )
            
            # Return user details with tokens
            user_serializer = TenantUserDetailSerializer(user)
            
            return Response({
                'message': 'Login successful',
                'access_token': tokens['access'],
                'refresh_token': tokens['refresh'],
                'user': user_serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': 'Login failed',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def token_refresh(request):
    """
    POST /api/auth/token/refresh/ - Refresh access token using refresh token
    """
    refresh_token = request.data.get('refresh_token')
    
    if not refresh_token:
        return Response({
            'error': 'Refresh token is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Validate and refresh the token
        refresh = RefreshToken(refresh_token)
        
        # Get user to validate tenant status
        user_id = refresh['user_id']
        user = TenantUser.objects.select_related('tenant').get(id=user_id)
        
        if not user.is_active:
            return Response({
                'error': 'User account is inactive'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        if user.tenant.status != 'active':
            return Response({
                'error': 'Tenant account is suspended'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Generate new access token
        access_token = refresh.access_token
        
        return Response({
            'access_token': str(access_token)
        }, status=status.HTTP_200_OK)
        
    except TokenError as e:
        return Response({
            'error': 'Invalid refresh token'
        }, status=status.HTTP_401_UNAUTHORIZED)
    except TenantUser.DoesNotExist:
        return Response({
            'error': 'User not found'
        }, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    """
    POST /api/auth/logout/ - Logout current user by blacklisting refresh token
    """
    try:
        refresh_token = request.data.get('refresh_token')
        
        if refresh_token:
            # Blacklist the refresh token
            token = RefreshToken(refresh_token)
            token.blacklist()
        
        # Log logout action
        AuditLog.objects.create(
            tenant=request.user.tenant,
            user=request.user,
            action_type='USER_LOGOUT',
            resource_type='TENANT_USER',
            resource_id=request.user.id,
            old_values={'last_login': request.user.last_login.isoformat() if request.user.last_login else None},
            ip_address=request.META.get('REMOTE_ADDR', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            session_id=request.session.session_key or ''
        )
        
        return Response({
            'message': 'Logout successful'
        }, status=status.HTTP_200_OK)
        
    except TokenError:
        return Response({
            'message': 'Logout successful'  # Still return success even if token was invalid
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            'error': 'Logout failed',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def profile(request):
    """
    GET /api/auth/profile/ - Get current user profile
    """
    serializer = TenantUserDetailSerializer(request.user)
    return Response({
        'user': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    """
    PUT/PATCH /api/auth/profile/ - Update current user profile
    """
    serializer = TenantUserUpdateSerializer(
        request.user, 
        data=request.data, 
        partial=request.method == 'PATCH'
    )
    
    if serializer.is_valid():
        try:
            # Store old values for audit
            old_values = {
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'role': request.user.role
            }
            
            # Update user
            user = serializer.save()
            
            # Log profile update
            AuditLog.objects.create(
                tenant=user.tenant,
                user=user,
                action_type='USER_PROFILE_UPDATE',
                resource_type='TENANT_USER',
                resource_id=user.id,
                old_values=old_values,
                new_values=serializer.validated_data,
                ip_address=request.META.get('REMOTE_ADDR', ''),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                session_id=request.session.session_key or ''
            )
            
            # Return updated user data
            response_serializer = TenantUserDetailSerializer(user)
            
            return Response({
                'message': 'Profile updated successfully',
                'user': response_serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': 'Profile update failed',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """
    POST /api/auth/change-password/ - Change user password
    """
    serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
    
    if serializer.is_valid():
        try:
            # Update password
            user = request.user
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            
            # Log password change
            AuditLog.objects.create(
                tenant=user.tenant,
                user=user,
                action_type='PASSWORD_CHANGE',
                resource_type='TENANT_USER',
                resource_id=user.id,
                new_values={'password_changed_at': timezone.now().isoformat()},
                ip_address=request.META.get('REMOTE_ADDR', ''),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                session_id=request.session.session_key or ''
            )
            
            # Generate new tokens for the user
            tokens = get_tokens_for_user(user)
            
            return Response({
                'message': 'Password changed successfully',
                'access_token': tokens['access'],
                'refresh_token': tokens['refresh']
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': 'Password change failed',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def users(request):
    """
    GET /api/auth/users/ - List tenant users (admin only)
    """
    
    # Check if user is admin
    if not request.user.is_admin:
        return Response({
            'error': 'Only administrators can access user management'
        }, status=status.HTTP_403_FORBIDDEN)
    
    # Get all users in the same tenant
    queryset = TenantUser.objects.filter(tenant=request.user.tenant)
    
    # Filter by active status if requested
    is_active = request.query_params.get('is_active')
    if is_active is not None:
        is_active_bool = is_active.lower() in ['true', '1', 'yes']
        queryset = queryset.filter(is_active=is_active_bool)
    
    # Search by name or email
    search = request.query_params.get('search')
    if search:
        queryset = queryset.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )
    
    # Filter by role
    role = request.query_params.get('role')
    if role:
        queryset = queryset.filter(role=role)
    
    # Order by creation date
    queryset = queryset.order_by('-created_at')
    
    # Serialize users
    serializer = TenantUserDetailSerializer(queryset, many=True)
    
    # Add summary statistics
    total_users = queryset.count()
    active_users = queryset.filter(is_active=True).count()
    
    return Response({
        'results': serializer.data,
        'summary': {
            'total_users': total_users,
            'active_users': active_users,
            'inactive_users': total_users - active_users
        }
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def verify_token(request):
    """
    GET /api/auth/verify/ - Verify token validity and return user info
    """
    serializer = TenantUserDetailSerializer(request.user)
    return Response({
        'valid': True,
        'user': serializer.data
    }, status=status.HTTP_200_OK)