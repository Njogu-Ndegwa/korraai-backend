# views.py
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from .models import TenantAISettings
from platforms.models import SocialPlatform, TenantPlatformAccount
from .serializers import (
    AISettingsListSerializer, AISettingsDetailSerializer,
    AISettingsUpdateSerializer, AISettingsTestSerializer,
    PlatformAISettingsSerializer
)
import json
import random
import time
# views.py
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.db.models import Count, Avg, Q
from datetime import timedelta, date
from .models import AIIntentCategory, Message, Conversation, TenantUser
from .serializers import (
    IntentCategoryListSerializer, IntentCategoryDetailSerializer,
    IntentCategoryCreateUpdateSerializer, IntentAnalyticsSerializer,
    IntentAutoActionsSerializer
)



@api_view(['GET', 'PUT'])
def ai_settings(request):
    """
    GET /api/ai/settings - Get AI configuration settings
    PUT /api/ai/settings - Update AI configuration
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    if request.method == 'GET':
        # Get all AI settings for the tenant across all platforms
        ai_settings = TenantAISettings.objects.filter(
            tenant_id=tenant_id
        ).select_related('platform').order_by('platform__display_name')
        
        # If no settings exist, create default ones for connected platforms
        if not ai_settings.exists():
            connected_platforms = TenantPlatformAccount.objects.filter(
                tenant_id=tenant_id,
                connection_status='active'
            ).values_list('platform_id', flat=True)
            
            for platform_id in connected_platforms:
                TenantAISettings.objects.get_or_create(
                    tenant_id=tenant_id,
                    platform_id=platform_id,
                    defaults={
                        'system_prompt': 'You are a helpful AI assistant.',
                        'auto_response_enabled': False,
                        'response_delay_seconds': 2,
                        'confidence_threshold': 0.8,
                        'knowledge_base_enabled': True,
                        'max_knowledge_chunks': 5,
                        'similarity_threshold': 0.7,
                        'business_hours': _get_default_business_hours(),
                        'escalation_keywords': ['human', 'agent', 'manager', 'escalate'],
                        'blocked_topics': [],
                        'handover_triggers': _get_default_handover_triggers()
                    }
                )
            
            # Refresh queryset
            ai_settings = TenantAISettings.objects.filter(
                tenant_id=tenant_id
            ).select_related('platform').order_by('platform__display_name')
        
        serializer = AISettingsListSerializer(ai_settings, many=True)
        
        # Add summary statistics
        total_settings = ai_settings.count()
        enabled_auto_response = ai_settings.filter(auto_response_enabled=True).count()
        enabled_knowledge_base = ai_settings.filter(knowledge_base_enabled=True).count()
        
        response_data = {
            'results': serializer.data,
            'summary': {
                'total_platforms': total_settings,
                'auto_response_enabled': enabled_auto_response,
                'knowledge_base_enabled': enabled_knowledge_base,
                'avg_confidence_threshold': ai_settings.aggregate(
                    avg=models.Avg('confidence_threshold')
                )['avg'] or 0.0
            }
        }
        
        return Response(response_data)
    
    elif request.method == 'PUT':
        # Update settings for all platforms (bulk update)
        serializer = AISettingsUpdateSerializer(data=request.data)
        
        if serializer.is_valid():
            validated_data = serializer.validated_data
            
            with transaction.atomic():
                # Update all AI settings for the tenant
                updated_count = TenantAISettings.objects.filter(
                    tenant_id=tenant_id
                ).update(**validated_data, updated_at=timezone.now())
                
                if updated_count == 0:
                    return Response(
                        {'error': 'No AI settings found to update.'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            
            # Return updated settings
            ai_settings = TenantAISettings.objects.filter(
                tenant_id=tenant_id
            ).select_related('platform')
            
            response_serializer = AISettingsListSerializer(ai_settings, many=True)
            return Response({
                'message': f'Updated AI settings for {updated_count} platform(s).',
                'settings': response_serializer.data
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT'])
def platform_ai_settings(request, platform_id):
    """
    GET /api/ai/settings/platform/{platform_id} - Get platform-specific AI settings
    PUT /api/ai/settings/platform/{platform_id} - Update platform-specific AI settings
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    # Verify platform exists
    platform = get_object_or_404(SocialPlatform, id=platform_id)
    
    # Get or create AI settings for this platform
    ai_settings, created = TenantAISettings.objects.get_or_create(
        tenant_id=tenant_id,
        platform_id=platform_id,
        defaults={
            'system_prompt': f'You are a helpful AI assistant for {platform.display_name}.',
            'auto_response_enabled': False,
            'response_delay_seconds': 2,
            'confidence_threshold': 0.8,
            'knowledge_base_enabled': True,
            'max_knowledge_chunks': 5,
            'similarity_threshold': 0.7,
            'business_hours': _get_default_business_hours(),
            'escalation_keywords': ['human', 'agent', 'manager', 'escalate'],
            'blocked_topics': [],
            'handover_triggers': _get_default_handover_triggers()
        }
    )
    
    if request.method == 'GET':
        serializer = PlatformAISettingsSerializer(ai_settings)
        
        response_data = serializer.data
        if created:
            response_data['_meta'] = {
                'message': 'Default AI settings created for this platform.',
                'created': True
            }
        
        return Response(response_data)
    
    elif request.method == 'PUT':
        serializer = AISettingsUpdateSerializer(ai_settings, data=request.data, partial=True)
        
        if serializer.is_valid():
            with transaction.atomic():
                updated_settings = serializer.save()
            
            # Return updated settings
            response_serializer = PlatformAISettingsSerializer(updated_settings)
            return Response({
                'message': f'AI settings updated for {platform.display_name}.',
                'settings': response_serializer.data
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def test_ai_settings(request):
    """
    POST /api/ai/settings/test - Test AI configuration
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    serializer = AISettingsTestSerializer(
        data=request.data,
        context={'tenant_id': tenant_id}
    )
    
    if serializer.is_valid():
        test_message = serializer.validated_data['test_message']
        include_knowledge_base = serializer.validated_data['include_knowledge_base']
        test_type = serializer.validated_data['test_type']
        platform_id = serializer.validated_data.get('platform_id')
        
        # Get AI settings
        if platform_id:
            try:
                ai_settings = TenantAISettings.objects.get(
                    tenant_id=tenant_id,
                    platform_id=platform_id
                )
            except TenantAISettings.DoesNotExist:
                return Response(
                    {'error': 'AI settings not found for specified platform.'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # Use first available AI settings
            ai_settings = TenantAISettings.objects.filter(
                tenant_id=tenant_id
            ).first()
            
            if not ai_settings:
                return Response(
                    {'error': 'No AI settings configured.'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Simulate AI processing (replace with actual AI service calls)
        test_results = _simulate_ai_test(
            test_message, test_type, ai_settings, include_knowledge_base
        )
        
        response_data = {
            'test_input': {
                'message': test_message,
                'test_type': test_type,
                'include_knowledge_base': include_knowledge_base,
                'platform_id': platform_id,
                'platform_name': ai_settings.platform.display_name if ai_settings.platform else None
            },
            'ai_settings_used': {
                'confidence_threshold': ai_settings.confidence_threshold,
                'knowledge_base_enabled': ai_settings.knowledge_base_enabled,
                'system_prompt_length': len(ai_settings.system_prompt or ''),
                'response_delay_seconds': ai_settings.response_delay_seconds
            },
            'test_results': test_results,
            'timestamp': timezone.now()
        }
        
        return Response(response_data)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


def _get_default_business_hours():
    """Get default business hours configuration"""
    default_weekday = {
        'enabled': True,
        'start': '09:00',
        'end': '17:00'
    }
    default_weekend = {
        'enabled': False,
        'start': '09:00',
        'end': '17:00'
    }
    
    return {
        'monday': default_weekday.copy(),
        'tuesday': default_weekday.copy(),
        'wednesday': default_weekday.copy(),
        'thursday': default_weekday.copy(),
        'friday': default_weekday.copy(),
        'saturday': default_weekend.copy(),
        'sunday': default_weekend.copy()
    }


def _get_default_handover_triggers():
    """Get default handover triggers configuration"""
    return {
        'low_confidence': {
            'enabled': True,
            'threshold': 0.6
        },
        'escalation_keywords': {
            'enabled': True,
            'keywords': ['human', 'agent', 'manager']
        },
        'negative_sentiment': {
            'enabled': True,
            'threshold': -0.7
        },
        'multiple_questions': {
            'enabled': False,
            'max_questions': 3
        },
        'custom_rules': {
            'enabled': False,
            'rules': []
        }
    }


def _simulate_ai_test(test_message, test_type, ai_settings, include_knowledge_base):
    """
    Simulate AI processing for testing purposes
    Replace this with actual AI service integration
    """
    # Simulate processing delay
    time.sleep(0.5)
    
    base_confidence = random.uniform(0.6, 0.95)
    
    results = {
        'processing_time_ms': random.randint(200, 800),
        'confidence_score': round(base_confidence, 3),
        'meets_threshold': base_confidence >= ai_settings.confidence_threshold
    }
    
    if test_type == 'intent_detection':
        results.update({
            'detected_intent': 'customer_inquiry',
            'intent_confidence': round(base_confidence, 3),
            'entities': [
                {'entity': 'product', 'value': 'subscription', 'confidence': 0.9}
            ]
        })
    
    elif test_type == 'sentiment_analysis':
        sentiment_score = random.uniform(-1, 1)
        results.update({
            'sentiment_score': round(sentiment_score, 3),
            'sentiment_label': 'positive' if sentiment_score > 0.1 else 'negative' if sentiment_score < -0.1 else 'neutral',
            'emotion_detected': random.choice(['neutral', 'happy', 'frustrated', 'confused'])
        })
    
    elif test_type == 'knowledge_retrieval':
        if include_knowledge_base and ai_settings.knowledge_base_enabled:
            results.update({
                'knowledge_chunks_retrieved': random.randint(1, ai_settings.max_knowledge_chunks),
                'avg_similarity_score': round(random.uniform(0.6, 0.9), 3),
                'chunks_used': random.randint(1, 3),
                'sources': ['FAQ Document 1', 'Policy Document 2']
            })
        else:
            results.update({
                'knowledge_chunks_retrieved': 0,
                'reason': 'Knowledge base disabled or not included in test'
            })
    
    elif test_type == 'full_response':
        results.update({
            'generated_response': f"Based on your message '{test_message[:50]}...', I understand you're asking about our services. How can I help you further?",
            'response_length': random.randint(50, 200),
            'handover_recommended': base_confidence < ai_settings.confidence_threshold,
            'escalation_triggered': any(keyword in test_message.lower() for keyword in ai_settings.escalation_keywords)
        })
        
        if include_knowledge_base and ai_settings.knowledge_base_enabled:
            results['knowledge_used'] = True
            results['knowledge_chunks_count'] = random.randint(1, 3)
        else:
            results['knowledge_used'] = False
    
    # Add any trigger warnings
    warnings = []
    if base_confidence < ai_settings.confidence_threshold:
        warnings.append('Low confidence score - would trigger handover')
    
    if any(keyword in test_message.lower() for keyword in ai_settings.escalation_keywords):
        warnings.append('Escalation keyword detected')
    
    if any(topic in test_message.lower() for topic in ai_settings.blocked_topics):
        warnings.append('Blocked topic detected')
    
    results['warnings'] = warnings
    results['would_auto_respond'] = (
        ai_settings.auto_response_enabled and 
        base_confidence >= ai_settings.confidence_threshold and 
        not warnings
    )
    
    return results


@api_view(['GET', 'POST'])
def intent_list_create(request):
    """
    GET /api/ai/intents - List all intent categories
    POST /api/ai/intents - Create custom intent category
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    if request.method == 'GET':
        # Get all intent categories for the tenant
        intents = AIIntentCategory.objects.filter(
            tenant_id=tenant_id
        ).order_by('-priority_score', 'display_name')
        
        # Apply filters
        is_active = request.GET.get('is_active')
        if is_active is not None:
            is_active_bool = is_active.lower() in ('true', '1', 'yes')
            intents = intents.filter(is_active=is_active_bool)
        
        is_system_defined = request.GET.get('is_system_defined')
        if is_system_defined is not None:
            is_system_bool = is_system_defined.lower() in ('true', '1', 'yes')
            intents = intents.filter(is_system_defined=is_system_bool)
        
        # Search filter
        search = request.GET.get('search')
        if search:
            intents = intents.filter(
                Q(intent_key__icontains=search) |
                Q(display_name__icontains=search) |
                Q(description__icontains=search)
            )
        
        # Usage filter (intents used in last X days)
        usage_days = request.GET.get('usage_days')
        if usage_days:
            try:
                days = int(usage_days)
                cutoff_date = timezone.now() - timedelta(days=days)
                used_intent_keys = Message.objects.filter(
                    tenant_id=tenant_id,
                    created_at__gte=cutoff_date,
                    ai_intent__isnull=False
                ).values_list('ai_intent', flat=True).distinct()
                
                intents = intents.filter(intent_key__in=used_intent_keys)
            except ValueError:
                pass
        
        serializer = IntentCategoryListSerializer(intents, many=True)
        
        # Add summary statistics
        total_intents = intents.count()
        active_intents = intents.filter(is_active=True).count()
        custom_intents = intents.filter(is_system_defined=False).count()
        
        # Get most used intents in last 30 days
        thirty_days_ago = timezone.now() - timedelta(days=30)
        most_used = Message.objects.filter(
            tenant_id=tenant_id,
            created_at__gte=thirty_days_ago,
            ai_intent__isnull=False
        ).values('ai_intent').annotate(
            count=Count('id')
        ).order_by('-count')[:5]
        
        response_data = {
            'results': serializer.data,
            'summary': {
                'total_intents': total_intents,
                'active_intents': active_intents,
                'custom_intents': custom_intents,
                'system_intents': total_intents - custom_intents,
                'most_used_intents': list(most_used)
            }
        }
        
        return Response(response_data)
    
    elif request.method == 'POST':
        serializer = IntentCategoryCreateUpdateSerializer(
            data=request.data,
            context={'tenant_id': tenant_id}
        )
        
        if serializer.is_valid():
            with transaction.atomic():
                intent_category = serializer.save(
                    tenant_id=tenant_id,
                    is_system_defined=False  # User-created intents are not system-defined
                )
            
            # Return detailed intent category data
            detail_serializer = IntentCategoryDetailSerializer(intent_category)
            return Response(detail_serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
def intent_detail(request, intent_id):
    """
    GET /api/ai/intents/{intent_id} - Get intent category details
    PUT /api/ai/intents/{intent_id} - Update intent category
    DELETE /api/ai/intents/{intent_id} - Delete custom intent category
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    intent_category = get_object_or_404(
        AIIntentCategory,
        id=intent_id,
        tenant_id=tenant_id
    )
    
    if request.method == 'GET':
        serializer = IntentCategoryDetailSerializer(intent_category)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        # Prevent updating system-defined intents
        if intent_category.is_system_defined:
            return Response(
                {'error': 'Cannot update system-defined intent categories.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = IntentCategoryCreateUpdateSerializer(
            intent_category,
            data=request.data,
            partial=True,
            context={'tenant_id': tenant_id}
        )
        
        if serializer.is_valid():
            with transaction.atomic():
                updated_intent = serializer.save()
            
            # Return updated intent details
            detail_serializer = IntentCategoryDetailSerializer(updated_intent)
            return Response(detail_serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        # Prevent deleting system-defined intents
        if intent_category.is_system_defined:
            return Response(
                {'error': 'Cannot delete system-defined intent categories.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if intent is being used in recent messages
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_usage_count = Message.objects.filter(
            tenant_id=tenant_id,
            ai_intent=intent_category.intent_key,
            created_at__gte=thirty_days_ago
        ).count()
        
        if recent_usage_count > 0:
            return Response(
                {
                    'error': f'Cannot delete intent category. It has been used {recent_usage_count} times in the last 30 days.',
                    'recent_usage_count': recent_usage_count,
                    'suggestion': 'Consider deactivating the intent instead of deleting it.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            intent_category.delete()
        
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
def intent_analytics(request):
    """
    GET /api/ai/intents/analytics - Get intent detection analytics
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    # Get date range parameters
    days = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)
    
    # Get all intents for the tenant
    intents = AIIntentCategory.objects.filter(tenant_id=tenant_id, is_active=True)
    
    # Get intent usage statistics
    intent_usage = Message.objects.filter(
        tenant_id=tenant_id,
        created_at__gte=start_date,
        ai_intent__isnull=False
    ).values('ai_intent').annotate(
        count=Count('id'),
        avg_confidence=Avg('ai_confidence')
    ).order_by('-count')
    
    # Get daily breakdown
    daily_stats = []
    for i in range(days):
        day = (timezone.now() - timedelta(days=i)).date()
        day_messages = Message.objects.filter(
            tenant_id=tenant_id,
            created_at__date=day,
            ai_processed=True
        )
        
        total_processed = day_messages.count()
        with_intent = day_messages.filter(ai_intent__isnull=False).count()
        
        daily_stats.append({
            'date': day,
            'total_processed': total_processed,
            'with_intent_detected': with_intent,
            'detection_rate': round((with_intent / total_processed) * 100, 2) if total_processed > 0 else 0
        })
    
    # Get confidence distribution
    confidence_ranges = {
        'high': (0.8, 1.0),
        'medium': (0.6, 0.8),
        'low': (0.0, 0.6)
    }
    
    confidence_distribution = {}
    for range_name, (min_conf, max_conf) in confidence_ranges.items():
        count = Message.objects.filter(
            tenant_id=tenant_id,
            created_at__gte=start_date,
            ai_confidence__gte=min_conf,
            ai_confidence__lt=max_conf,
            ai_intent__isnull=False
        ).count()
        confidence_distribution[range_name] = count
    
    # Get top performing intents
    top_intents = []
    for usage in intent_usage[:10]:
        intent_key = usage['ai_intent']
        try:
            intent_obj = intents.get(intent_key=intent_key)
            top_intents.append({
                'intent_key': intent_key,
                'display_name': intent_obj.display_name,
                'usage_count': usage['count'],
                'avg_confidence': round(usage['avg_confidence'], 3),
                'color_code': intent_obj.color_code
            })
        except AIIntentCategory.DoesNotExist:
            # Intent might have been deleted
            top_intents.append({
                'intent_key': intent_key,
                'display_name': f'Unknown ({intent_key})',
                'usage_count': usage['count'],
                'avg_confidence': round(usage['avg_confidence'], 3),
                'color_code': '#CCCCCC'
            })
    
    # Get unrecognized patterns (messages without intent)
    total_processed = Message.objects.filter(
        tenant_id=tenant_id,
        created_at__gte=start_date,
        ai_processed=True
    ).count()
    
    without_intent = Message.objects.filter(
        tenant_id=tenant_id,
        created_at__gte=start_date,
        ai_processed=True,
        ai_intent__isnull=True
    ).count()
    
    # Get platform breakdown
    platform_stats = Message.objects.filter(
        tenant_id=tenant_id,
        created_at__gte=start_date,
        ai_intent__isnull=False
    ).values(
        'conversation__platform__display_name'
    ).annotate(
        count=Count('id')
    ).order_by('-count')
    
    analytics_data = {
        'summary': {
            'total_intents': intents.count(),
            'period_days': days,
            'total_messages_processed': total_processed,
            'messages_with_intent': total_processed - without_intent,
            'overall_detection_rate': round(((total_processed - without_intent) / total_processed) * 100, 2) if total_processed > 0 else 0,
            'unrecognized_messages': without_intent
        },
        'daily_breakdown': daily_stats,
        'confidence_distribution': confidence_distribution,
        'top_intents': top_intents,
        'platform_breakdown': list(platform_stats),
        'performance_metrics': {
            'avg_confidence_overall': round(
                Message.objects.filter(
                    tenant_id=tenant_id,
                    created_at__gte=start_date,
                    ai_intent__isnull=False
                ).aggregate(avg=Avg('ai_confidence'))['avg'] or 0, 3
            ),
            'most_confident_intent': top_intents[0] if top_intents else None,
            'least_confident_intent': top_intents[-1] if top_intents else None
        }
    }
    
    return Response(analytics_data)


@api_view(['PUT'])
def intent_auto_actions(request, intent_id):
    """
    PUT /api/ai/intents/{intent_id}/actions - Configure auto-actions for intent
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    intent_category = get_object_or_404(
        AIIntentCategory,
        id=intent_id,
        tenant_id=tenant_id
    )
    
    # Prevent modifying system-defined intents
    if intent_category.is_system_defined:
        return Response(
            {'error': 'Cannot modify auto-actions for system-defined intent categories.'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    serializer = IntentAutoActionsSerializer(data=request.data)
    
    if serializer.is_valid():
        auto_actions = serializer.validated_data['auto_actions']
        
        # Validate referenced entities exist (agents, categories, etc.)
        validation_errors = _validate_auto_action_references(auto_actions, tenant_id)
        if validation_errors:
            return Response(
                {'error': 'Invalid references in auto-actions.', 'details': validation_errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            intent_category.auto_actions = auto_actions
            intent_category.save(update_fields=['auto_actions', 'updated_at'])
        
        # Return updated intent details
        detail_serializer = IntentCategoryDetailSerializer(intent_category)
        return Response({
            'message': 'Auto-actions configured successfully.',
            'intent': detail_serializer.data
        })
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


def _validate_auto_action_references(auto_actions, tenant_id):
    """
    Validate that referenced entities in auto-actions exist
    """
    errors = []
    
    for action_key, action_config in auto_actions.items():
        if not action_config.get('enabled'):
            continue
        
        if action_key == 'assign_agent':
            agent_id = action_config.get('agent_id')
            if agent_id:
                try:
                    TenantUser.objects.get(id=agent_id, tenant_id=tenant_id, is_active=True)
                except TenantUser.DoesNotExist:
                    errors.append(f"Agent with ID {agent_id} not found or inactive.")
        
        elif action_key == 'create_lead':
            category_id = action_config.get('category_id')
            stage_id = action_config.get('stage_id')
            
            if category_id:
                try:
                    from .models import LeadCategory
                    LeadCategory.objects.get(id=category_id, tenant_id=tenant_id, is_active=True)
                except LeadCategory.DoesNotExist:
                    errors.append(f"Lead category with ID {category_id} not found or inactive.")
            
            if stage_id:
                try:
                    from .models import LeadStage
                    LeadStage.objects.get(id=stage_id, tenant_id=tenant_id, is_active=True)
                except LeadStage.DoesNotExist:
                    errors.append(f"Lead stage with ID {stage_id} not found or inactive.")
        
        elif action_key == 'send_template':
            template_id = action_config.get('template_id')
            if template_id:
                # Assuming you have a MessageTemplate model
                try:
                    from .models import MessageTemplate
                    MessageTemplate.objects.get(id=template_id, tenant_id=tenant_id, is_active=True)
                except MessageTemplate.DoesNotExist:
                    errors.append(f"Message template with ID {template_id} not found or inactive.")
        
        elif action_key == 'set_category':
            category_id = action_config.get('category_id')
            if category_id:
                try:
                    from .models import ContactLabel
                    ContactLabel.objects.get(id=category_id, tenant_id=tenant_id)
                except ContactLabel.DoesNotExist:
                    errors.append(f"Contact category with ID {category_id} not found.")
    
    return errors