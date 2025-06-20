# views.py
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import Customer, Conversation
from .serializers import (
    CustomerListSerializer, CustomerDetailSerializer,
    CustomerCreateUpdateSerializer, ConversationListSerializer
)
from django.db.models import Count, Q, Max, Prefetch, Exists, OuterRef
from django.utils import timezone
from datetime import timedelta

from .models import Customer, MessageReadStatus, ContactLabel
from conversations.models import Conversation, Message
from .serializers import (
    ContactsListResponseSerializer, ContactListSerializer, RecentContactSerializer,
    UnreadContactSerializer, ContactSummarySerializer
)

@api_view(['GET', 'POST'])
def customer_list_create(request):
    """
    GET /api/customers - List all customers
    POST /api/customers - Create new customer manually
    """
    # Get tenant from request (assuming you have middleware that sets this)
    tenant_id = getattr(request, 'tenant_id', None)
    
    if request.method == 'GET':
        customers = Customer.objects.filter(
            tenant_id=tenant_id,
            is_archived=False
        ).select_related('platform', 'platform_account').order_by('-created_at')
        
        serializer = CustomerListSerializer(customers, many=True)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = CustomerCreateUpdateSerializer(data=request.data)
        if serializer.is_valid():
            with transaction.atomic():
                customer = serializer.save(tenant_id=tenant_id)
            
            # Return detailed customer data
            detail_serializer = CustomerDetailSerializer(customer)
            return Response(detail_serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
def customer_detail(request, customer_id):
    """
    GET /api/customers/{customer_id} - Get customer details and profile with engagement data
    PUT /api/customers/{customer_id} - Update customer information
    DELETE /api/customers/{customer_id} - Delete customer record
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    customer = get_object_or_404(
        Customer.objects.select_related(
            'platform', 'platform_account'
        ).prefetch_related('contact_insights'),
        id=customer_id,
        tenant_id=tenant_id
    )
    
    if request.method == 'GET':
        serializer = CustomerDetailSerializer(customer)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = CustomerCreateUpdateSerializer(customer, data=request.data, partial=True)
        if serializer.is_valid():
            with transaction.atomic():
                updated_customer = serializer.save()
            
            # Return updated customer details
            detail_serializer = CustomerDetailSerializer(updated_customer)
            return Response(detail_serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        with transaction.atomic():
            # Soft delete by setting is_archived to True
            customer.is_archived = True
            customer.save(update_fields=['is_archived', 'updated_at'])
        
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
def customer_conversations(request, customer_id):
    """
    GET /api/customers/{customer_id}/conversations - Get customer's conversation history
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    # Verify customer exists and belongs to tenant
    customer = get_object_or_404(
        Customer,
        id=customer_id,
        tenant_id=tenant_id
    )
    
    conversations = Conversation.objects.filter(
        customer_id=customer_id,
        tenant_id=tenant_id
    ).select_related(
        'platform', 'platform_account'
    ).prefetch_related('messages').order_by('-created_at')
    
    serializer = ConversationListSerializer(conversations, many=True)
    return Response(serializer.data)



@api_view(['GET'])
def contacts_list(request):
    """
    GET /api/contacts - Get contacts list with latest message preview and unread counts
    """
    tenant_id = getattr(request, 'tenant_id', None)
    current_user_id = getattr(request, 'user_id', None)
    
    # Base queryset with optimizations
    contacts = Customer.objects.filter(
        tenant_id=tenant_id,
        is_archived=False
    ).select_related(
        'platform'
    ).prefetch_related(
        'customerlabel_set__label',
        Prefetch(
            'conversations',
            queryset=Conversation.objects.select_related().order_by('-last_message_at')
        )
    )
    
    # Apply filters
    search = request.GET.get('search')
    if search:
        contacts = contacts.filter(
            Q(platform_username__icontains=search) |
            Q(platform_display_name__icontains=search) |
            Q(email_encrypted__icontains=search)  # This would need proper search on encrypted fields
        )
    
    # Filter by platform
    platform = request.GET.get('platform')
    if platform:
        contacts = contacts.filter(platform__name=platform)
    
    # Filter by status
    contact_status = request.GET.get('status')
    if contact_status == 'online':
        five_minutes_ago = timezone.now() - timedelta(minutes=5)
        contacts = contacts.filter(last_seen_at__gte=five_minutes_ago)
    elif contact_status == 'typing':
        contacts = contacts.filter(is_typing=True)
    elif contact_status == 'pinned':
        contacts = contacts.filter(is_pinned=True)
    
    # Filter by labels
    labels = request.GET.get('labels')
    if labels:
        label_list = [label.strip() for label in labels.split(',')]
        contacts = contacts.filter(
            customerlabel_set__label__name__in=label_list
        ).distinct()
    
    # Filter by engagement score
    min_engagement = request.GET.get('min_engagement')
    if min_engagement:
        try:
            contacts = contacts.filter(engagement_score__gte=float(min_engagement))
        except ValueError:
            pass
    
    # Filter by unread status
    has_unread = request.GET.get('has_unread')
    if has_unread and has_unread.lower() in ('true', '1', 'yes') and current_user_id:
        # Subquery to check for unread messages
        unread_messages_exist = Message.objects.filter(
            conversation__customer_id=OuterRef('id'),
            sender_type='customer'
        ).exclude(
            id__in=MessageReadStatus.objects.filter(
                user_id=current_user_id
            ).values_list('message_id', flat=True)
        )
        
        contacts = contacts.filter(
            Exists(unread_messages_exist)
        )
    
    # Sorting
    sort_by = request.GET.get('sort_by', '-last_contact_at')
    valid_sort_fields = [
        'platform_username', '-platform_username',
        'last_contact_at', '-last_contact_at',
        'last_seen_at', '-last_seen_at',
        'engagement_score', '-engagement_score',
        'created_at', '-created_at'
    ]
    
    if sort_by in valid_sort_fields:
        contacts = contacts.order_by(sort_by)
    elif sort_by == 'unread_count' and current_user_id:
        # Custom sorting by unread count (complex, would need raw SQL for efficiency)
        contacts = contacts.order_by('-last_contact_at')  # Fallback
    else:
        # Default: pinned first, then by last contact
        contacts = contacts.order_by('-is_pinned', '-last_contact_at')
    
    # Pagination
    limit = min(int(request.GET.get('limit', 50)), 100)
    offset = int(request.GET.get('offset', 0))
    
    total_count = contacts.count()
    paginated_contacts = contacts[offset:offset + limit]
    
    # Serialize contacts
    contact_serializer = ContactListSerializer(
        paginated_contacts,
        many=True,
        context={'current_user_id': current_user_id}
    )
    
    # Calculate summary statistics
    summary_data = _calculate_contacts_summary(tenant_id, current_user_id)
    
    # Prepare response
    response_data = {
        'contacts': contact_serializer.data,
        'total': total_count,
        'summary': summary_data,
        'filters_applied': {
            'search': search,
            'platform': platform,
            'status': contact_status,
            'labels': labels,
            'min_engagement': min_engagement,
            'has_unread': has_unread,
            'sort_by': sort_by
        },
        'pagination': {
            'limit': limit,
            'offset': offset,
            'has_more': (offset + limit) < total_count,
            'total_pages': (total_count + limit - 1) // limit,
            'current_page': (offset // limit) + 1
        }
    }
    
    return Response(response_data)


@api_view(['GET'])
def contacts_recent(request):
    """
    GET /api/contacts/recent - Get recently active contacts (last 24-48 hours)
    """
    tenant_id = getattr(request, 'tenant_id', None)
    current_user_id = getattr(request, 'user_id', None)
    
    # Get timeframe from query params (default 24 hours)
    hours = int(request.GET.get('hours', 24))
    hours = min(hours, 168)  # Max 1 week
    
    cutoff_time = timezone.now() - timedelta(hours=hours)
    
    # Get contacts with recent activity
    recent_contacts = Customer.objects.filter(
        tenant_id=tenant_id,
        is_archived=False
    ).filter(
        Q(last_contact_at__gte=cutoff_time) |
        Q(last_seen_at__gte=cutoff_time) |
        Q(conversations__last_message_at__gte=cutoff_time)
    ).select_related(
        'platform'
    ).prefetch_related(
        Prefetch(
            'conversations',
            queryset=Conversation.objects.order_by('-last_message_at')
        )
    ).distinct().order_by('-last_contact_at', '-last_seen_at')
    
    # Apply additional filters
    platform = request.GET.get('platform')
    if platform:
        recent_contacts = recent_contacts.filter(platform__name=platform)
    
    min_engagement = request.GET.get('min_engagement')
    if min_engagement:
        try:
            recent_contacts = recent_contacts.filter(engagement_score__gte=float(min_engagement))
        except ValueError:
            pass
    
    # Pagination
    limit = min(int(request.GET.get('limit', 20)), 50)
    offset = int(request.GET.get('offset', 0))
    
    total_count = recent_contacts.count()
    paginated_contacts = recent_contacts[offset:offset + limit]
    
    # Serialize
    serializer = RecentContactSerializer(
        paginated_contacts,
        many=True,
        context={'current_user_id': current_user_id}
    )
    
    response_data = {
        'contacts': serializer.data,
        'total': total_count,
        'timeframe_hours': hours,
        'filters_applied': {
            'platform': platform,
            'min_engagement': min_engagement
        },
        'pagination': {
            'limit': limit,
            'offset': offset,
            'has_more': (offset + limit) < total_count
        }
    }
    
    return Response(response_data)


@api_view(['GET'])
def contacts_unread(request):
    """
    GET /api/contacts/unread - Get contacts with unread messages only
    """
    tenant_id = getattr(request, 'tenant_id', None)
    current_user_id = getattr(request, 'user_id', None)
    
    if not current_user_id:
        return Response(
            {'error': 'Authentication required to view unread messages.'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    # Get contacts with unread messages
    unread_contacts = Customer.objects.filter(
        tenant_id=tenant_id,
        is_archived=False
    ).filter(
        # Has messages that current user hasn't read
        conversations__messages__sender_type='customer'
    ).exclude(
        conversations__messages__id__in=MessageReadStatus.objects.filter(
            user_id=current_user_id
        ).values_list('message_id', flat=True)
    ).select_related(
        'platform'
    ).prefetch_related(
        Prefetch(
            'conversations',
            queryset=Conversation.objects.order_by('-last_message_at')
        )
    ).distinct()
    
    # Apply filters
    platform = request.GET.get('platform')
    if platform:
        unread_contacts = unread_contacts.filter(platform__name=platform)
    
    # Filter by priority (pinned contacts first)
    priority_only = request.GET.get('priority_only')
    if priority_only and priority_only.lower() in ('true', '1', 'yes'):
        unread_contacts = unread_contacts.filter(is_pinned=True)
    
    # Sort by urgency (pinned first, then by last message time)
    unread_contacts = unread_contacts.order_by(
        '-is_pinned',
        '-conversations__last_message_at'
    )
    
    # Pagination
    limit = min(int(request.GET.get('limit', 30)), 100)
    offset = int(request.GET.get('offset', 0))
    
    total_count = unread_contacts.count()
    paginated_contacts = unread_contacts[offset:offset + limit]
    
    # Serialize
    serializer = UnreadContactSerializer(
        paginated_contacts,
        many=True,
        context={'current_user_id': current_user_id}
    )
    
    # Calculate unread summary
    total_unread_messages = Message.objects.filter(
        conversation__customer__tenant_id=tenant_id,
        sender_type='customer'
    ).exclude(
        id__in=MessageReadStatus.objects.filter(
            user_id=current_user_id
        ).values_list('message_id', flat=True)
    ).count()
    
    response_data = {
        'contacts': serializer.data,
        'total': total_count,
        'summary': {
            'total_unread_messages': total_unread_messages,
            'contacts_with_unread': total_count,
            'priority_contacts_with_unread': unread_contacts.filter(is_pinned=True).count()
        },
        'filters_applied': {
            'platform': platform,
            'priority_only': priority_only
        },
        'pagination': {
            'limit': limit,
            'offset': offset,
            'has_more': (offset + limit) < total_count
        }
    }
    
    return Response(response_data)


def _calculate_contacts_summary(tenant_id, current_user_id):
    """Calculate summary statistics for contacts"""
    
    # Total contacts
    total_contacts = Customer.objects.filter(
        tenant_id=tenant_id,
        is_archived=False
    ).count()
    
    # Pinned contacts
    pinned_contacts = Customer.objects.filter(
        tenant_id=tenant_id,
        is_archived=False,
        is_pinned=True
    ).count()
    
    # Online contacts (active in last 5 minutes)
    five_minutes_ago = timezone.now() - timedelta(minutes=5)
    online_contacts = Customer.objects.filter(
        tenant_id=tenant_id,
        is_archived=False,
        last_seen_at__gte=five_minutes_ago
    ).count()
    
    # Recent contacts (active in last 24 hours)
    twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
    recent_contacts_24h = Customer.objects.filter(
        tenant_id=tenant_id,
        is_archived=False
    ).filter(
        Q(last_contact_at__gte=twenty_four_hours_ago) |
        Q(last_seen_at__gte=twenty_four_hours_ago)
    ).count()
    
    # Unread statistics (if user is authenticated)
    contacts_with_unread = 0
    total_unread_messages = 0
    
    if current_user_id:
        # Get contacts with unread messages
        contacts_with_unread = Customer.objects.filter(
            tenant_id=tenant_id,
            is_archived=False,
            conversations__messages__sender_type='customer'
        ).exclude(
            conversations__messages__id__in=MessageReadStatus.objects.filter(
                user_id=current_user_id
            ).values_list('message_id', flat=True)
        ).distinct().count()
        
        # Total unread messages
        total_unread_messages = Message.objects.filter(
            conversation__customer__tenant_id=tenant_id,
            sender_type='customer'
        ).exclude(
            id__in=MessageReadStatus.objects.filter(
                user_id=current_user_id
            ).values_list('message_id', flat=True)
        ).count()
    
    return {
        'total_contacts': total_contacts,
        'contacts_with_unread': contacts_with_unread,
        'total_unread_messages': total_unread_messages,
        'pinned_contacts': pinned_contacts,
        'online_contacts': online_contacts,
        'recent_contacts_24h': recent_contacts_24h
    }