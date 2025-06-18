# tenants/authentication.py
from django.contrib.auth.backends import BaseBackend
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth.models import AnonymousUser
from .models import TenantUser
import jwt
from django.conf import settings


class TenantUserBackend(BaseBackend):
    """
    Custom authentication backend for TenantUser model
    """
    def authenticate(self, request, email=None, password=None, **kwargs):
        try:
            user = TenantUser.objects.get(email=email, is_active=True)
            # In production, use proper password hashing
            if user.password_hash == password:
                return user
        except TenantUser.DoesNotExist:
            return None
        return None

    def get_user(self, user_id):
        try:
            return TenantUser.objects.get(pk=user_id, is_active=True)
        except TenantUser.DoesNotExist:
            return None


class TenantJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication for TenantUser
    """
    def get_user(self, validated_token):
        """
        Attempts to find and return a user using the given validated token.
        """
        try:
            user_id = validated_token['user_id']
        except KeyError:
            raise InvalidToken('Token contained no recognizable user identification')

        try:
            user = TenantUser.objects.get(**{'id': user_id, 'is_active': True})
        except TenantUser.DoesNotExist:
            raise InvalidToken('User not found')

        return user


# Custom user property for request
class TenantUserMiddleware:
    """
    Middleware to set tenant user as request.user
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        # This will be handled by DRF authentication classes
        pass