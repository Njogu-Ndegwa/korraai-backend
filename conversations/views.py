# views.py
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.db.models import Count, Q, Prefetch
from .models import Conversation, Message, MessageReadStatus
from tenants.models import Tenant
from .serializers import (
    ConversationListSerializer, ConversationDetailSerializer,
    ConversationTakeoverSerializer, ConversationAIControlSerializer,     
    MessageListSerializer, MessageDetailSerializer,
    MessageCreateSerializer, MessageReadStatusSerializer
)
import hashlib


@api_view(['GET'])
def conversation_list(request):
    """
    GET /api/conversations - List conversations
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    # Build base queryset with optimizations
    conversations = Conversation.objects.filter(
        tenant_id=tenant_id
    ).select_related(
        'customer', 'platform', 'platform_account', 'lead',
        'lead__lead_stage', 'lead__lead_category'
    ).prefetch_related(
        Prefetch('messages', queryset=Message.objects.order_by('-created_at')[:1])
    ).annotate(
        message_count=Count('messages')
    )
    
    # Apply filters based on query parameters
    status_filter = request.GET.get('status')
    if status_filter:
        conversations = conversations.filter(status=status_filter)
    
    priority_filter = request.GET.get('priority')
    if priority_filter:
        conversations = conversations.filter(priority=priority_filter)
    
    handler_type = request.GET.get('handler_type')
    if handler_type:
        conversations = conversations.filter(current_handler_type=handler_type)
    
    assigned_user = request.GET.get('assigned_user')
    if assigned_user:
        conversations = conversations.filter(assigned_user_id=assigned_user)
    
    ai_enabled = request.GET.get('ai_enabled')
    if ai_enabled is not None:
        ai_enabled_bool = ai_enabled.lower() in ('true', '1', 'yes')
        conversations = conversations.filter(ai_enabled=ai_enabled_bool)
    
    platform_id = request.GET.get('platform')
    if platform_id:
        conversations = conversations.filter(platform_id=platform_id)
    
    # Handle search query
    search = request.GET.get('search')
    if search:
        conversations = conversations.filter(
            Q(subject__icontains=search) |
            Q(customer__platform_username__icontains=search) |
            Q(customer__platform_display_name__icontains=search) |
            Q(external_conversation_id__icontains=search)
        )
    
    # Handle overdue filter
    overdue = request.GET.get('overdue')
    if overdue and overdue.lower() in ('true', '1', 'yes'):
        conversations = conversations.filter(
            response_due_at__lt=timezone.now(),
            status__in=['active', 'pending']
        )
    
    # Apply sorting
    sort_by = request.GET.get('sort_by', '-last_message_at')
    valid_sort_fields = [
        'last_message_at', '-last_message_at',
        'created_at', '-created_at',
        'priority', '-priority',
        'status', '-status',
        'sentiment_score', '-sentiment_score'
    ]
    
    if sort_by in valid_sort_fields:
        conversations = conversations.order_by(sort_by)
    else:
        conversations = conversations.order_by('-last_message_at')
    
    serializer = ConversationListSerializer(conversations, many=True)
    
    # Add metadata about the result set
    response_data = {
        'results': serializer.data,
        'count': conversations.count(),
        'filters_applied': {
            'status': status_filter,
            'priority': priority_filter,
            'handler_type': handler_type,
            'assigned_user': assigned_user,
            'ai_enabled': ai_enabled,
            'platform': platform_id,
            'search': search,
            'overdue': overdue
        }
    }
    
    return Response(response_data)


@api_view(['GET'])
def conversation_detail(request, conversation_id):
    """
    GET /api/conversations/{conversation_id} - Get conversation details
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    conversation = get_object_or_404(
        Conversation.objects.select_related(
            'customer', 'platform', 'platform_account', 'lead',
            'lead__lead_stage', 'lead__lead_category'
        ).prefetch_related(
            'messages'
        ),
        id=conversation_id,
        tenant_id=tenant_id
    )
    
    # Mark messages as read for current user (if user tracking is implemented)
    # This would typically update MessageReadStatus records
    
    serializer = ConversationDetailSerializer(conversation)
    return Response(serializer.data)


@api_view(['POST'])
def conversation_takeover(request, conversation_id):
    """
    POST /api/conversations/{conversation_id}/takeover - Take over conversation from AI
    """
    tenant_id = getattr(request, 'tenant_id', None)
    current_user_id = getattr(request, 'user_id', None)  # Assuming middleware sets this
    
    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
        tenant_id=tenant_id
    )
    
    # Validate current state
    if conversation.current_handler_type == 'human':
        return Response(
            {
                'error': 'Conversation is already being handled by a human agent.',
                'current_handler': conversation.current_handler_type,
                'assigned_user_id': conversation.assigned_user_id
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if conversation.status in ['resolved', 'closed']:
        return Response(
            {
                'error': f'Cannot take over a {conversation.status} conversation.',
                'status': conversation.status
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    serializer = ConversationTakeoverSerializer(data=request.data)
    
    if serializer.is_valid():
        reason = serializer.validated_data.get('reason', 'Manual takeover by agent')
        pause_ai = serializer.validated_data.get('pause_ai', True)
        assign_to_me = serializer.validated_data.get('assign_to_me', True)
        
        with transaction.atomic():
            # Update conversation
            conversation.current_handler_type = 'human'
            conversation.handover_reason = reason
            conversation.last_human_response_at = timezone.now()
            
            if pause_ai:
                conversation.ai_enabled = False
                conversation.ai_paused_at = timezone.now()
                conversation.ai_paused_by_user_id = current_user_id
                conversation.ai_pause_reason = reason
                conversation.can_ai_resume = True
            
            if assign_to_me and current_user_id:
                conversation.assigned_user_id = current_user_id
            
            # Update status if needed
            if conversation.status == 'ai_handling':
                conversation.status = 'active'
            
            conversation.save(update_fields=[
                'current_handler_type', 'handover_reason', 'last_human_response_at',
                'ai_enabled', 'ai_paused_at', 'ai_paused_by_user_id', 'ai_pause_reason',
                'can_ai_resume', 'assigned_user_id', 'status', 'updated_at'
            ])
            
            # Log the takeover event (you might have an audit log system)
            # AuditLog.objects.create(
            #     tenant_id=tenant_id,
            #     user_id=current_user_id,
            #     action_type='conversation_takeover',
            #     resource_type='conversation',
            #     resource_id=conversation.id,
            #     new_values={'reason': reason, 'pause_ai': pause_ai}
            # )
        
        # Return updated conversation details
        detail_serializer = ConversationDetailSerializer(conversation)
        return Response({
            'message': 'Conversation successfully taken over from AI.',
            'conversation': detail_serializer.data
        })
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT'])
def conversation_ai_control(request, conversation_id):
    """
    PUT /api/conversations/{conversation_id}/ai-control - Enable/disable AI for conversation
    """
    tenant_id = getattr(request, 'tenant_id', None)
    current_user_id = getattr(request, 'user_id', None)
    
    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
        tenant_id=tenant_id
    )
    
    # Validate current state
    if conversation.status in ['resolved', 'closed']:
        return Response(
            {
                'error': f'Cannot modify AI control for a {conversation.status} conversation.',
                'status': conversation.status
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    serializer = ConversationAIControlSerializer(
        data=request.data,
        context={'conversation': conversation}
    )
    
    if serializer.is_valid():
        ai_enabled = serializer.validated_data['ai_enabled']
        reason = serializer.validated_data.get('reason', '')
        
        # Check if there's actually a change
        if conversation.ai_enabled == ai_enabled:
            return Response({
                'message': f'AI is already {"enabled" if ai_enabled else "disabled"} for this conversation.',
                'ai_enabled': ai_enabled
            })
        
        with transaction.atomic():
            old_ai_enabled = conversation.ai_enabled
            conversation.ai_enabled = ai_enabled
            
            if ai_enabled:
                # Enabling AI
                conversation.current_handler_type = 'ai'
                conversation.ai_paused_at = None
                conversation.ai_paused_by_user_id = None
                conversation.ai_pause_reason = None
                conversation.can_ai_resume = True
                conversation.last_ai_response_at = timezone.now()
                
                # Update status
                if conversation.status == 'pending':
                    conversation.status = 'ai_handling'
                
            else:
                # Disabling AI
                conversation.current_handler_type = 'human'
                conversation.ai_paused_at = timezone.now()
                conversation.ai_paused_by_user_id = current_user_id
                conversation.ai_pause_reason = reason or 'AI disabled by agent'
                conversation.can_ai_resume = True
                conversation.last_human_response_at = timezone.now()
                
                # Assign to current user if not already assigned
                if not conversation.assigned_user_id and current_user_id:
                    conversation.assigned_user_id = current_user_id
                
                # Update status
                if conversation.status == 'ai_handling':
                    conversation.status = 'active'
            
            conversation.save(update_fields=[
                'ai_enabled', 'current_handler_type', 'ai_paused_at',
                'ai_paused_by_user_id', 'ai_pause_reason', 'can_ai_resume',
                'last_ai_response_at', 'last_human_response_at', 'assigned_user_id',
                'status', 'updated_at'
            ])
            
            # Log the AI control change
            # AuditLog.objects.create(
            #     tenant_id=tenant_id,
            #     user_id=current_user_id,
            #     action_type='ai_control_change',
            #     resource_type='conversation',
            #     resource_id=conversation.id,
            #     old_values={'ai_enabled': old_ai_enabled},
            #     new_values={'ai_enabled': ai_enabled, 'reason': reason}
            # )
        
        # Return updated conversation details
        detail_serializer = ConversationDetailSerializer(conversation)
        return Response({
            'message': f'AI {"enabled" if ai_enabled else "disabled"} for conversation.',
            'conversation': detail_serializer.data
        })
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




@api_view(['GET', 'POST'])
def conversation_messages(request, conversation_id):
    """
    GET /api/conversations/{conversation_id}/messages - Get messages in conversation with read status
    POST /api/conversations/{conversation_id}/messages - Send new message
    """
    tenant_id = getattr(request, 'tenant_id', None)
    current_user_id = getattr(request, 'user_id', None)
    
    # Verify conversation exists and belongs to tenant
    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
        tenant_id=tenant_id
    )
    
    if request.method == 'GET':
        # Build messages queryset with optimizations
        messages = Message.objects.filter(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            is_deleted=False
        ).select_related(
            'conversation'
        ).prefetch_related(
            Prefetch(
                'messagereadstatus_set',
                queryset=MessageReadStatus.objects.select_related('user')
            )
        )
        
        # Apply filters
        sender_type = request.GET.get('sender_type')
        if sender_type:
            messages = messages.filter(sender_type=sender_type)
        
        message_type = request.GET.get('message_type')
        if message_type:
            messages = messages.filter(message_type=message_type)
        
        # Filter by read status
        read_status = request.GET.get('read_status')
        if read_status == 'unread' and current_user_id:
            # Get messages not read by current user
            read_message_ids = MessageReadStatus.objects.filter(
                user_id=current_user_id,
                message__conversation_id=conversation_id
            ).values_list('message_id', flat=True)
            messages = messages.exclude(id__in=read_message_ids)
        elif read_status == 'read' and current_user_id:
            # Get messages read by current user
            read_message_ids = MessageReadStatus.objects.filter(
                user_id=current_user_id,
                message__conversation_id=conversation_id
            ).values_list('message_id', flat=True)
            messages = messages.filter(id__in=read_message_ids)
        
        # Date range filtering
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')
        if from_date:
            try:
                from django.utils.dateparse import parse_datetime
                from_datetime = parse_datetime(from_date)
                if from_datetime:
                    messages = messages.filter(created_at__gte=from_datetime)
            except ValueError:
                pass
        
        if to_date:
            try:
                from django.utils.dateparse import parse_datetime
                to_datetime = parse_datetime(to_date)
                if to_datetime:
                    messages = messages.filter(created_at__lte=to_datetime)
            except ValueError:
                pass
        
        # Search in message content
        search = request.GET.get('search')
        if search:
            # This would need to be adapted based on your encryption implementation
            messages = messages.filter(
                Q(sender_name__icontains=search) |
                Q(ai_intent__icontains=search)
                # Add content search if you have full-text search capability
            )
        
        # Pagination parameters
        limit = min(int(request.GET.get('limit', 50)), 100)  # Max 100 messages
        offset = int(request.GET.get('offset', 0))
        
        # Apply ordering and pagination
        messages = messages.order_by('-created_at')[offset:offset + limit]
        
        # Serialize messages
        serializer = MessageListSerializer(
            messages, 
            many=True,
            context={'current_user_id': current_user_id}
        )
        
        # Get total count for pagination info
        total_count = Message.objects.filter(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            is_deleted=False
        ).count()
        
        # Get unread count for current user
        unread_count = 0
        if current_user_id:
            read_message_ids = MessageReadStatus.objects.filter(
                user_id=current_user_id,
                message__conversation_id=conversation_id
            ).values_list('message_id', flat=True)
            unread_count = Message.objects.filter(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                is_deleted=False
            ).exclude(id__in=read_message_ids).count()
        
        response_data = {
            'results': serializer.data,
            'pagination': {
                'total_count': total_count,
                'limit': limit,
                'offset': offset,
                'has_more': (offset + limit) < total_count
            },
            'unread_count': unread_count,
            'conversation': {
                'id': conversation.id,
                'subject': conversation.subject,
                'status': conversation.status
            }
        }
        
        return Response(response_data)
    
    elif request.method == 'POST':
        # Validate conversation state
        if conversation.status in ['resolved', 'closed']:
            return Response(
                {
                    'error': f'Cannot send messages to a {conversation.status} conversation.',
                    'conversation_status': conversation.status
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = MessageCreateSerializer(data=request.data)
        
        if serializer.is_valid():
            content = serializer.validated_data['content']
            message_type = serializer.validated_data['message_type']
            attachments = serializer.validated_data['attachments']
            
            with transaction.atomic():
                # Create content hash for deduplication
                content_hash = hashlib.sha256(
                    (content + str(current_user_id) + str(timezone.now().timestamp())).encode()
                ).hexdigest()
                
                # Get current user details
                current_user = None
                if current_user_id:
                    try:
                        current_user = TenantUser.objects.get(id=current_user_id)
                    except TenantUser.DoesNotExist:
                        return Response(
                            {'error': 'Current user not found.'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                
                # Create the message
                message = Message.objects.create(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    message_type=message_type,
                    direction='outbound',
                    sender_type='agent',
                    sender_id=current_user_id,
                    sender_name=f"{current_user.first_name} {current_user.last_name}".strip() if current_user else 'Agent',
                    content_encrypted=self._encrypt_content(content),  # Implement encryption
                    content_hash=content_hash,
                    attachments=attachments,
                    delivery_status='sent',
                    platform_timestamp=timezone.now(),
                    processed_at=timezone.now()
                )
                
                # Update conversation
                conversation.last_message_at = timezone.now()
                conversation.last_human_response_at = timezone.now()
                
                # If AI was handling and human sends message, take over
                if conversation.current_handler_type == 'ai':
                    conversation.current_handler_type = 'human'
                    conversation.handover_reason = 'Agent sent message'
                
                # Update conversation status if needed
                if conversation.status == 'pending':
                    conversation.status = 'active'
                
                conversation.save(update_fields=[
                    'last_message_at', 'last_human_response_at', 
                    'current_handler_type', 'handover_reason', 'status', 'updated_at'
                ])
                
                # Mark message as read by sender
                MessageReadStatus.objects.create(
                    tenant_id=tenant_id,
                    message_id=message.id,
                    user_id=current_user_id,
                    read_at=timezone.now()
                )
                
                # Here you would typically:
                # 1. Send message to external platform
                # 2. Trigger AI processing if needed
                # 3. Send real-time notifications
                
            # Return created message details
            detail_serializer = MessageDetailSerializer(
                message,
                context={'current_user_id': current_user_id}
            )
            return Response(detail_serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def message_detail(request, message_id):
    """
    GET /api/messages/{message_id} - Get specific message details
    """
    tenant_id = getattr(request, 'tenant_id', None)
    current_user_id = getattr(request, 'user_id', None)
    
    message = get_object_or_404(
        Message.objects.select_related(
            'conversation'
        ).prefetch_related(
            'messagereadstatus_set__user'
        ),
        id=message_id,
        tenant_id=tenant_id,
        is_deleted=False
    )
    
    # Auto-mark as read for current user if not already read
    if current_user_id:
        MessageReadStatus.objects.get_or_create(
            tenant_id=tenant_id,
            message_id=message.id,
            user_id=current_user_id,
            defaults={'read_at': timezone.now()}
        )
    
    serializer = MessageDetailSerializer(
        message,
        context={'current_user_id': current_user_id}
    )
    return Response(serializer.data)


@api_view(['POST'])
def message_mark_read(request, message_id):
    """
    POST /api/messages/{message_id}/mark-read - Mark specific message as read by current user
    """
    tenant_id = getattr(request, 'tenant_id', None)
    current_user_id = getattr(request, 'user_id', None)
    
    if not current_user_id:
        return Response(
            {'error': 'Authentication required to mark messages as read.'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    # Verify message exists and belongs to tenant
    message = get_object_or_404(
        Message,
        id=message_id,
        tenant_id=tenant_id,
        is_deleted=False
    )
    
    serializer = MessageReadStatusSerializer(data=request.data)
    
    if serializer.is_valid():
        read_at = serializer.validated_data['read_at']
        
        # Create or update read status
        read_status, created = MessageReadStatus.objects.get_or_create(
            tenant_id=tenant_id,
            message_id=message.id,
            user_id=current_user_id,
            defaults={'read_at': read_at}
        )
        
        if not created:
            # Update existing read status if new timestamp is more recent
            if read_at > read_status.read_at:
                read_status.read_at = read_at
                read_status.save(update_fields=['read_at'])
        
        # Get updated message details
        message_serializer = MessageDetailSerializer(
            message,
            context={'current_user_id': current_user_id}
        )
        
        response_data = {
            'message': f'Message marked as read at {read_at}.',
            'was_already_read': not created,
            'read_at': read_status.read_at,
            'message_details': message_serializer.data
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


def _encrypt_content(content):
    """
    Helper function to encrypt message content
    This is a placeholder - implement actual encryption based on your requirements
    """
    # Implement your encryption logic here
    # For now, just return the content as-is
    return content