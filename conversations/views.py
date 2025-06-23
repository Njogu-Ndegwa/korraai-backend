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
from rest_framework.decorators import api_view, permission_classes
from .serializers import ConversationCreateSerializer, ConversationResponseSerializer
from core.utils import get_tenant_from_user
from rest_framework.permissions import IsAuthenticated

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_conversation(request):
    """
    POST /api/conversations/
    Create a new conversation
    """
    tenant_id, error_response = get_tenant_from_user(request)
    if error_response:
        return error_response
    
    # Add tenant to serializer context
    serializer = ConversationCreateSerializer(
        data=request.data,
        context={'tenant': request.user.tenant}
    )
    
    if not serializer.is_valid():
        return Response(
            {
                'success': False,
                'errors': serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Check for duplicate conversation
        existing_conversation = Conversation.objects.filter(
            tenant_id=tenant_id,
            platform=serializer.validated_data['platform'],
            external_conversation_id=serializer.validated_data['external_conversation_id']
        ).first()
        
        if existing_conversation:
            # Return existing conversation instead of creating duplicate
            response_serializer = ConversationResponseSerializer(existing_conversation)
            return Response(
                {
                    'success': True,
                    'message': 'Conversation already exists',
                    'conversation': response_serializer.data,
                    'created': False
                },
                status=status.HTTP_200_OK
            )
        
        # Create new conversation
        conversation = serializer.save()
        
        # Set first_message_at if not provided
        if not conversation.first_message_at:
            conversation.first_message_at = timezone.now()
            conversation.save(update_fields=['first_message_at'])
        
        # Update customer last contact
        customer = conversation.customer
        customer.last_contact_at = timezone.now()
        customer.save(update_fields=['last_contact_at'])
        
        # Prepare response
        response_serializer = ConversationResponseSerializer(conversation)
        
        return Response(
            {
                'success': True,
                'message': 'Conversation created successfully',
                'conversation': response_serializer.data,
                'created': True
            },
            status=status.HTTP_201_CREATED
        )
        
    except Exception as e:
        return Response(
            {
                'success': False,
                'message': f'Failed to create conversation: {str(e)}'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_conversation(request, conversation_id):
    """
    GET /api/conversations/{conversation_id}/
    Get conversation details
    """
    tenant_id, error_response = get_tenant_from_user(request)
    if error_response:
        return error_response
    
    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
        tenant_id=tenant_id
    )
    
    serializer = ConversationResponseSerializer(conversation)
    
    return Response(
        {
            'success': True,
            'conversation': serializer.data
        },
        status=status.HTTP_200_OK
    )


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_conversation_status(request, conversation_id):
    """
    PUT /api/conversations/{conversation_id}/status/
    Update conversation status
    """
    tenant_id, error_response = get_tenant_from_user(request)
    if error_response:
        return error_response
    
    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
        tenant_id=tenant_id
    )
    
    new_status = request.data.get('status')
    if not new_status:
        return Response(
            {
                'success': False,
                'message': 'Status is required'
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    valid_statuses = ['active', 'pending', 'resolved', 'closed', 'archived']
    if new_status not in valid_statuses:
        return Response(
            {
                'success': False,
                'message': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        old_status = conversation.status
        conversation.status = new_status
        
        # Set resolved_at timestamp if resolving
        if new_status == 'resolved' and old_status != 'resolved':
            conversation.resolved_at = timezone.now()
        elif new_status != 'resolved':
            conversation.resolved_at = None
        
        conversation.save()
        
        serializer = ConversationResponseSerializer(conversation)
        
        return Response(
            {
                'success': True,
                'message': f'Conversation status updated from {old_status} to {new_status}',
                'conversation': serializer.data
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        return Response(
            {
                'success': False,
                'message': f'Failed to update status: {str(e)}'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


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


from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Max, Exists, OuterRef, Case, When, IntegerField
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import Conversation, Message, MessageReadStatus

channel_layer = get_channel_layer()

class ConversationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_conversations(request):
    """
    Get conversations for agent dashboard with real-time message indicators
    Returns conversations ordered by latest message first with unread counts
    """
    tenant = request.tenant
    user = request.user
    
    # Get conversations with unread message counts and latest message info
    conversations = Conversation.objects.filter(
        tenant=tenant
    ).select_related(
        'customer', 'platform', 'assigned_user'
    ).annotate(
        # Count total messages in conversation
        total_messages=Count('messages'),
        
        # Get latest message timestamp
        latest_message_at=Max('messages__created_at'),
        
        # Count unread messages for this user
        unread_count=Count(
            'messages',
            filter=Q(
                messages__created_at__gt=OuterRef('last_read_at')
            ) | Q(last_read_at__isnull=True)
        ),
        
        # Check if user has read any messages in this conversation
        last_read_at=Max(
            'messages__read_statuses__read_at',
            filter=Q(messages__read_statuses__user=user)
        ),
        
        # Get latest message content
        latest_message_content=Max('messages__content_encrypted'),
        latest_message_sender=Max('messages__sender_name'),
        latest_message_type=Max('messages__sender_type'),
        
        # Mark as new conversation if user never read any messages
        is_new_conversation=Case(
            When(last_read_at__isnull=True, then=1),
            default=0,
            output_field=IntegerField()
        )
    ).order_by('-latest_message_at', '-updated_at')
    
    # Apply pagination
    paginator = ConversationPagination()
    page = paginator.paginate_queryset(conversations, request)
    
    # Serialize the data
    conversation_data = []
    for conv in page:
        data = {
            'id': str(conv.id),
            'customer': {
                'id': str(conv.customer.id),
                'name': conv.customer.display_name,
                'avatar': conv.customer.profile_picture_url,
                'status': conv.customer.status,
                'platform': conv.platform.display_name,
                'is_typing': conv.customer.is_typing and 
                           conv.customer.typing_in_conversation_id == conv.id
            },
            'conversation': {
                'status': conv.status,
                'priority': conv.priority,
                'current_handler_type': conv.current_handler_type,
                'ai_enabled': conv.ai_enabled,
                'assigned_user_name': conv.assigned_user.first_name + ' ' + conv.assigned_user.last_name if conv.assigned_user else None,
                'sentiment_score': float(conv.sentiment_score) if conv.sentiment_score else None
            },
            'latest_message': {
                'content': conv.latest_message_content or '',
                'sender_name': conv.latest_message_sender or '',
                'sender_type': conv.latest_message_type or '',
                'timestamp': conv.latest_message_at.isoformat() if conv.latest_message_at else None
            },
            'message_stats': {
                'total_messages': conv.total_messages,
                'unread_count': conv.unread_count,
                'is_new_conversation': bool(conv.is_new_conversation),
                'last_read_at': conv.last_read_at.isoformat() if conv.last_read_at else None
            },
            'timestamps': {
                'created_at': conv.created_at.isoformat(),
                'updated_at': conv.updated_at.isoformat(),
                'latest_message_at': conv.latest_message_at.isoformat() if conv.latest_message_at else None
            }
        }
        conversation_data.append(data)
    
    return paginator.get_paginated_response(conversation_data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def conversation_messages(request, conversation_id):
    """
    Get messages for a specific conversation (newest first)
    Automatically mark messages as read when fetched
    """
    tenant = request.tenant
    user = request.user
    
    conversation = get_object_or_404(
        Conversation.objects.select_related('customer', 'platform'),
        id=conversation_id,
        tenant=tenant
    )
    
    # Get messages ordered by newest first
    messages = Message.objects.filter(
        conversation=conversation,
        tenant=tenant,
        is_deleted=False
    ).select_related('conversation').annotate(
        # Check if this message is read by current user
        is_read_by_user=Exists(
            MessageReadStatus.objects.filter(
                message=OuterRef('pk'),
                user=user
            )
        )
    ).order_by('-created_at')  # Newest first
    
    # Apply pagination
    paginator = ConversationPagination()
    page = paginator.paginate_queryset(messages, request)
    
    # Serialize messages
    message_data = []
    unread_message_ids = []
    
    for msg in page:
        data = {
            'id': str(msg.id),
            'content': msg.content_encrypted,
            'sender_type': msg.sender_type,
            'sender_name': msg.sender_name,
            'direction': msg.direction,
            'message_type': msg.message_type,
            'delivery_status': msg.delivery_status,
            'ai_confidence': float(msg.ai_confidence) if msg.ai_confidence else None,
            'ai_intent': msg.ai_intent,
            'ai_sentiment': float(msg.ai_sentiment) if msg.ai_sentiment else None,
            'attachments': msg.attachments,
            'is_read': msg.is_read_by_user,
            'created_at': msg.created_at.isoformat(),
            'platform_timestamp': msg.platform_timestamp.isoformat() if msg.platform_timestamp else None
        }
        message_data.append(data)
        
        # Collect unread message IDs for batch marking as read
        if not msg.is_read_by_user:
            unread_message_ids.append(msg.id)
    
    # Mark unread messages as read (batch operation)
    if unread_message_ids:
        mark_messages_as_read(unread_message_ids, user, tenant)
        
        # Notify other agents about read status update
        async_to_sync(channel_layer.group_send)(
            f"conversation_{conversation_id}",
            {
                'type': 'messages_read',
                'message_ids': [str(mid) for mid in unread_message_ids],
                'read_by_user': user.email,
                'read_at': timezone.now().isoformat()
            }
        )
    
    response_data = {
        'conversation': {
            'id': str(conversation.id),
            'customer_name': conversation.customer.display_name,
            'platform': conversation.platform.display_name,
            'status': conversation.status,
            'current_handler_type': conversation.current_handler_type,
            'ai_enabled': conversation.ai_enabled
        },
        'messages': message_data,
        'pagination': {
            'total_unread': len(unread_message_ids),
            'has_next': paginator.page.has_next() if hasattr(paginator, 'page') else False,
            'has_previous': paginator.page.has_previous() if hasattr(paginator, 'page') else False
        }
    }
    
    return paginator.get_paginated_response(response_data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_messages_read(request, conversation_id):
    """
    Manually mark specific messages as read
    """
    tenant = request.tenant
    user = request.user
    message_ids = request.data.get('message_ids', [])
    
    if not message_ids:
        return Response(
            {'error': 'message_ids required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
        tenant=tenant
    )
    
    # Validate messages belong to this conversation and tenant
    valid_messages = Message.objects.filter(
        id__in=message_ids,
        conversation=conversation,
        tenant=tenant
    ).values_list('id', flat=True)
    
    # Mark as read
    read_count = mark_messages_as_read(list(valid_messages), user, tenant)
    
    # Notify other agents
    async_to_sync(channel_layer.group_send)(
        f"conversation_{conversation_id}",
        {
            'type': 'messages_read',
            'message_ids': [str(mid) for mid in valid_messages],
            'read_by_user': user.email,
            'read_at': timezone.now().isoformat()
        }
    )
    
    return Response({
        'status': 'success',
        'marked_read_count': read_count,
        'message_ids': [str(mid) for mid in valid_messages]
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    """
    Get dashboard statistics for agent overview
    """
    tenant = request.tenant
    user = request.user
    
    # Get overall stats
    total_conversations = Conversation.objects.filter(tenant=tenant).count()
    
    # Count conversations with unread messages for this user
    conversations_with_unread = Conversation.objects.filter(
        tenant=tenant,
        messages__isnull=False
    ).annotate(
        unread_count=Count(
            'messages',
            filter=~Exists(
                MessageReadStatus.objects.filter(
                    message=OuterRef('messages'),
                    user=user
                )
            )
        )
    ).filter(unread_count__gt=0).count()
    
    # Count new conversations (never read by user)
    new_conversations = Conversation.objects.filter(
        tenant=tenant,
        messages__isnull=False
    ).exclude(
        messages__read_statuses__user=user
    ).distinct().count()
    
    # Count total unread messages
    total_unread_messages = Message.objects.filter(
        tenant=tenant,
        is_deleted=False
    ).exclude(
        read_statuses__user=user
    ).count()
    
    # Count conversations by status
    status_counts = Conversation.objects.filter(
        tenant=tenant
    ).values('status').annotate(
        count=Count('id')
    )
    
    # Count conversations by handler type
    handler_counts = Conversation.objects.filter(
        tenant=tenant
    ).values('current_handler_type').annotate(
        count=Count('id')
    )
    
    # Get assigned conversations for this user
    assigned_to_user = Conversation.objects.filter(
        tenant=tenant,
        assigned_user=user
    ).count()
    
    return Response({
        'overview': {
            'total_conversations': total_conversations,
            'conversations_with_unread': conversations_with_unread,
            'new_conversations': new_conversations,
            'total_unread_messages': total_unread_messages,
            'assigned_to_me': assigned_to_user
        },
        'status_breakdown': {item['status']: item['count'] for item in status_counts},
        'handler_breakdown': {item['current_handler_type']: item['count'] for item in handler_counts},
        'generated_at': timezone.now().isoformat()
    })


def mark_messages_as_read(message_ids, user, tenant):
    """
    Helper function to mark messages as read (batch operation)
    """
    if not message_ids:
        return 0
    
    # Get messages that aren't already read by this user
    unread_messages = Message.objects.filter(
        id__in=message_ids,
        tenant=tenant
    ).exclude(
        read_statuses__user=user
    )
    
    # Create read status records
    read_statuses = []
    read_time = timezone.now()
    
    for message in unread_messages:
        read_statuses.append(
            MessageReadStatus(
                tenant=tenant,
                message=message,
                user=user,
                read_at=read_time
            )
        )
    
    # Batch create
    if read_statuses:
        MessageReadStatus.objects.bulk_create(
            read_statuses,
            ignore_conflicts=True  # Handle race conditions
        )
    
    return len(read_statuses)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_typing_status(request, conversation_id):
    """Update customer typing status"""
    tenant = request.tenant
    is_typing = request.data.get('is_typing', False)
    
    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
        tenant=tenant
    )
    
    # Update customer typing status
    customer = conversation.customer
    if is_typing:
        customer.set_typing(conversation_id=conversation.id, is_typing=True)
    else:
        customer.set_typing(is_typing=False)
    
    # Notify real-time about typing status
    DashboardNotifier.notify_customer_typing(conversation, is_typing)
    
    return Response({
        'status': 'success',
        'conversation_id': str(conversation_id),
        'is_typing': is_typing
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def assign_conversation(request, conversation_id):
    """Assign conversation to a user"""
    tenant = request.tenant
    user = request.user
    assign_to_user_id = request.data.get('user_id')
    
    if not assign_to_user_id:
        return Response(
            {'error': 'user_id required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
        tenant=tenant
    )
    
    # Get the user to assign to
    from tenants.models import TenantUser
    assigned_user = get_object_or_404(
        TenantUser,
        id=assign_to_user_id,
        tenant=tenant,
        is_active=True
    )
    
    # Update conversation
    conversation.assigned_user = assigned_user
    conversation.current_handler_type = 'human'
    conversation.ai_enabled = False
    conversation.save(update_fields=['assigned_user', 'current_handler_type', 'ai_enabled'])
    
    # Send notification
    DashboardNotifier.notify_conversation_assigned(conversation, assigned_user, user)
    
    return Response({
        'status': 'success',
        'conversation_id': str(conversation_id),
        'assigned_to': assigned_user.email,
        'assigned_by': user.email
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def unread_counts(request):
    """Get unread message counts per conversation"""
    tenant = request.tenant
    user = request.user
    
    # Get conversations with unread counts
    conversations_with_unread = Conversation.objects.filter(
        tenant=tenant,
        messages__isnull=False
    ).annotate(
        unread_count=Count(
            'messages',
            filter=~Exists(
                MessageReadStatus.objects.filter(
                    message=OuterRef('messages'),
                    user=user
                )
            )
        )
    ).filter(unread_count__gt=0).values(
        'id', 'unread_count'
    )
    
    # Format response
    unread_data = {}
    total_unread = 0
    
    for conv in conversations_with_unread:
        conversation_id = str(conv['id'])
        unread_count = conv['unread_count']
        unread_data[conversation_id] = unread_count
        total_unread += unread_count
    
    return Response({
        'total_unread': total_unread,
        'conversations': unread_data,
        'generated_at': timezone.now().isoformat()
    })


