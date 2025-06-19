# views.py
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import LeadStage, LeadCategory, Lead
from .serializers import (
    LeadCategoryListSerializer, LeadCategoryDetailSerializer,
    LeadCategoryCreateUpdateSerializer,     LeadListSerializer, LeadDetailSerializer,
    LeadCreateUpdateSerializer, LeadStageUpdateSerializer
)


@api_view(['GET', 'POST'])
def lead_stage_list_create(request):
    """
    GET /api/lead-stages - List all lead stages
    POST /api/lead-stages - Create new lead stage
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    if request.method == 'GET':
        lead_stages = LeadStage.objects.filter(
            tenant_id=tenant_id
        ).prefetch_related('leads').order_by('stage_order', 'created_at')
        
        serializer = LeadStageListSerializer(lead_stages, many=True)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = LeadStageCreateUpdateSerializer(
            data=request.data,
            context={'tenant_id': tenant_id}
        )
        
        if serializer.is_valid():
            with transaction.atomic():
                lead_stage = serializer.save(tenant_id=tenant_id)
            
            # Return detailed lead stage data
            detail_serializer = LeadStageDetailSerializer(lead_stage)
            return Response(detail_serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
def lead_stage_detail(request, stage_id):
    """
    GET /api/lead-stages/{stage_id} - Get lead stage details
    PUT /api/lead-stages/{stage_id} - Update lead stage
    DELETE /api/lead-stages/{stage_id} - Delete lead stage
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    lead_stage = get_object_or_404(
        LeadStage.objects.prefetch_related('leads'),
        id=stage_id,
        tenant_id=tenant_id
    )
    
    if request.method == 'GET':
        serializer = LeadStageDetailSerializer(lead_stage)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = LeadStageCreateUpdateSerializer(
            lead_stage,
            data=request.data,
            partial=True,
            context={'tenant_id': tenant_id}
        )
        
        if serializer.is_valid():
            with transaction.atomic():
                updated_lead_stage = serializer.save()
            
            # Return updated lead stage details
            detail_serializer = LeadStageDetailSerializer(updated_lead_stage)
            return Response(detail_serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        # Check if there are active leads in this stage
        active_leads_count = lead_stage.leads.filter(status='active').count()
        
        if active_leads_count > 0:
            return Response(
                {
                    'error': f'Cannot delete lead stage. There are {active_leads_count} active leads in this stage.',
                    'active_leads_count': active_leads_count
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            # Check if this is the only active stage
            active_stages_count = LeadStage.objects.filter(
                tenant_id=tenant_id,
                is_active=True
            ).count()
            
            if lead_stage.is_active and active_stages_count <= 1:
                return Response(
                    {'error': 'Cannot delete the only active lead stage.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            lead_stage.delete()
        
        return Response(status=status.HTTP_204_NO_CONTENT)



@api_view(['GET', 'POST'])
def lead_category_list_create(request):
    """
    GET /api/lead-categories - List all lead categories
    POST /api/lead-categories - Create new lead category
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    if request.method == 'GET':
        lead_categories = LeadCategory.objects.filter(
            tenant_id=tenant_id
        ).prefetch_related('leads').order_by('-priority_score', 'name')
        
        serializer = LeadCategoryListSerializer(lead_categories, many=True)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = LeadCategoryCreateUpdateSerializer(
            data=request.data,
            context={'tenant_id': tenant_id}
        )
        
        if serializer.is_valid():
            with transaction.atomic():
                lead_category = serializer.save(
                    tenant_id=tenant_id,
                    is_system_defined=False  # User-created categories are not system-defined
                )
            
            # Return detailed lead category data
            detail_serializer = LeadCategoryDetailSerializer(lead_category)
            return Response(detail_serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
def lead_category_detail(request, category_id):
    """
    GET /api/lead-categories/{category_id} - Get lead category details
    PUT /api/lead-categories/{category_id} - Update lead category
    DELETE /api/lead-categories/{category_id} - Delete lead category
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    lead_category = get_object_or_404(
        LeadCategory.objects.prefetch_related('leads'),
        id=category_id,
        tenant_id=tenant_id
    )
    
    if request.method == 'GET':
        serializer = LeadCategoryDetailSerializer(lead_category)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        # Prevent updating system-defined categories
        if lead_category.is_system_defined:
            return Response(
                {'error': 'Cannot update system-defined lead category.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = LeadCategoryCreateUpdateSerializer(
            lead_category,
            data=request.data,
            partial=True,
            context={'tenant_id': tenant_id}
        )
        
        if serializer.is_valid():
            with transaction.atomic():
                updated_lead_category = serializer.save()
            
            # Return updated lead category details
            detail_serializer = LeadCategoryDetailSerializer(updated_lead_category)
            return Response(detail_serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        # Prevent deleting system-defined categories
        if lead_category.is_system_defined:
            return Response(
                {'error': 'Cannot delete system-defined lead category.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if there are active leads in this category
        active_leads_count = lead_category.leads.filter(status='active').count()
        
        if active_leads_count > 0:
            return Response(
                {
                    'error': f'Cannot delete lead category. There are {active_leads_count} active leads in this category.',
                    'active_leads_count': active_leads_count
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            # Check if this is the only active category
            active_categories_count = LeadCategory.objects.filter(
                tenant_id=tenant_id,
                is_active=True
            ).count()
            
            if lead_category.is_active and active_categories_count <= 1:
                return Response(
                    {'error': 'Cannot delete the only active lead category.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            lead_category.delete()
        
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'POST'])
def lead_list_create(request):
    """
    GET /api/leads - List all leads
    POST /api/leads - Create new lead manually
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    if request.method == 'GET':
        leads = Lead.objects.filter(
            tenant_id=tenant_id
        ).select_related(
            'customer', 'lead_category', 'lead_stage', 'source_platform'
        ).order_by('-created_at')
        
        serializer = LeadListSerializer(leads, many=True)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = LeadCreateUpdateSerializer(
            data=request.data,
            context={'tenant_id': tenant_id}
        )
        
        if serializer.is_valid():
            with transaction.atomic():
                lead = serializer.save(
                    tenant_id=tenant_id,
                    last_activity_at=timezone.now()
                )
            
            # Return detailed lead data
            detail_serializer = LeadDetailSerializer(lead)
            return Response(detail_serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
def lead_detail(request, lead_id):
    """
    GET /api/leads/{lead_id} - Get lead details
    PUT /api/leads/{lead_id} - Update lead information
    DELETE /api/leads/{lead_id} - Delete lead
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    lead = get_object_or_404(
        Lead.objects.select_related(
            'customer', 'lead_category', 'lead_stage', 'source_platform'
        ).prefetch_related('conversations'),
        id=lead_id,
        tenant_id=tenant_id
    )
    
    if request.method == 'GET':
        serializer = LeadDetailSerializer(lead)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = LeadCreateUpdateSerializer(
            lead,
            data=request.data,
            partial=True,
            context={'tenant_id': tenant_id}
        )
        
        if serializer.is_valid():
            with transaction.atomic():
                updated_lead = serializer.save(
                    last_activity_at=timezone.now()
                )
            
            # Return updated lead details
            detail_serializer = LeadDetailSerializer(updated_lead)
            return Response(detail_serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        with transaction.atomic():
            # Soft delete by setting status to 'deleted'
            lead.status = 'deleted'
            lead.save(update_fields=['status', 'updated_at'])
        
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['PUT'])
def lead_stage_update(request, lead_id):
    """
    PUT /api/leads/{lead_id}/stage - Move lead to different stage
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    lead = get_object_or_404(
        Lead.objects.select_related('lead_stage'),
        id=lead_id,
        tenant_id=tenant_id
    )
    
    serializer = LeadStageUpdateSerializer(
        data=request.data,
        context={'tenant_id': tenant_id}
    )
    
    if serializer.is_valid():
        new_stage_id = serializer.validated_data['lead_stage_id']
        reason = serializer.validated_data.get('reason', '')
        
        # Check if stage is actually changing
        if str(lead.lead_stage_id) == str(new_stage_id):
            return Response(
                {'message': 'Lead is already in the specified stage.'},
                status=status.HTTP_200_OK
            )
        
        with transaction.atomic():
            old_stage = lead.lead_stage
            
            # Update lead stage
            lead.lead_stage_id = new_stage_id
            lead.last_activity_at = timezone.now()
            lead.save(update_fields=['lead_stage_id', 'last_activity_at', 'updated_at'])
            
            # Here you could log the stage change for audit purposes
            # stage_change_log = {
            #     'old_stage': old_stage.name if old_stage else None,
            #     'new_stage_id': new_stage_id,
            #     'reason': reason,
            #     'changed_at': timezone.now(),
            #     'changed_by': request.user.id if hasattr(request, 'user') else None
            # }
        
        # Return updated lead details
        detail_serializer = LeadDetailSerializer(lead)
        return Response({
            'message': 'Lead stage updated successfully.',
            'lead': detail_serializer.data
        })
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)