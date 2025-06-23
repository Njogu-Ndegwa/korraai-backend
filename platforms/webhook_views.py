# # platforms/webhook_views.py
# import json
# import hashlib
# import hmac
# import asyncio
# from datetime import datetime
# from typing import Optional

# from django.http import HttpResponse, JsonResponse
# from django.views.decorators.csrf import csrf_exempt
# from django.views.decorators.http import require_http_methods, require_GET, require_POST
# from django.utils.decorators import method_decorator
# from django.views import View
# from django.conf import settings
# from django.utils import timezone
# from channels.layers import get_channel_layer
# from asgiref.sync import async_to_sync, sync_to_async

# from .models import SocialPlatform, TenantPlatformAccount
# from tenants.models import Tenant
# from customers.models import Customer
# from conversations.models import Conversation, Message
# from ai.models import TenantAISetting
# import uuid
# import logging

# logger = logging.getLogger(__name__)
# channel_layer = get_channel_layer()

# # platforms/webhook_views.py
# import json
# import hashlib
# import hmac
# import asyncio
# from datetime import datetime
# from typing import Optional

# from django.http import HttpResponse, JsonResponse
# from django.views.decorators.csrf import csrf_exempt
# from django.views.decorators.http import require_http_methods, require_GET, require_POST
# from django.utils.decorators import method_decorator
# from django.views import View
# from django.conf import settings
# from django.utils import timezone
# from channels.layers import get_channel_layer
# from asgiref.sync import async_to_sync

# from .models import SocialPlatform, TenantPlatformAccount
# from tenants.models import Tenant
# from customers.models import Customer
# from conversations.models import Conversation, Message
# from ai.models import TenantAISetting
# import uuid
# import logging

# logger = logging.getLogger(__name__)
# channel_layer = get_channel_layer()

# class FacebookWebhookView(View):
#     """Handle Facebook Messenger webhook verification and messages"""
    
#     @method_decorator(csrf_exempt)
#     def dispatch(self, request, *args, **kwargs):
#         return super().dispatch(request, *args, **kwargs)
    
#     def get(self, request):
#         """Webhook verification for Facebook"""
#         mode = request.GET.get('hub.mode')
#         token = request.GET.get('hub.verify_token')
#         challenge = request.GET.get('hub.challenge')
        
#         # Get Facebook platform
#         try:
#             facebook_platform = SocialPlatform.objects.get(name='facebook')
            
#             # Get any tenant's Facebook account for verification
#             # In production, you might want to handle this differently
#             facebook_account = TenantPlatformAccount.objects.filter(
#                 platform=facebook_platform
#             ).first()
            
#             if not facebook_account:
#                 logger.error("No Facebook account configured for webhook verification")
#                 return HttpResponse("No Facebook account configured", status=403)
                
#             verify_token = settings.FACEBOOK_VERIFY_TOKEN
            
#         except SocialPlatform.DoesNotExist:
#             logger.error("Facebook platform not found in database")
#             return HttpResponse("Platform not configured", status=500)
            
#         if mode == 'subscribe' and token == verify_token:
#             logger.info("Facebook webhook verified successfully")
#             return HttpResponse(challenge)
#         else:
#             logger.warning("Facebook webhook verification failed")
#             return HttpResponse("Verification failed", status=403)
    
#     def post(self, request):
#         """Handle incoming Facebook messages"""
#         try:
#             payload = json.loads(request.body)
#             logger.info(f"Facebook webhook payload: {json.dumps(payload, indent=2)}")
            
#             if payload.get('object') == 'page':
#                 for entry in payload.get('entry', []):
#                     # Get page ID to identify the tenant account
#                     page_id = entry.get('id')
                    
#                     for messaging_event in entry.get('messaging', []):
#                         if 'message' in messaging_event:
#                             asyncio.create_task(
#                                 self._process_facebook_message(messaging_event, page_id)
#                             )
            
#             return JsonResponse({'status': 'success'})
            
#         except Exception as e:
#             logger.error(f"Error processing Facebook webhook: {e}")
#             return JsonResponse({'error': 'Processing failed'}, status=500)
    
#     async def _process_facebook_message(self, messaging_event, page_id):
#         """Process individual Facebook message"""
#         try:
#             sender_id = messaging_event['sender']['id']
#             message_text = messaging_event['message'].get('text', '')
#             message_id = messaging_event['message'].get('mid')
#             timestamp = messaging_event.get('timestamp')
            
#             if not message_text:
#                 return
                
#             # Get tenant account and platform
#             facebook_platform = await self._get_facebook_platform()
#             tenant_account = await self._get_tenant_account(page_id, facebook_platform)
            
#             if not tenant_account:
#                 logger.error(f"No tenant account found for Facebook page {page_id}")
#                 return
                
#             # Get or create customer
#             customer = await self._get_or_create_customer(
#                 sender_id, tenant_account, facebook_platform
#             )
            
#             # Get or create conversation
#             conversation = await self._get_or_create_conversation(
#                 customer, tenant_account, facebook_platform
#             )
            
#             # Create user message
#             user_message = await self._create_message(
#                 tenant_account.tenant,
#                 conversation,
#                 message_id,
#                 message_text,
#                 'customer',
#                 'inbound',
#                 customer,
#                 timestamp
#             )
            
#             # Check if AI should handle this conversation
#             should_ai_handle = await self._should_ai_handle_conversation(conversation)
            
#             if should_ai_handle:
#                 # Send to RAG processing via WebSocket
#                 await self._send_to_rag_processor(conversation.id, message_text)
#             else:
#                 # Notify human agents via WebSocket
#                 await self._notify_human_agents(conversation.id, user_message)
                
#         except Exception as e:
#             logger.error(f"Error processing Facebook message: {e}")

# class WhatsAppWebhookView(View):
#     """Handle WhatsApp Business API webhook verification and messages"""
    
#     @method_decorator(csrf_exempt)
#     def dispatch(self, request, *args, **kwargs):
#         return super().dispatch(request, *args, **kwargs)
    
#     def get(self, request):
#         """Webhook verification for WhatsApp"""
#         mode = request.GET.get('hub.mode')
#         token = request.GET.get('hub.verify_token')
#         challenge = request.GET.get('hub.challenge')
        
#         verify_token = settings.WHATSAPP_VERIFY_TOKEN
        
#         if mode == 'subscribe' and token == verify_token:
#             logger.info("WhatsApp webhook verified successfully")
#             return HttpResponse(challenge)
#         else:
#             logger.warning("WhatsApp webhook verification failed")
#             return HttpResponse("Verification failed", status=403)
    
#     def post(self, request):
#         """Handle incoming WhatsApp messages"""
#         try:
#             payload = json.loads(request.body)
#             logger.info(f"WhatsApp webhook payload: {json.dumps(payload, indent=2)}")
            
#             if payload.get('object') == 'whatsapp_business_account':
#                 for entry in payload.get('entry', []):
#                     for change in entry.get('changes', []):
#                         if change.get('field') == 'messages':
#                             waba_id = entry.get('id')  # WhatsApp Business Account ID
                            
#                             for message in change.get('value', {}).get('messages', []):
#                                 if message.get('type') == 'text':
#                                     asyncio.create_task(
#                                         self._process_whatsapp_message(message, waba_id)
#                                     )
            
#             return JsonResponse({'status': 'success'})
            
#         except Exception as e:
#             logger.error(f"Error processing WhatsApp webhook: {e}")
#             return JsonResponse({'error': 'Processing failed'}, status=500)
    
#     async def _process_whatsapp_message(self, message, waba_id):
#         """Process individual WhatsApp message"""
#         try:
#             sender_id = message.get('from')
#             message_text = message.get('text', {}).get('body', '')
#             message_id = message.get('id')
#             timestamp = message.get('timestamp')
            
#             if not message_text:
#                 return
                
#             # Get tenant account and platform
#             whatsapp_platform = await self._get_whatsapp_platform()
#             tenant_account = await self._get_tenant_account(waba_id, whatsapp_platform)
            
#             if not tenant_account:
#                 logger.error(f"No tenant account found for WhatsApp Business Account {waba_id}")
#                 return
                
#             # Get or create customer
#             customer = await self._get_or_create_customer(
#                 sender_id, tenant_account, whatsapp_platform
#             )
            
#             # Get or create conversation
#             conversation = await self._get_or_create_conversation(
#                 customer, tenant_account, whatsapp_platform
#             )
            
#             # Create user message
#             user_message = await self._create_message(
#                 tenant_account.tenant,
#                 conversation,
#                 message_id,
#                 message_text,
#                 'customer',
#                 'inbound',
#                 customer,
#                 timestamp
#             )
            
#             # Check if AI should handle this conversation
#             should_ai_handle = await self._should_ai_handle_conversation(conversation)
            
#             if should_ai_handle:
#                 # Send to RAG processing via WebSocket
#                 await self._send_to_rag_processor(conversation.id, message_text)
#             else:
#                 # Notify human agents via WebSocket
#                 await self._notify_human_agents(conversation.id, user_message)
                
#         except Exception as e:
#             logger.error(f"Error processing WhatsApp message: {e}")

# # Shared methods for both webhook views
# class WebhookMixin:
#     """Shared methods for webhook processing"""
    
#     @sync_to_async
#     def _get_facebook_platform(self):
#         return SocialPlatform.objects.get(name='facebook')
    
#     @sync_to_async
#     def _get_whatsapp_platform(self):
#         return SocialPlatform.objects.get(name='whatsapp')
    
#     @sync_to_async
#     def _get_tenant_account(self, platform_account_id, platform):
#         try:
#             return TenantPlatformAccount.objects.select_related('tenant').get(
#                 platform_account_id=platform_account_id,
#                 platform=platform,
#                 connection_status='active'
#             )
#         except TenantPlatformAccount.DoesNotExist:
#             return None
    
#     @sync_to_async
#     def _get_or_create_customer(self, external_id, tenant_account, platform):
#         customer, created = Customer.objects.get_or_create(
#             external_id=external_id,
#             platform=platform,
#             platform_account=tenant_account,
#             tenant=tenant_account.tenant,
#             defaults={
#                 'platform_username': external_id,
#                 'first_contact_at': timezone.now(),
#                 'last_contact_at': timezone.now(),
#                 'last_seen_at': timezone.now(),
#                 'status': 'active'
#             }
#         )
        
#         if not created:
#             # Update last contact info
#             customer.last_contact_at = timezone.now()
#             customer.last_seen_at = timezone.now()
#             customer.save(update_fields=['last_contact_at', 'last_seen_at'])
            
#         return customer
    
#     @sync_to_async
#     def _get_or_create_conversation(self, customer, tenant_account, platform):
#         # Try to get existing active conversation
#         try:
#             conversation = Conversation.objects.get(
#                 customer=customer,
#                 platform=platform,
#                 platform_account=tenant_account,
#                 status__in=['active', 'pending'],
#                 tenant=tenant_account.tenant
#             )
#         except Conversation.DoesNotExist:
#             # Create new conversation
#             conversation = Conversation.objects.create(
#                 tenant=tenant_account.tenant,
#                 customer=customer,
#                 platform=platform,
#                 platform_account=tenant_account,
#                 external_conversation_id=f"{platform.name}_{customer.external_id}_{uuid.uuid4().hex[:8]}",
#                 conversation_type='direct_message',
#                 current_handler_type='ai',  # Start with AI handling
#                 ai_enabled=True,
#                 status='active',
#                 first_message_at=timezone.now(),
#                 last_message_at=timezone.now()
#             )
        
#         # Update last message timestamp
#         conversation.last_message_at = timezone.now()
#         conversation.save(update_fields=['last_message_at'])
        
#         return conversation
    
#     @sync_to_async
#     def _create_message(self, tenant, conversation, external_message_id, content, 
#                        sender_type, direction, customer, timestamp):
#         # Convert timestamp if provided
#         if timestamp:
#             try:
#                 platform_timestamp = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc)
#             except (ValueError, TypeError):
#                 platform_timestamp = timezone.now()
#         else:
#             platform_timestamp = timezone.now()
            
#         message = Message.objects.create(
#             tenant=tenant,
#             conversation=conversation,
#             external_message_id=external_message_id or f"{sender_type}_{uuid.uuid4().hex[:16]}",
#             message_type='text',
#             direction=direction,
#             sender_type=sender_type,
#             sender_id=customer.id if sender_type == 'customer' else None,
#             sender_name=customer.platform_display_name or customer.platform_username,
#             content_encrypted=content,  # Add encryption in production
#             content_hash=str(hash(content)),
#             delivery_status='delivered',
#             platform_timestamp=platform_timestamp,
#             ai_processed=False
#         )
        
#         return message
    
#     @sync_to_async
#     def _should_ai_handle_conversation(self, conversation):
#         """Check if AI should handle this conversation"""
#         # Check if conversation is assigned to human
#         if conversation.assigned_user_id:
#             return False
            
#         # Check if AI is paused
#         if conversation.ai_paused_by_user_id:
#             return False
            
#         # Check if AI is enabled for this conversation
#         if not conversation.ai_enabled:
#             return False
            
#         # Check tenant AI settings
#         try:
#             ai_settings = TenantAISetting.objects.get(
#                 tenant=conversation.tenant,
#                 platform=conversation.platform
#             )
#             return ai_settings.auto_response_enabled
#         except TenantAISetting.DoesNotExist:
#             return True  # Default to AI handling
    
#     async def _send_to_rag_processor(self, conversation_id, message_text):
#         """Send message to RAG processor via WebSocket"""
#         try:
#             # Send to the QA WebSocket consumer
#             await channel_layer.group_send(
#                 f"rag_processor_{conversation_id}",
#                 {
#                     'type': 'process_message',
#                     'message': message_text,
#                     'conversation_id': str(conversation_id)
#                 }
#             )
#         except Exception as e:
#             logger.error(f"Error sending to RAG processor: {e}")
    
#     async def _notify_human_agents(self, conversation_id, message):
#         """Notify human agents about new message"""
#         try:
#             await channel_layer.group_send(
#                 f"conversation_{conversation_id}",
#                 {
#                     'type': 'new_message',
#                     'message': {
#                         'id': str(message.id),
#                         'content': message.content_encrypted,
#                         'sender_type': message.sender_type,
#                         'timestamp': message.created_at.isoformat()
#                     }
#                 }
#             )
#         except Exception as e:
#             logger.error(f"Error notifying human agents: {e}")

# # Add mixin to webhook views
# class FacebookWebhookView(FacebookWebhookView, WebhookMixin):
#     pass

# class WhatsAppWebhookView(WhatsAppWebhookView, WebhookMixin):
#     pass


# # Response utility functions for sending messages back to platforms
# import requests

# class PlatformMessenger:
#     """Utility class for sending messages to different platforms"""
    
#     @staticmethod
#     async def send_facebook_message(recipient_id, message_text, tenant_account):
#         """Send message via Facebook Messenger API"""
#         try:
#             # Decrypt access token in production
#             access_token = tenant_account.access_token_encrypted
            
#             url = "https://graph.facebook.com/v19.0/me/messages"
#             headers = {"Content-Type": "application/json"}
#             params = {"access_token": access_token}
#             payload = {
#                 "recipient": {"id": recipient_id},
#                 "message": {"text": message_text},
#             }
            
#             response = requests.post(url, headers=headers, json=payload, params=params)
#             response.raise_for_status()
            
#             logger.info(f"Facebook message sent to {recipient_id}")
#             return True
            
#         except Exception as e:
#             logger.error(f"Error sending Facebook message: {e}")
#             return False
    
#     @staticmethod
#     async def send_whatsapp_message(recipient_id, message_text, tenant_account):
#         """Send message via WhatsApp Business API"""
#         try:
#             # Decrypt access token in production
#             access_token = tenant_account.access_token_encrypted
#             phone_number_id = tenant_account.account_settings.get('phone_number_id')
            
#             if not phone_number_id:
#                 logger.error("Phone number ID not configured for WhatsApp account")
#                 return False
            
#             url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
#             headers = {"Content-Type": "application/json"}
#             params = {"access_token": access_token}
#             payload = {
#                 "messaging_product": "whatsapp",
#                 "recipient_type": "individual", 
#                 "to": recipient_id,
#                 "type": "text",
#                 "text": {"body": message_text}
#             }
            
#             response = requests.post(url, headers=headers, json=payload, params=params)
#             response.raise_for_status()
            
#             logger.info(f"WhatsApp message sent to {recipient_id}")
#             return True
            
#         except Exception as e:
#             logger.error(f"Error sending WhatsApp message: {e}")
#             return False



# platforms/webhook_views.py
import json
import hashlib
import hmac
import asyncio
from datetime import datetime
from typing import Optional

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.utils.decorators import method_decorator
from django.views import View
from django.conf import settings
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync, sync_to_async

from .models import SocialPlatform, TenantPlatformAccount
from tenants.models import Tenant
from customers.models import Customer
from conversations.models import Conversation, Message
from conversations.notification_utils import DashboardNotifier
from ai.models import TenantAISetting
import uuid
import logging
import requests
import aiohttp

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()

class FacebookWebhookView(View):
    """Handle Facebook Messenger webhook verification and messages"""
    
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
    
    def get(self, request):
        """Webhook verification for Facebook"""
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        
        try:
            facebook_platform = SocialPlatform.objects.get(name='facebook')
            facebook_account = TenantPlatformAccount.objects.filter(
                platform=facebook_platform
            ).first()
            
            if not facebook_account:
                logger.error("No Facebook account configured for webhook verification")
                return HttpResponse("No Facebook account configured", status=403)
                
            verify_token = settings.FACEBOOK_VERIFY_TOKEN
            
        except SocialPlatform.DoesNotExist:
            logger.error("Facebook platform not found in database")
            return HttpResponse("Platform not configured", status=500)
            
        if mode == 'subscribe' and token == verify_token:
            logger.info("Facebook webhook verified successfully")
            return HttpResponse(challenge)
        else:
            logger.warning("Facebook webhook verification failed")
            return HttpResponse("Verification failed", status=403)
    
    def post(self, request):
        """Handle incoming Facebook messages"""
        try:
            payload = json.loads(request.body)
            logger.info(f"Facebook webhook payload: {json.dumps(payload, indent=2)}")
            
            if payload.get('object') == 'page':
                for entry in payload.get('entry', []):
                    page_id = entry.get('id')
                    
                    for messaging_event in entry.get('messaging', []):
                        if 'message' in messaging_event:
                            asyncio.create_task(
                                self._process_facebook_message(messaging_event, page_id)
                            )
            
            return JsonResponse({'status': 'success'})
            
        except Exception as e:
            logger.error(f"Error processing Facebook webhook: {e}")
            return JsonResponse({'error': 'Processing failed'}, status=500)
    
    async def _process_facebook_message(self, messaging_event, page_id):
        """Process individual Facebook message"""
        try:
            sender_id = messaging_event['sender']['id']
            message_text = messaging_event['message'].get('text', '')
            message_id = messaging_event['message'].get('mid')
            timestamp = messaging_event.get('timestamp')
            
            if not message_text:
                return
                
            facebook_platform = await sync_to_async(SocialPlatform.objects.get)(name='facebook')
            tenant_account = await sync_to_async(TenantPlatformAccount.objects.select_related('tenant').get)(
                platform_account_id=page_id,
                platform=facebook_platform,
                connection_status='active'
            )
            
            if not tenant_account:
                logger.error(f"No tenant account found for Facebook page {page_id}")
                return
                
            customer = await self._get_or_create_customer(
                sender_id, tenant_account, facebook_platform
            )
            
            conversation = await self._get_or_create_conversation(
                customer, tenant_account, facebook_platform
            )
            
            user_message = await self._create_message(
                tenant_account.tenant,
                conversation,
                message_id,
                message_text,
                'customer',
                'inbound',
                customer,
                timestamp
            )
            
            # Send real-time notification
            DashboardNotifier.notify_new_message(user_message, conversation)
            
            should_ai_handle = await self._should_ai_handle_conversation(conversation)
            
            if should_ai_handle:
                await self._send_to_rag_processor(conversation.id, message_text)
            else:
                await self._notify_human_agents(conversation.id, user_message)
                
        except Exception as e:
            logger.error(f"Error processing Facebook message: {e}")


class WhatsAppWebhookView(View):
    """Handle WhatsApp Business API webhook verification and messages"""
    
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
    
    def get(self, request):
        """Webhook verification for WhatsApp"""
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        
        verify_token = settings.WHATSAPP_VERIFY_TOKEN
        
        if mode == 'subscribe' and token == verify_token:
            logger.info("WhatsApp webhook verified successfully")
            return HttpResponse(challenge)
        else:
            logger.warning("WhatsApp webhook verification failed")
            return HttpResponse("Verification failed", status=403)
    
    def post(self, request):
        """Handle incoming WhatsApp messages"""
        try:
            payload = json.loads(request.body)
            logger.info(f"WhatsApp webhook payload: {json.dumps(payload, indent=2)}")
            
            if payload.get('object') == 'whatsapp_business_account':
                for entry in payload.get('entry', []):
                    for change in entry.get('changes', []):
                        if change.get('field') == 'messages':
                            waba_id = entry.get('id')
                            
                            for message in change.get('value', {}).get('messages', []):
                                if message.get('type') == 'text':
                                    asyncio.create_task(
                                        self._process_whatsapp_message(message, waba_id)
                                    )
            
            return JsonResponse({'status': 'success'})
            
        except Exception as e:
            logger.error(f"Error processing WhatsApp webhook: {e}")
            return JsonResponse({'error': 'Processing failed'}, status=500)
    
    async def _process_whatsapp_message(self, message, waba_id):
        """Process individual WhatsApp message"""
        try:
            sender_id = message.get('from')
            message_text = message.get('text', {}).get('body', '')
            message_id = message.get('id')
            timestamp = message.get('timestamp')
            
            if not message_text:
                return
                
            whatsapp_platform = await sync_to_async(SocialPlatform.objects.get)(name='whatsapp')
            tenant_account = await sync_to_async(TenantPlatformAccount.objects.select_related('tenant').get)(
                platform_account_id=waba_id,
                platform=whatsapp_platform,
                connection_status='active'
            )
            
            if not tenant_account:
                logger.error(f"No tenant account found for WhatsApp Business Account {waba_id}")
                return
                
            customer = await self._get_or_create_customer(
                sender_id, tenant_account, whatsapp_platform
            )
            
            conversation = await self._get_or_create_conversation(
                customer, tenant_account, whatsapp_platform
            )
            
            user_message = await self._create_message(
                tenant_account.tenant,
                conversation,
                message_id,
                message_text,
                'customer',
                'inbound',
                customer,
                timestamp
            )
            
            # Send real-time notification
            DashboardNotifier.notify_new_message(user_message, conversation)
            
            should_ai_handle = await self._should_ai_handle_conversation(conversation)
            
            if should_ai_handle:
                await self._send_to_rag_processor(conversation.id, message_text)
            else:
                await self._notify_human_agents(conversation.id, user_message)
                
        except Exception as e:
            logger.error(f"Error processing WhatsApp message: {e}")

    @sync_to_async
    def _get_or_create_customer(self, external_id, tenant_account, platform):
        customer, created = Customer.objects.get_or_create(
            external_id=external_id,
            platform=platform,
            platform_account=tenant_account,
            tenant=tenant_account.tenant,
            defaults={
                'platform_username': external_id,
                'first_contact_at': timezone.now(),
                'last_contact_at': timezone.now(),
                'last_seen_at': timezone.now(),
                'status': 'active'
            }
        )
        
        if not created:
            customer.last_contact_at = timezone.now()
            customer.last_seen_at = timezone.now()
            customer.save(update_fields=['last_contact_at', 'last_seen_at'])
            
        return customer
    
    @sync_to_async
    def _get_or_create_conversation(self, customer, tenant_account, platform):
        try:
            conversation = Conversation.objects.get(
                customer=customer,
                platform=platform,
                platform_account=tenant_account,
                status__in=['active', 'pending'],
                tenant=tenant_account.tenant
            )
        except Conversation.DoesNotExist:
            conversation = Conversation.objects.create(
                tenant=tenant_account.tenant,
                customer=customer,
                platform=platform,
                platform_account=tenant_account,
                external_conversation_id=f"{platform.name}_{customer.external_id}_{uuid.uuid4().hex[:8]}",
                conversation_type='direct_message',
                current_handler_type='ai',
                ai_enabled=True,
                status='active',
                priority='normal',
                first_message_at=timezone.now(),
                last_message_at=timezone.now()
            )
        
        conversation.last_message_at = timezone.now()
        conversation.save(update_fields=['last_message_at'])
        
        return conversation
    
    @sync_to_async
    def _create_message(self, tenant, conversation, external_message_id, content, 
                       sender_type, direction, customer, timestamp):
        if timestamp:
            try:
                platform_timestamp = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc)
            except (ValueError, TypeError):
                platform_timestamp = timezone.now()
        else:
            platform_timestamp = timezone.now()
            
        message = Message.objects.create(
            tenant=tenant,
            conversation=conversation,
            external_message_id=external_message_id or f"{sender_type}_{uuid.uuid4().hex[:16]}",
            message_type='text',
            direction=direction,
            sender_type=sender_type,
            sender_id=customer.id if sender_type == 'customer' else None,
            sender_name=customer.platform_display_name or customer.platform_username,
            content_encrypted=content,
            content_hash=str(hash(content)),
            delivery_status='delivered',
            platform_timestamp=platform_timestamp,
            ai_processed=False
        )
        
        return message
    
    @sync_to_async
    def _should_ai_handle_conversation(self, conversation):
        if conversation.assigned_user_id:
            return False
        if conversation.ai_paused_by_user_id:
            return False
        if not conversation.ai_enabled:
            return False
            
        try:
            ai_settings = TenantAISetting.objects.get(
                tenant=conversation.tenant,
                platform=conversation.platform
            )
            return ai_settings.auto_response_enabled
        except TenantAISetting.DoesNotExist:
            return True
    
    async def _send_to_rag_processor(self, conversation_id, message_text):
        try:
            await channel_layer.group_send(
                f"rag_processor_{conversation_id}",
                {
                    'type': 'process_message',
                    'message': message_text,
                    'conversation_id': str(conversation_id)
                }
            )
        except Exception as e:
            logger.error(f"Error sending to RAG processor: {e}")
    
    async def _notify_human_agents(self, conversation_id, message):
        try:
            await channel_layer.group_send(
                f"conversation_{conversation_id}",
                {
                    'type': 'new_message',
                    'message': {
                        'id': str(message.id),
                        'content': message.content_encrypted,
                        'sender_type': message.sender_type,
                        'timestamp': message.created_at.isoformat()
                    }
                }
            )
        except Exception as e:
            logger.error(f"Error notifying human agents: {e}")


# Platform messaging utility
class PlatformMessenger:
    """Utility class for sending messages to different platforms"""
    
    @staticmethod
    async def send_facebook_message(recipient_id, message_text, tenant_account):
        """Send message via Facebook Messenger API"""
        try:
            access_token = tenant_account.access_token_encrypted
            
            url = "https://graph.facebook.com/v19.0/me/messages"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}"
            }
            payload = {
                "recipient": {"id": recipient_id},
                "message": {"text": message_text},
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        logger.info(f"Facebook message sent to {recipient_id}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Facebook API error {response.status}: {error_text}")
                        return False
            
        except Exception as e:
            logger.error(f"Error sending Facebook message: {e}")
            return False
    
    @staticmethod
    async def send_whatsapp_message(recipient_id, message_text, tenant_account):
        """Send message via WhatsApp Business API"""
        try:
            access_token = tenant_account.access_token_encrypted
            phone_number_id = tenant_account.account_settings.get('phone_number_id')
            
            if not phone_number_id:
                logger.error("Phone number ID not configured for WhatsApp account")
                return False
            
            url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}"
            }
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual", 
                "to": recipient_id,
                "type": "text",
                "text": {"body": message_text}
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        message_id = response_data.get('messages', [{}])[0].get('id')
                        logger.info(f"WhatsApp message sent to {recipient_id}, message_id: {message_id}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"WhatsApp API error {response.status}: {error_text}")
                        return False
            
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
            return False