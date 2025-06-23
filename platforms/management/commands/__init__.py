# conversations/utils.py
import re
from typing import List, Dict, Optional, Tuple
from django.utils import timezone
from django.db.models import Q
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer

from .models import Conversation, Message
from customers.models import Customer
from ai.models import TenantAISetting, AIIntentCategory, AISentimentRange
from tenants.models import TenantUser
import logging

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()

class HandoverManager:
    """Manages AI to human handover logic and context preservation"""
    
    @staticmethod
    async def should_trigger_handover(conversation: Conversation, message_content: str, 
                                    sentiment_score: float = None, intent: str = None) -> Tuple[bool, str]:
        """
        Determine if conversation should be handed over to human agent
        Returns: (should_handover: bool, reason: str)
        """
        ai_settings = await sync_to_async(TenantAISetting.objects.get)(
            tenant=conversation.tenant,
            platform=conversation.platform
        )
        
        handover_triggers = ai_settings.handover_triggers or {}
        
        # Check escalation keywords
        escalation_keywords = ai_settings.escalation_keywords or []
        for keyword in escalation_keywords:
            if keyword.lower() in message_content.lower():
                return True, f"Escalation keyword detected: {keyword}"
        
        # Check blocked topics
        blocked_topics = ai_settings.blocked_topics or []
        for topic in blocked_topics:
            if topic.lower() in message_content.lower():
                return True, f"Blocked topic detected: {topic}"
        
        # Check sentiment threshold
        if sentiment_score is not None:
            sentiment_threshold = handover_triggers.get('negative_sentiment_threshold', -0.7)
            if sentiment_score <= sentiment_threshold:
                return True, f"Negative sentiment threshold exceeded: {sentiment_score}"
        
        # Check for specific intents that require human intervention
        high_priority_intents = handover_triggers.get('priority_intents', ['complaint', 'refund_request'])
        if intent in high_priority_intents:
            return True, f"High priority intent detected: {intent}"
        
        # Check for consecutive unresolved messages
        consecutive_limit = handover_triggers.get('consecutive_unresolved_limit', 3)
        consecutive_count = await HandoverManager._count_consecutive_unresolved(conversation)
        if consecutive_count >= consecutive_limit:
            return True, f"Too many consecutive unresolved messages: {consecutive_count}"
        
        # Check for explicit human agent requests
        agent_request_patterns = [
            r'\b(speak|talk)\s+to\s+(human|agent|person|representative)\b',
            r'\b(human|agent|person|representative)\s+please\b',
            r'\bcan\s+i\s+(speak|talk)\s+to\s+someone\b',
            r'\btransfer\s+me\s+to\s+(human|agent)\b'
        ]
        
        for pattern in agent_request_patterns:
            if re.search(pattern, message_content.lower()):
                return True, "Customer requested human agent"
        
        return False, ""
    
    @staticmethod
    async def _count_consecutive_unresolved(conversation: Conversation) -> int:
        """Count consecutive messages where AI couldn't provide satisfactory response"""
        recent_messages = await sync_to_async(list)(
            Message.objects.filter(
                conversation=conversation,
                sender_type='customer'
            ).order_by('-created_at')[:5]
        )
        
        # Simple heuristic: if customer sends multiple short messages in succession,
        # it might indicate AI responses aren't helpful
        consecutive_count = 0
        for msg in recent_messages:
            if len(msg.content_encrypted.split()) <= 3:  # Short message
                consecutive_count += 1
            else:
                break
                
        return consecutive_count
    
    @staticmethod
    async def initiate_handover(conversation: Conversation, reason: str, 
                              assigned_user: TenantUser = None) -> bool:
        """
        Initiate handover from AI to human agent
        """
        try:
            # Update conversation
            conversation.current_handler_type = 'human'
            conversation.handover_reason = reason
            conversation.ai_enabled = False
            
            if assigned_user:
                conversation.assigned_user_id = assigned_user.id
            else:
                # Auto-assign to available agent (implement your logic here)
                available_agent = await HandoverManager._find_available_agent(conversation.tenant)
                if available_agent:
                    conversation.assigned_user_id = available_agent.id
            
            await sync_to_async(conversation.save)(
                update_fields=['current_handler_type', 'handover_reason', 'ai_enabled', 'assigned_user_id']
            )
            
            # Create handover notification message
            await HandoverManager._create_handover_notification(conversation, reason)
            
            # Notify monitoring systems
            await HandoverManager._notify_handover(conversation, reason)
            
            logger.info(f"Handover initiated for conversation {conversation.id}: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initiate handover for conversation {conversation.id}: {e}")
            return False
    
    @staticmethod
    async def _find_available_agent(tenant) -> Optional[TenantUser]:
        """Find available human agent for assignment"""
        # Simple round-robin assignment - implement more sophisticated logic as needed
        agents = await sync_to_async(list)(
            TenantUser.objects.filter(
                tenant=tenant,
                role__in=['agent', 'admin'],
                is_active=True
            ).order_by('last_login')
        )
        
        if agents:
            return agents[0]
        return None
    
    @staticmethod
    async def _create_handover_notification(conversation: Conversation, reason: str):
        """Create a system message indicating handover"""
        await sync_to_async(Message.objects.create)(
            tenant=conversation.tenant,
            conversation=conversation,
            external_message_id=f"system_handover_{timezone.now().timestamp()}",
            message_type='system',
            direction='internal',
            sender_type='system',
            sender_name='System',
            content_encrypted=f"Conversation handed over to human agent. Reason: {reason}",
            content_hash=str(hash(reason)),
            delivery_status='delivered',
            platform_timestamp=timezone.now()
        )
    
    @staticmethod
    async def _notify_handover(conversation: Conversation, reason: str):
        """Notify monitoring dashboard about handover"""
        try:
            await channel_layer.group_send(
                f"conversation_{conversation.id}",
                {
                    'type': 'handover_notification',
                    'conversation_id': str(conversation.id),
                    'reason': reason,
                    'timestamp': timezone.now().isoformat()
                }
            )
        except Exception as e:
            logger.error(f"Failed to notify handover: {e}")


class ConversationContextManager:
    """Manages conversation context and state across platform interactions"""
    
    @staticmethod
    async def prepare_context_summary(conversation: Conversation) -> Dict:
        """Prepare context summary for human agents taking over"""
        try:
            # Get conversation history
            messages = await sync_to_async(list)(
                Message.objects.filter(
                    conversation=conversation
                ).order_by('created_at')
            )
            
            # Get customer info
            customer = conversation.customer
            
            # Analyze conversation patterns
            message_stats = {
                'total_messages': len(messages),
                'customer_messages': len([m for m in messages if m.sender_type == 'customer']),
                'ai_messages': len([m for m in messages if m.sender_type == 'ai']),
                'human_messages': len([m for m in messages if m.sender_type == 'human'])
            }
            
            # Get recent AI analysis
            recent_ai_messages = [m for m in messages if m.sender_type == 'ai'][-5:]
            ai_insights = []
            for msg in recent_ai_messages:
                if hasattr(msg, 'ai_intent') and msg.ai_intent:
                    ai_insights.append({
                        'intent': msg.ai_intent,
                        'confidence': msg.ai_confidence,
                        'sentiment': msg.ai_sentiment
                    })
            
            # Prepare summary
            context_summary = {
                'conversation_id': str(conversation.id),
                'customer': {
                    'id': str(customer.id),
                    'name': customer.platform_display_name or customer.platform_username,
                    'platform': conversation.platform.display_name,
                    'first_contact': customer.first_contact_at.isoformat() if customer.first_contact_at else None,
                    'total_conversations': await sync_to_async(
                        Conversation.objects.filter(customer=customer).count
                    )()
                },
                'conversation': {
                    'started_at': conversation.created_at.isoformat(),
                    'last_message_at': conversation.last_message_at.isoformat() if conversation.last_message_at else None,
                    'status': conversation.status,
                    'handover_reason': conversation.handover_reason
                },
                'message_stats': message_stats,
                'ai_insights': ai_insights,
                'recent_messages': [
                    {
                        'content': m.content_encrypted,
                        'sender_type': m.sender_type,
                        'timestamp': m.created_at.isoformat()
                    }
                    for m in messages[-10:]  # Last 10 messages
                ]
            }
            
            return context_summary
            
        except Exception as e:
            logger.error(f"Failed to prepare context summary: {e}")
            return {}
    
    @staticmethod
    async def update_customer_insights(customer: Customer, conversation: Conversation):
        """Update customer insights based on conversation"""
        try:
            from customers.models import ContactInsights
            
            # Get or create insights record
            insights, created = await sync_to_async(ContactInsights.objects.get_or_create)(
                tenant=customer.tenant,
                customer=customer,
                defaults={
                    'total_messages': 0,
                    'messages_sent': 0,
                    'messages_received': 0,
                    'avg_response_time_seconds': 0,
                    'sentiment_trend': 'neutral',
                    'insights_generated_at': timezone.now()
                }
            )
            
            # Count messages
            message_counts = await sync_to_async(
                Message.objects.filter(conversation__customer=customer).aggregate
            )(
                total=models.Count('id'),
                sent=models.Count('id', filter=Q(sender_type='customer')),
                received=models.Count('id', filter=Q(sender_type__in=['ai', 'human']))
            )
            
            # Update insights
            insights.total_messages = message_counts['total'] or 0
            insights.messages_sent = message_counts['sent'] or 0
            insights.messages_received = message_counts['received'] or 0
            insights.last_engagement_score_update = timezone.now()
            insights.insights_generated_at = timezone.now()
            
            await sync_to_async(insights.save)()
            
        except Exception as e:
            logger.error(f"Failed to update customer insights: {e}")


class BusinessHoursManager:
    """Manages business hours and AI availability"""
    
    @staticmethod
    def is_within_business_hours(ai_settings: TenantAISetting) -> bool:
        """Check if current time is within configured business hours"""
        if not ai_settings.business_hours:
            return True  # If no business hours configured, assume always available
        
        current_time = timezone.now()
        current_day = current_time.strftime('%A').lower()
        current_hour = current_time.hour
        current_minute = current_time.minute
        current_time_minutes = current_hour * 60 + current_minute
        
        business_hours = ai_settings.business_hours
        day_config = business_hours.get(current_day)
        
        if not day_config or not day_config.get('enabled', True):
            return False
        
        start_time = day_config.get('start', '09:00')
        end_time = day_config.get('end', '17:00')
        
        try:
            start_hour, start_minute = map(int, start_time.split(':'))
            end_hour, end_minute = map(int, end_time.split(':'))
            
            start_minutes = start_hour * 60 + start_minute
            end_minutes = end_hour * 60 + end_minute
            
            return start_minutes <= current_time_minutes <= end_minutes
            
        except (ValueError, AttributeError):
            return True  # If parsing fails, assume available
    
    @staticmethod
    async def get_out_of_hours_message(ai_settings: TenantAISetting) -> str:
        """Get out of hours auto-response message"""
        business_hours = ai_settings.business_hours or {}
        default_message = ("Thank you for your message. We're currently outside of business hours. "
                         "We'll respond to your message as soon as possible during our next business day.")
        
        return business_hours.get('out_of_hours_message', default_message)


from django.db import models