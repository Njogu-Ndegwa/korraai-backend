from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import transaction, IntegrityError
from django.db.models import Count, Q
from django.utils import timezone
from .models import SocialPlatform, TenantPlatformAccount
from .serializers import (
    SocialPlatformSerializer,
    SocialPlatformCreateSerializer,
    SocialPlatformUpdateSerializer,
    SocialPlatformListSerializer,
    SocialPlatformDetailSerializer,
    TenantPlatformAccountSerializer,
    TenantPlatformAccountListSerializer,
    TenantPlatformAccountCreateSerializer,
    TenantPlatformAccountUpdateSerializer,
    TenantPlatformAccountDetailSerializer
)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def platforms(request):
    """
    GET /api/platforms/ - List all available social platforms
    POST /api/platforms/ - Create new platform (admin only)
    """
    
    if request.method == 'GET':
        # Get all platforms with optional filtering
        queryset = SocialPlatform.objects.all()
        
        # Filter by active status if requested
        is_active = request.query_params.get('is_active')
        if is_active is not None:
            is_active_bool = is_active.lower() in ['true', '1', 'yes']
            queryset = queryset.filter(is_active=is_active_bool)
        
        # Search by name or display name
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(display_name__icontains=search)
            )
        
        # Annotate with connected accounts count for current tenant
        tenant_id = getattr(request, 'tenant_id', None)
        if tenant_id:
            queryset = queryset.annotate(
                connected_accounts_count=Count(
                    'tenant_accounts',
                    filter=Q(
                        tenant_accounts__tenant_id=tenant_id,
                        tenant_accounts__connection_status='active'
                    )
                )
            )
        else:
            queryset = queryset.annotate(connected_accounts_count=Count('tenant_accounts'))
        
        # Order by display name
        queryset = queryset.order_by('display_name')
        
        # Serialize platforms
        serializer = SocialPlatformListSerializer(queryset, many=True)
        
        # Add summary statistics
        total_platforms = queryset.count()
        active_platforms = queryset.filter(is_active=True).count()
        
        return Response({
            'results': serializer.data,
            'summary': {
                'total_platforms': total_platforms,
                'active_platforms': active_platforms,
                'inactive_platforms': total_platforms - active_platforms
            }
        })
    
    elif request.method == 'POST':
        # Check if user is admin (only admins can create platforms)
        if not request.user.is_staff:
            return Response(
                {'error': 'Only administrators can create new platforms'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = SocialPlatformCreateSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    platform = serializer.save()
                
                # Return detailed platform info
                response_serializer = SocialPlatformDetailSerializer(platform)
                
                return Response(
                    {
                        'message': f'Platform "{platform.display_name}" created successfully',
                        'data': response_serializer.data
                    },
                    status=status.HTTP_201_CREATED
                )
                
            except IntegrityError as e:
                return Response(
                    {
                        'error': 'Failed to create platform due to database constraint',
                        'details': str(e)
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            except Exception as e:
                return Response(
                    {
                        'error': 'Failed to create platform',
                        'details': str(e)
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def platform_detail(request, platform_id):
    """
    GET /api/platforms/{platform_id}/ - Get specific platform details
    PUT /api/platforms/{platform_id}/ - Update platform configuration (admin only)
    DELETE /api/platforms/{platform_id}/ - Deactivate platform (admin only)
    """
    
    # Get platform object
    try:
        platform = get_object_or_404(SocialPlatform, id=platform_id)
    except Exception:
        return Response(
            {'error': 'Platform not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    if request.method == 'GET':
        # Anyone can view platform details
        serializer = SocialPlatformDetailSerializer(platform)
        
        # Add tenant-specific information if available
        tenant_id = getattr(request, 'tenant_id', None)
        platform_data = serializer.data
        
        if tenant_id:
            # Get tenant's connection status for this platform
            tenant_accounts = TenantPlatformAccount.objects.filter(
                tenant_id=tenant_id,
                platform=platform
            )
            
            platform_data['tenant_connection'] = {
                'is_connected': tenant_accounts.filter(connection_status='active').exists(),
                'total_accounts': tenant_accounts.count(),
                'active_accounts': tenant_accounts.filter(connection_status='active').count(),
                'last_connected': tenant_accounts.filter(
                    connection_status='active'
                ).order_by('-created_at').first().created_at if tenant_accounts.exists() else None
            }
        
        return Response({
            'data': platform_data
        })
    
    elif request.method == 'PUT':
        # Check if user is admin
        if not request.user.is_staff:
            return Response(
                {'error': 'Only administrators can update platforms'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = SocialPlatformUpdateSerializer(platform, data=request.data, partial=True)
        
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    updated_platform = serializer.save()
                
                # Return updated platform data
                response_serializer = SocialPlatformDetailSerializer(updated_platform)
                
                return Response(
                    {
                        'message': f'Platform "{updated_platform.display_name}" updated successfully',
                        'data': response_serializer.data
                    }
                )
                
            except Exception as e:
                return Response(
                    {
                        'error': 'Failed to update platform',
                        'details': str(e)
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        # Check if user is admin
        if not request.user.is_staff:
            return Response(
                {'error': 'Only administrators can deactivate platforms'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if platform has active connections
        active_connections = TenantPlatformAccount.objects.filter(
            platform=platform,
            connection_status='active'
        ).count()
        
        if active_connections > 0:
            return Response(
                {
                    'error': 'Cannot deactivate platform with active connections',
                    'message': f'Platform has {active_connections} active tenant connections. Please disconnect all accounts first.',
                    'active_connections': active_connections
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Soft delete - deactivate the platform
        try:
            with transaction.atomic():
                platform.is_active = False
                platform.save(update_fields=['is_active'])
            
            return Response(
                {
                    'message': f'Platform "{platform.display_name}" deactivated successfully',
                    'data': {
                        'id': str(platform.id),
                        'name': platform.name,
                        'deactivated_at': timezone.now().isoformat()
                    }
                }
            )
            
        except Exception as e:
            return Response(
                {
                    'error': 'Failed to deactivate platform',
                    'details': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



@api_view(['GET'])
def platform_accounts(request):
    """
    GET /api/platform-accounts/ - List tenant's connected accounts
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    # Get all platform accounts for the tenant
    queryset = TenantPlatformAccount.objects.filter(
        tenant_id=tenant_id
    ).select_related('platform').order_by('-created_at')
    
    # Filter by connection status if requested
    connection_status = request.query_params.get('connection_status')
    if connection_status:
        valid_statuses = ['active', 'paused', 'disconnected', 'error']
        if connection_status in valid_statuses:
            queryset = queryset.filter(connection_status=connection_status)
    
    # Filter by platform if requested
    platform_name = request.query_params.get('platform')
    if platform_name:
        queryset = queryset.filter(platform__name__icontains=platform_name)
    
    # Search by account name
    search = request.query_params.get('search')
    if search:
        queryset = queryset.filter(
            Q(account_name__icontains=search) | 
            Q(platform_account_id__icontains=search)
        )
    
    # Serialize accounts
    serializer = TenantPlatformAccountListSerializer(queryset, many=True)
    
    # Add summary statistics
    total_accounts = queryset.count()
    active_accounts = queryset.filter(connection_status='active').count()
    platforms_connected = queryset.values('platform').distinct().count()
    
    # Get accounts that need attention (not synced in 24 hours)
    needs_attention = queryset.filter(
        connection_status='active',
        last_sync__lt=timezone.now() - timezone.timedelta(hours=24)
    ).count()
    
    return Response({
        'results': serializer.data,
        'summary': {
            'total_accounts': total_accounts,
            'active_accounts': active_accounts,
            'platforms_connected': platforms_connected,
            'needs_attention': needs_attention
        }
    })


@api_view(['POST'])
def platform_accounts_connect(request):
    """
    POST /api/platform-accounts/connect/ - Connect new platform account
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    serializer = TenantPlatformAccountCreateSerializer(
        data=request.data,
        context={'request': request}
    )
    
    if serializer.is_valid():
        try:
            with transaction.atomic():
                # Create the platform account connection
                platform_account = serializer.save()
                
                # Test the connection (you would implement actual platform API test)
                connection_test_result = _test_platform_connection(platform_account)
                
                if not connection_test_result['success']:
                    # Update connection status if test failed
                    platform_account.connection_status = 'error'
                    platform_account.save(update_fields=['connection_status'])
                    
                    return Response(
                        {
                            'error': 'Failed to establish connection with platform',
                            'details': connection_test_result['error'],
                            'account_id': str(platform_account.id)
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Return success response with account details
            response_serializer = TenantPlatformAccountDetailSerializer(platform_account)
            
            return Response(
                {
                    'message': f'Successfully connected to {platform_account.platform.display_name}',
                    'data': response_serializer.data,
                    'connection_test': connection_test_result
                },
                status=status.HTTP_201_CREATED
            )
            
        except IntegrityError as e:
            return Response(
                {
                    'error': 'Failed to connect platform account due to database constraint',
                    'details': str(e)
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {
                    'error': 'Failed to connect platform account',
                    'details': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
def platform_account_detail(request, account_id):
    """
    GET /api/platform-accounts/{account_id}/ - Get specific account details
    PUT /api/platform-accounts/{account_id}/ - Update account settings
    DELETE /api/platform-accounts/{account_id}/ - Disconnect account
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    # Get platform account with tenant validation
    try:
        platform_account = get_object_or_404(
            TenantPlatformAccount,
            id=account_id,
            tenant_id=tenant_id
        )
    except Exception:
        return Response(
            {'error': 'Platform account not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    if request.method == 'GET':
        # Return detailed account information
        serializer = TenantPlatformAccountDetailSerializer(platform_account)
        
        # Add additional context
        account_data = serializer.data
        account_data['health_check'] = _get_account_health_status(platform_account)
        
        return Response({
            'data': account_data
        })
    
    elif request.method == 'PUT':
        # Update account settings
        serializer = TenantPlatformAccountUpdateSerializer(
            platform_account,
            data=request.data,
            partial=True
        )
        
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    updated_account = serializer.save()
                    
                    # If connection status changed to active, test the connection
                    if (updated_account.connection_status == 'active' and 
                        'connection_status' in request.data):
                        
                        test_result = _test_platform_connection(updated_account)
                        if not test_result['success']:
                            updated_account.connection_status = 'error'
                            updated_account.save(update_fields=['connection_status'])
                
                # Return updated account data
                response_serializer = TenantPlatformAccountDetailSerializer(updated_account)
                
                return Response(
                    {
                        'message': 'Platform account updated successfully',
                        'data': response_serializer.data
                    }
                )
                
            except Exception as e:
                return Response(
                    {
                        'error': 'Failed to update platform account',
                        'details': str(e)
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        # Disconnect the platform account
        
        # Check if account has active conversations or pending operations
        active_conversations_count = _get_active_conversations_count(platform_account)
        
        if active_conversations_count > 0:
            force_disconnect = request.query_params.get('force', 'false').lower() == 'true'
            
            if not force_disconnect:
                return Response(
                    {
                        'error': 'Account has active conversations',
                        'message': f'This account has {active_conversations_count} active conversations. Add ?force=true to disconnect anyway.',
                        'active_conversations': active_conversations_count
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        try:
            with transaction.atomic():
                # Update connection status instead of hard delete
                platform_account.connection_status = 'disconnected'
                platform_account.save(update_fields=['connection_status'])
                
                # Optionally clear sensitive tokens
                platform_account.access_token_encrypted = ''
                platform_account.refresh_token_encrypted = ''
                platform_account.webhook_secret_encrypted = ''
                platform_account.save(update_fields=[
                    'access_token_encrypted',
                    'refresh_token_encrypted', 
                    'webhook_secret_encrypted'
                ])
            
            return Response(
                {
                    'message': f'Successfully disconnected from {platform_account.platform.display_name}',
                    'data': {
                        'account_id': str(platform_account.id),
                        'platform_name': platform_account.platform.name,
                        'account_name': platform_account.account_name,
                        'disconnected_at': timezone.now().isoformat()
                    }
                }
            )
            
        except Exception as e:
            return Response(
                {
                    'error': 'Failed to disconnect platform account',
                    'details': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


def _test_platform_connection(platform_account):
    """Test connection to platform API"""
    # This is a placeholder - implement actual platform API testing
    # You would make API calls to verify tokens work
    
    try:
        # Simulate API test based on platform
        platform_name = platform_account.platform.name
        
        if platform_name == 'facebook':
            # Test Facebook Graph API
            success = True  # Placeholder
        elif platform_name == 'whatsapp':
            # Test WhatsApp Business API
            success = True  # Placeholder
        else:
            success = True  # Default success for now
        
        return {
            'success': success,
            'message': 'Connection test successful',
            'tested_at': timezone.now().isoformat()
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'tested_at': timezone.now().isoformat()
        }


def _get_account_health_status(platform_account):
    """Get health status of platform account"""
    health_status = {
        'overall_status': 'healthy',
        'issues': [],
        'last_checked': timezone.now().isoformat()
    }
    
    # Check token validity
    if not platform_account.access_token_encrypted:
        health_status['issues'].append('Missing access token')
        health_status['overall_status'] = 'error'
    
    # Check sync freshness
    if platform_account.last_sync:
        hours_since_sync = (timezone.now() - platform_account.last_sync).total_seconds() / 3600
        if hours_since_sync > 24:
            health_status['issues'].append(f'No sync in {int(hours_since_sync)} hours')
            health_status['overall_status'] = 'warning'
    else:
        health_status['issues'].append('Never synced')
        health_status['overall_status'] = 'warning'
    
    # Check connection status
    if platform_account.connection_status != 'active':
        health_status['issues'].append(f'Connection status: {platform_account.connection_status}')
        health_status['overall_status'] = 'error'
    
    return health_status


def _get_active_conversations_count(platform_account):
    """Get count of active conversations for this platform account"""
    # This would query your conversations model
    # Placeholder implementation
    return 0