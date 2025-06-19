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