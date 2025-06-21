# knowledge_base/auth_utils.py
from rest_framework.response import Response
from rest_framework import status
from tenants.models import TenantUser


def get_tenant_from_user(request):
    """
    Extract tenant_id from authenticated user
    Returns tuple: (tenant_id, error_response)
    """
    if not request.user.is_authenticated:
        return None, Response(
            {'error': 'Authentication required'}, 
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    tenant_id = None
    
    # Try different ways to get tenant_id based on your user model
    
    # Option 1: Direct tenant_id field on user
    if hasattr(request.user, 'tenant_id') and request.user.tenant_id:
        tenant_id = request.user.tenant_id
    
    # Option 2: Tenant relationship on user
    elif hasattr(request.user, 'tenant') and request.user.tenant:
        tenant_id = request.user.tenant.id
    
    # Option 3: Through TenantUser model (most likely for your case)
    else:
        try:
            # Assuming your user model has an email field
            tenant_user = TenantUser.objects.select_related('tenant').get(
                email=request.user.email,
                is_active=True
            )
            tenant_id = tenant_user.tenant_id
        except TenantUser.DoesNotExist:
            try:
                # Alternative: if user model has different identifier
                tenant_user = TenantUser.objects.select_related('tenant').get(
                    id=request.user.id,
                    is_active=True
                )
                tenant_id = tenant_user.tenant_id
            except (TenantUser.DoesNotExist, AttributeError):
                pass
    
    if not tenant_id:
        return None, Response(
            {
                'error': 'User is not associated with any tenant or tenant is inactive',
                'user_id': str(request.user.id),
                'user_email': getattr(request.user, 'email', 'N/A')
            }, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    return tenant_id, None


def get_user_id_from_request(request):
    """
    Get user ID from authenticated user for TenantUser lookup
    """
    if not request.user.is_authenticated:
        return None
    
    # Try to get TenantUser ID
    try:
        tenant_user = TenantUser.objects.get(
            email=request.user.email,
            is_active=True
        )
        return tenant_user.id
    except TenantUser.DoesNotExist:
        return None