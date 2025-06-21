# tenants/authentication.py
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth import get_user_model


class TenantJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication with tenant validation
    """
    
    def get_user(self, validated_token):
        """
        Get user from validated token and perform tenant checks
        """
        try:
            user_id = validated_token['user_id']
        except KeyError:
            raise InvalidToken('Token contained no recognizable user identification')
        
        try:
            User = get_user_model()
            user = User.objects.select_related('tenant').get(id=user_id)
        except User.DoesNotExist:
            raise AuthenticationFailed('User not found')
        
        if not user.is_active:
            raise AuthenticationFailed('User inactive or deleted')
        
        # Check tenant status
        if user.tenant and user.tenant.status != 'active':
            raise AuthenticationFailed('Tenant account is suspended')
        
        return user


# Custom JWT Token Classes with tenant info
from rest_framework_simplejwt.tokens import RefreshToken

class TenantRefreshToken(RefreshToken):
    """Custom refresh token that includes tenant information"""
    
    @classmethod
    def for_user(cls, user):
        token = super().for_user(user)
        
        # Add custom claims
        token['tenant_id'] = str(user.tenant.id)
        token['tenant_name'] = user.tenant.business_name
        token['user_role'] = user.role
        token['email'] = user.email
        
        return token


def get_tokens_for_user(user):
    """
    Generate access and refresh tokens for a user
    """
    refresh = TenantRefreshToken.for_user(user)
    
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }