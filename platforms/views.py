# platforms/views.py
from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .models import SocialPlatform, TenantPlatformAccount
from .serializers import (
    SocialPlatformSerializer, SocialPlatformDetailSerializer,
    TenantPlatformAccountSerializer, TenantPlatformAccountCreateSerializer,
    TenantPlatformAccountUpdateSerializer, ConnectionTestSerializer,
    SyncStatusSerializer, WebhookVerificationSerializer,
    FacebookWebhookSerializer, WhatsAppWebhookSerializer,
    InstagramWebhookSerializer, TelegramWebhookSerializer,
    TikTokWebhookSerializer
)
from tenants.permissions import IsTenantMember, IsTenantAdmin
from .services import (
    PlatformConnectionService, WebhookProcessingService
)
import logging

logger = logging.getLogger(__name__)


# Platform Management Views
class SocialPlatformListView(generics.ListAPIView):
    """List available social media platforms"""
    serializer_class = SocialPlatformSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]
    queryset = SocialPlatform.objects.filter(is_active=True)
    
    def get_queryset(self):
        """Filter platforms based on tenant subscription"""
        queryset = super().get_queryset()
        # TODO: Filter based on tenant subscription tier
        return queryset


class SocialPlatformDetailView(generics.RetrieveAPIView):
    """Get platform details and requirements"""
    serializer_class = SocialPlatformDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]
    queryset = SocialPlatform.objects.filter(is_active=True)


# Platform Connections Views
class TenantPlatformAccountListCreateView(generics.ListCreateAPIView):
    """List connected platform accounts and connect new ones"""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return TenantPlatformAccountCreateSerializer
        return TenantPlatformAccountSerializer
    
    def get_queryset(self):
        return TenantPlatformAccount.objects.filter(
            tenant=self.request.user.tenant
        ).select_related('platform')
    
    def perform_create(self, serializer):
        # Additional permission check for creation
        if not (self.request.user.role in ['admin', 'owner']):
            raise permissions.PermissionDenied("Only admins and owners can connect platforms")
        
        account = serializer.save()
        
        # Test connection after creation
        try:
            connection_service = PlatformConnectionService(account)
            test_result = connection_service.test_connection()
            
            if test_result['success']:
                account.connection_status = 'connected'
            else:
                account.connection_status = 'failed'
                
            account.save(update_fields=['connection_status'])
            
        except Exception as e:
            logger.error(f"Failed to test connection for {account.id}: {str(e)}")
            account.connection_status = 'failed'
            account.save(update_fields=['connection_status'])


class TenantPlatformAccountDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update, or delete platform account"""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return TenantPlatformAccountUpdateSerializer
        return TenantPlatformAccountSerializer
    
    def get_queryset(self):
        return TenantPlatformAccount.objects.filter(
            tenant=self.request.user.tenant
        ).select_related('platform')
    
    def perform_update(self, serializer):
        # Check permissions for updates
        if not (self.request.user.role in ['admin', 'owner']):
            raise permissions.PermissionDenied("Only admins and owners can update platform connections")
        
        serializer.save()
    
    def perform_destroy(self, instance):
        # Check permissions for deletion
        if not (self.request.user.role in ['admin', 'owner']):
            raise permissions.PermissionDenied("Only admins and owners can disconnect platforms")
        
        with transaction.atomic():
            # TODO: Clean up related data (webhooks, conversations, etc.)
            instance.delete()


class PlatformConnectionTestView(APIView):
    """Test platform connection"""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]
    
    def post(self, request, account_id):
        account = get_object_or_404(
            TenantPlatformAccount,
            id=account_id,
            tenant=request.user.tenant
        )
        
        try:
            connection_service = PlatformConnectionService(account)
            test_result = connection_service.test_connection()
            
            # Update connection status
            if test_result['success']:
                account.connection_status = 'connected'
            else:
                account.connection_status = 'failed'
            
            account.save(update_fields=['connection_status'])
            
            serializer = ConnectionTestSerializer(data={
                'success': test_result['success'],
                'message': test_result['message'],
                'details': test_result.get('details', {}),
                'last_tested': timezone.now()
            })
            
            if serializer.is_valid():
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Connection test failed for {account_id}: {str(e)}")
            return Response({
                'success': False,
                'message': 'Connection test failed due to internal error',
                'details': {'error': str(e)}
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PlatformSyncView(APIView):
    """Manual sync with platform"""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]
    
    def post(self, request, account_id):
        account = get_object_or_404(
            TenantPlatformAccount,
            id=account_id,
            tenant=request.user.tenant
        )
        
        if account.connection_status != 'connected':
            return Response({
                'sync_started': False,
                'message': 'Cannot sync - platform is not connected'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # TODO: Implement actual sync logic
            sync_id = f"sync_{account_id}_{int(timezone.now().timestamp())}"
            
            # Update last sync time
            account.last_sync = timezone.now()
            account.save(update_fields=['last_sync'])
            
            serializer = SyncStatusSerializer(data={
                'sync_started': True,
                'message': 'Sync started successfully',
                'sync_id': sync_id,
                'estimated_duration': 30
            })
            
            if serializer.is_valid():
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Sync failed for {account_id}: {str(e)}")
            return Response({
                'sync_started': False,
                'message': 'Sync failed due to internal error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Webhook Views
@method_decorator(csrf_exempt, name='dispatch')
class FacebookWebhookView(APIView):
    """Facebook webhook endpoint"""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        """Webhook verification for Facebook"""
        serializer = WebhookVerificationSerializer(data=request.GET)
        if serializer.is_valid():
            challenge = serializer.validated_data.get('challenge')
            verify_token = serializer.validated_data.get('verify_token')
            
            # TODO: Validate verify_token against stored tokens
            if verify_token == 'your_verify_token':  # Replace with actual validation
                return Response(challenge, status=status.HTTP_200_OK)
            else:
                return Response('Invalid verify token', status=status.HTTP_403_FORBIDDEN)
        
        return Response('Invalid request', status=status.HTTP_400_BAD_REQUEST)
    
    def post(self, request):
        """Handle Facebook webhook payload"""
        try:
            serializer = FacebookWebhookSerializer(data=request.data)
            if serializer.is_valid():
                webhook_service = WebhookProcessingService('facebook')
                result = webhook_service.process_webhook(serializer.validated_data)
                
                if result['success']:
                    return Response({'status': 'ok'}, status=status.HTTP_200_OK)
                else:
                    return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Facebook webhook processing failed: {str(e)}")
            return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class WhatsAppWebhookView(APIView):
    """WhatsApp webhook endpoint"""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        """Webhook verification for WhatsApp"""
        serializer = WebhookVerificationSerializer(data=request.GET)
        if serializer.is_valid():
            challenge = serializer.validated_data.get('challenge')
            verify_token = serializer.validated_data.get('verify_token')
            
            # TODO: Validate verify_token against stored tokens
            if verify_token == 'your_verify_token':  # Replace with actual validation
                return Response(challenge, status=status.HTTP_200_OK)
            else:
                return Response('Invalid verify token', status=status.HTTP_403_FORBIDDEN)
        
        return Response('Invalid request', status=status.HTTP_400_BAD_REQUEST)
    
    def post(self, request):
        """Handle WhatsApp webhook payload"""
        try:
            serializer = WhatsAppWebhookSerializer(data=request.data)
            if serializer.is_valid():
                webhook_service = WebhookProcessingService('whatsapp')
                result = webhook_service.process_webhook(serializer.validated_data)
                
                if result['success']:
                    return Response({'status': 'ok'}, status=status.HTTP_200_OK)
                else:
                    return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"WhatsApp webhook processing failed: {str(e)}")
            return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class InstagramWebhookView(APIView):
    """Instagram webhook endpoint"""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        """Webhook verification for Instagram"""
        serializer = WebhookVerificationSerializer(data=request.GET)
        if serializer.is_valid():
            challenge = serializer.validated_data.get('challenge')
            verify_token = serializer.validated_data.get('verify_token')
            
            # TODO: Validate verify_token against stored tokens
            if verify_token == 'your_verify_token':  # Replace with actual validation
                return Response(challenge, status=status.HTTP_200_OK)
            else:
                return Response('Invalid verify token', status=status.HTTP_403_FORBIDDEN)
        
        return Response('Invalid request', status=status.HTTP_400_BAD_REQUEST)
    
    def post(self, request):
        """Handle Instagram webhook payload"""
        try:
            serializer = InstagramWebhookSerializer(data=request.data)
            if serializer.is_valid():
                webhook_service = WebhookProcessingService('instagram')
                result = webhook_service.process_webhook(serializer.validated_data)
                
                if result['success']:
                    return Response({'status': 'ok'}, status=status.HTTP_200_OK)
                else:
                    return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Instagram webhook processing failed: {str(e)}")
            return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class TelegramWebhookView(APIView):
    """Telegram webhook endpoint"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        """Handle Telegram webhook payload"""
        try:
            serializer = TelegramWebhookSerializer(data=request.data)
            if serializer.is_valid():
                webhook_service = WebhookProcessingService('telegram')
                result = webhook_service.process_webhook(serializer.validated_data)
                
                if result['success']:
                    return Response({'ok': True}, status=status.HTTP_200_OK)
                else:
                    return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Telegram webhook processing failed: {str(e)}")
            return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class TikTokWebhookView(APIView):
    """TikTok webhook endpoint"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        """Handle TikTok webhook payload"""
        try:
            serializer = TikTokWebhookSerializer(data=request.data)
            if serializer.is_valid():
                webhook_service = WebhookProcessingService('tiktok')
                result = webhook_service.process_webhook(serializer.validated_data)
                
                if result['success']:
                    return Response({'status': 'success'}, status=status.HTTP_200_OK)
                else:
                    return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"TikTok webhook processing failed: {str(e)}")
            return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def webhook_verification_view(request, platform):
    """Generic webhook verification endpoint"""
    try:
        platform_obj = get_object_or_404(SocialPlatform, name=platform)
        
        if platform in ['facebook', 'whatsapp', 'instagram']:
            serializer = WebhookVerificationSerializer(data=request.GET)
            if serializer.is_valid():
                challenge = serializer.validated_data.get('challenge')
                verify_token = serializer.validated_data.get('verify_token')
                
                # TODO: Validate verify_token against stored tokens for the platform
                if verify_token == 'your_verify_token':  # Replace with actual validation
                    return Response(challenge, status=status.HTTP_200_OK)
                else:
                    return Response('Invalid verify token', status=status.HTTP_403_FORBIDDEN)
            
            return Response('Invalid request', status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response('Verification not required for this platform', status=status.HTTP_200_OK)
            
    except Exception as e:
        logger.error(f"Webhook verification failed for {platform}: {str(e)}")
        return Response('Internal server error', status=status.HTTP_500_INTERNAL_SERVER_ERROR)