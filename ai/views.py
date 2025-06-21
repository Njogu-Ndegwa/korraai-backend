# ai_settings/views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import TenantAISetting
from .serializers import TenantAISettingSerializer, TenantAISettingCreateSerializer
from knowledgebase.auth_utils import get_tenant_from_user

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def ai_settings_list_create(request):
    tenant_id, error_response = get_tenant_from_user(request)
    if error_response:
        return error_response
    
    if request.method == 'GET':
        settings = TenantAISetting.objects.filter(tenant_id=tenant_id)
        serializer = TenantAISettingSerializer(settings, many=True)
        return Response({'results': serializer.data})
    
    elif request.method == 'POST':
        serializer = TenantAISettingCreateSerializer(
            data=request.data,
            context={'tenant_id': tenant_id}
        )
        if serializer.is_valid():
            ai_setting = serializer.save()
            response_serializer = TenantAISettingSerializer(ai_setting)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def ai_settings_detail(request, setting_id):
    tenant_id, error_response = get_tenant_from_user(request)
    if error_response:
        return error_response
    
    ai_setting = get_object_or_404(TenantAISetting, id=setting_id, tenant_id=tenant_id)
    
    if request.method == 'GET':
        serializer = TenantAISettingSerializer(ai_setting)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = TenantAISettingSerializer(ai_setting, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        ai_setting.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)