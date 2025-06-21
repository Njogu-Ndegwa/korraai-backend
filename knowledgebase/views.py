# # knowledge_base/views.py
# from rest_framework import status
# from rest_framework.decorators import api_view, permission_classes
# from rest_framework.permissions import IsAuthenticated
# from rest_framework.response import Response
# from django.shortcuts import get_object_or_404
# from django.db import transaction
# from django.utils import timezone
# from django.db.models import Count, Q
# from django.core.files.storage import default_storage
# from django.core.files.base import ContentFile
# from .models import KnowledgeBaseCategory, KnowledgeBaseDocument, DocumentChunk, DocumentEmbedding
# from .serializers import (
#     KnowledgeBaseCategorySerializer, 
#     DocumentListSerializer, 
#     DocumentDetailSerializer,
#     DocumentCreateSerializer,
#     DocumentChunkSerializer
# )
# from .utils import DocumentProcessor
# from .auth_utils import get_tenant_from_user, get_user_id_from_request
# import asyncio
# import json
# import os
# import uuid


# @api_view(['GET', 'POST'])
# @permission_classes([IsAuthenticated])
# def kb_category_list_create(request):
#     """
#     GET /api/knowledge-base/categories - List categories
#     POST /api/knowledge-base/categories - Create category
#     """
#     # Get tenant_id from authenticated user
#     tenant_id, error_response = get_tenant_from_user(request)
#     if error_response:
#         return error_response
    
#     if request.method == 'GET':
#         categories = KnowledgeBaseCategory.objects.filter(
#             tenant_id=tenant_id,
#             is_active=True
#         ).order_by('name')
        
#         serializer = KnowledgeBaseCategorySerializer(categories, many=True)
#         return Response({'results': serializer.data})
    
#     elif request.method == 'POST':
#         serializer = KnowledgeBaseCategorySerializer(
#             data=request.data,
#             context={'tenant_id': tenant_id}
#         )
        
#         if serializer.is_valid():
#             category = serializer.save(tenant_id=tenant_id)
#             return Response(
#                 KnowledgeBaseCategorySerializer(category).data, 
#                 status=status.HTTP_201_CREATED
#             )
        
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# @api_view(['GET', 'PUT', 'DELETE'])
# @permission_classes([IsAuthenticated])
# def kb_category_detail(request, category_id):
#     """Category detail operations"""
#     tenant_id, error_response = get_tenant_from_user(request)
#     if error_response:
#         return error_response
    
#     category = get_object_or_404(
#         KnowledgeBaseCategory,
#         id=category_id,
#         tenant_id=tenant_id
#     )
    
#     if request.method == 'GET':
#         serializer = KnowledgeBaseCategorySerializer(category)
#         return Response(serializer.data)
    
#     elif request.method == 'PUT':
#         serializer = KnowledgeBaseCategorySerializer(
#             category,
#             data=request.data,
#             partial=True,
#             context={'tenant_id': tenant_id}
#         )
        
#         if serializer.is_valid():
#             updated_category = serializer.save()
#             return Response(KnowledgeBaseCategorySerializer(updated_category).data)
        
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
#     elif request.method == 'DELETE':
#         active_documents = category.documents.filter(is_active=True).count()
        
#         if active_documents > 0:
#             return Response(
#                 {
#                     'error': f'Cannot delete category. It contains {active_documents} active documents.',
#                     'document_count': active_documents
#                 },
#                 status=status.HTTP_400_BAD_REQUEST
#             )
        
#         category.delete()
#         return Response(status=status.HTTP_204_NO_CONTENT)


# @api_view(['GET', 'POST'])
# @permission_classes([IsAuthenticated])
# def document_list_create(request):
#     """
#     GET /api/knowledge-base/documents - List documents
#     POST /api/knowledge-base/documents - Upload JSON document
#     """
#     tenant_id, error_response = get_tenant_from_user(request)
#     if error_response:
#         return error_response
    
#     current_user_id = get_user_id_from_request(request)
    
#     if request.method == 'GET':
#         documents = KnowledgeBaseDocument.objects.filter(
#             tenant_id=tenant_id
#         ).select_related('category').order_by('-created_at')
        
#         # Filters
#         category_id = request.GET.get('category')
#         if category_id:
#             documents = documents.filter(category_id=category_id)
            
#         processing_status = request.GET.get('status')
#         if processing_status:
#             documents = documents.filter(processing_status=processing_status)
        
#         serializer = DocumentListSerializer(documents, many=True)
#         return Response({'results': serializer.data})
    
#     elif request.method == 'POST':
#         serializer = DocumentCreateSerializer(
#             data=request.data,
#             context={'tenant_id': tenant_id}
#         )
        
#         if serializer.is_valid():
#             file = serializer.validated_data['file']
            
#             # Validate JSON file
#             if not file.name.lower().endswith('.json'):
#                 return Response(
#                     {'error': 'Only JSON files are supported currently'},
#                     status=status.HTTP_400_BAD_REQUEST
#                 )
            
#             try:
#                 # Read and validate JSON content
#                 file_content = file.read().decode('utf-8')
#                 json_data = json.loads(file_content)
                
#                 # Ensure it's a list of objects for our use case
#                 if not isinstance(json_data, list):
#                     return Response(
#                         {'error': 'JSON file must contain a list of objects'},
#                         status=status.HTTP_400_BAD_REQUEST
#                     )
                
#             except json.JSONDecodeError as e:
#                 return Response(
#                     {'error': f'Invalid JSON format: {str(e)}'},
#                     status=status.HTTP_400_BAD_REQUEST
#                 )
#             except UnicodeDecodeError:
#                 return Response(
#                     {'error': 'File encoding not supported. Use UTF-8 encoding.'},
#                     status=status.HTTP_400_BAD_REQUEST
#                 )
            
#             with transaction.atomic():
#                 # Generate unique filename
#                 unique_filename = f"{uuid.uuid4()}.json"
#                 file_path = f"knowledge_base/{tenant_id}/{unique_filename}"
                
#                 # Save file to storage
#                 saved_path = default_storage.save(
#                     file_path, 
#                     ContentFile(file_content.encode('utf-8'))
#                 )
                
#                 # Create document record
#                 document = KnowledgeBaseDocument.objects.create(
#                     tenant_id=tenant_id,
#                     category_id=serializer.validated_data['category_id'],
#                     uploaded_by_user_id=current_user_id,
#                     title=serializer.validated_data['title'],
#                     content=file_content,  # Store JSON content directly
#                     file_path=saved_path,
#                     file_type='json',
#                     file_size=len(file_content.encode('utf-8')),
#                     language=serializer.validated_data.get('language', 'en'),
#                     tags=serializer.validated_data.get('tags', []),
#                     metadata={
#                         'json_objects_count': len(json_data),
#                         'original_filename': file.name
#                     },
#                     processing_status='pending'
#                 )
            
#             # Return document details
#             detail_serializer = DocumentDetailSerializer(document)
#             return Response(detail_serializer.data, status=status.HTTP_201_CREATED)
        
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# @api_view(['GET', 'PUT', 'DELETE'])
# @permission_classes([IsAuthenticated])
# def document_detail(request, document_id):
#     """Document detail operations"""
#     tenant_id, error_response = get_tenant_from_user(request)
#     if error_response:
#         return error_response
    
#     document = get_object_or_404(
#         KnowledgeBaseDocument,
#         id=document_id,
#         tenant_id=tenant_id
#     )
    
#     if request.method == 'GET':
#         serializer = DocumentDetailSerializer(document)
#         return Response(serializer.data)
    
#     elif request.method == 'PUT':
#         # Only allow updating metadata
#         allowed_fields = ['title', 'tags', 'metadata', 'is_active']
#         update_data = {k: v for k, v in request.data.items() if k in allowed_fields}
        
#         for field, value in update_data.items():
#             setattr(document, field, value)
        
#         document.save()
        
#         serializer = DocumentDetailSerializer(document)
#         return Response(serializer.data)
    
#     elif request.method == 'DELETE':
#         with transaction.atomic():
#             # Delete file from storage
#             if document.file_path:
#                 try:
#                     default_storage.delete(document.file_path)
#                 except Exception:
#                     pass
            
#             document.delete()
        
#         return Response(status=status.HTTP_204_NO_CONTENT)


# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
# def process_document_chunks(request, document_id):
#     """
#     POST /api/knowledge-base/documents/{document_id}/process/
#     Process JSON document into chunks
#     """
#     tenant_id, error_response = get_tenant_from_user(request)

#     if error_response:
#         return error_response
    
#     document = get_object_or_404(
#         KnowledgeBaseDocument,
#         id=document_id,
#         tenant_id=tenant_id
#     )
#     print(document, "----282---")
#     if document.processing_status == 'processing':
#         return Response(
#             {'error': 'Document is already being processed'},
#             status=status.HTTP_400_BAD_REQUEST
#         )
    
#     # Get processing options
#     regenerate_chunks = request.data.get('regenerate_chunks', False)
    
#     try:
#         processor = DocumentProcessor()
        
#         # Run async processing
#         loop = asyncio.new_event_loop()
#         asyncio.set_event_loop(loop)
#         print("----297---")
#         try:
#             result = loop.run_until_complete(
#                 processor.process_json_document(
#                     document=document,
#                     regenerate_chunks=regenerate_chunks
#                 )
#             )
#         finally:
#             loop.close()
        
#         return Response(result, status=status.HTTP_200_OK)
    
#     except Exception as e:
#         print(e, "---311")
#         return Response(
#             {
#                 'success': False,
#                 'message': f'Processing failed: {str(e)}',
#                 'chunks_created': 0,
#                 'embeddings_created': 0
#             },
#             status=status.HTTP_500_INTERNAL_SERVER_ERROR
#         )


# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
# def generate_embeddings(request, document_id):
#     """
#     POST /api/knowledge-base/documents/{document_id}/embeddings/
#     Generate embeddings for document chunks
#     """
#     tenant_id, error_response = get_tenant_from_user(request)
#     if error_response:
#         return error_response
    
#     document = get_object_or_404(
#         KnowledgeBaseDocument,
#         id=document_id,
#         tenant_id=tenant_id
#     )
    
#     # Check if document has chunks
#     chunks = DocumentChunk.objects.filter(document=document)
#     if not chunks.exists():
#         return Response(
#             {'error': 'Document has no chunks. Process chunks first.'},
#             status=status.HTTP_400_BAD_REQUEST
#         )
    
#     regenerate_embeddings = request.data.get('regenerate_embeddings', False)
    
#     try:
#         processor = DocumentProcessor()
        
#         loop = asyncio.new_event_loop()
#         asyncio.set_event_loop(loop)
        
#         try:
#             result = loop.run_until_complete(
#                 processor.generate_embeddings_for_document(
#                     document=document,
#                     regenerate_embeddings=regenerate_embeddings
#                 )
#             )
#         finally:
#             loop.close()
        
#         return Response(result, status=status.HTTP_200_OK)
    
#     except Exception as e:
#         return Response(
#             {
#                 'success': False,
#                 'message': f'Embedding generation failed: {str(e)}',
#                 'embeddings_created': 0
#             },
#             status=status.HTTP_500_INTERNAL_SERVER_ERROR
#         )


# @api_view(['GET'])
# @permission_classes([IsAuthenticated])
# def document_chunks(request, document_id):
#     """Get document chunks"""
#     tenant_id, error_response = get_tenant_from_user(request)
#     if error_response:
#         return error_response
    
#     document = get_object_or_404(
#         KnowledgeBaseDocument,
#         id=document_id,
#         tenant_id=tenant_id
#     )
    
#     chunks = DocumentChunk.objects.filter(
#         document=document
#     ).order_by('chunk_index')
    
#     serializer = DocumentChunkSerializer(chunks, many=True)
    
#     return Response({
#         'document_id': str(document.id),
#         'document_title': document.title,
#         'total_chunks': chunks.count(),
#         'chunks': serializer.data
#     })


# @api_view(['GET'])
# @permission_classes([IsAuthenticated])
# def processing_status(request):
#     """Get processing status for all documents"""
#     tenant_id, error_response = get_tenant_from_user(request)
#     if error_response:
#         return error_response
    
#     documents = KnowledgeBaseDocument.objects.filter(tenant_id=tenant_id)
    
#     status_counts = documents.values('processing_status').annotate(
#         count=Count('id')
#     )
    
#     return Response({
#         'status_breakdown': {
#             item['processing_status']: item['count'] 
#             for item in status_counts
#         },
#         'total_documents': documents.count(),
#         'total_chunks': DocumentChunk.objects.filter(tenant_id=tenant_id).count(),
#         'total_embeddings': DocumentEmbedding.objects.filter(tenant_id=tenant_id).count()
#     })

# knowledge_base/views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.db.models import Count, Q
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from .models import KnowledgeBaseCategory, KnowledgeBaseDocument, DocumentChunk, DocumentEmbedding
from .serializers import (
    KnowledgeBaseCategorySerializer, 
    DocumentListSerializer, 
    DocumentDetailSerializer,
    DocumentCreateSerializer,
    DocumentChunkSerializer
)
from .utils import DocumentProcessor
from .sync_processor import SyncDocumentProcessor
from .auth_utils import get_tenant_from_user, get_user_id_from_request
import json
import os
import uuid


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def kb_category_list_create(request):
    """
    GET /api/knowledge-base/categories - List categories
    POST /api/knowledge-base/categories - Create category
    """
    # Get tenant_id from authenticated user
    tenant_id, error_response = get_tenant_from_user(request)
    if error_response:
        return error_response
    
    if request.method == 'GET':
        categories = KnowledgeBaseCategory.objects.filter(
            tenant_id=tenant_id,
            is_active=True
        ).order_by('name')
        
        serializer = KnowledgeBaseCategorySerializer(categories, many=True)
        return Response({'results': serializer.data})
    
    elif request.method == 'POST':
        serializer = KnowledgeBaseCategorySerializer(
            data=request.data,
            context={'tenant_id': tenant_id}
        )
        
        if serializer.is_valid():
            category = serializer.save(tenant_id=tenant_id)
            return Response(
                KnowledgeBaseCategorySerializer(category).data, 
                status=status.HTTP_201_CREATED
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def kb_category_detail(request, category_id):
    """Category detail operations"""
    tenant_id, error_response = get_tenant_from_user(request)
    if error_response:
        return error_response
    
    category = get_object_or_404(
        KnowledgeBaseCategory,
        id=category_id,
        tenant_id=tenant_id
    )
    
    if request.method == 'GET':
        serializer = KnowledgeBaseCategorySerializer(category)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = KnowledgeBaseCategorySerializer(
            category,
            data=request.data,
            partial=True,
            context={'tenant_id': tenant_id}
        )
        
        if serializer.is_valid():
            updated_category = serializer.save()
            return Response(KnowledgeBaseCategorySerializer(updated_category).data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        active_documents = category.documents.filter(is_active=True).count()
        
        if active_documents > 0:
            return Response(
                {
                    'error': f'Cannot delete category. It contains {active_documents} active documents.',
                    'document_count': active_documents
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def document_list_create(request):
    """
    GET /api/knowledge-base/documents - List documents
    POST /api/knowledge-base/documents - Upload JSON document
    """
    tenant_id, error_response = get_tenant_from_user(request)
    if error_response:
        return error_response
    
    current_user_id = get_user_id_from_request(request)
    
    if request.method == 'GET':
        documents = KnowledgeBaseDocument.objects.filter(
            tenant_id=tenant_id
        ).select_related('category').order_by('-created_at')
        
        # Filters
        category_id = request.GET.get('category')
        if category_id:
            documents = documents.filter(category_id=category_id)
            
        processing_status = request.GET.get('status')
        if processing_status:
            documents = documents.filter(processing_status=processing_status)
        
        serializer = DocumentListSerializer(documents, many=True)
        return Response({'results': serializer.data})
    
    elif request.method == 'POST':
        serializer = DocumentCreateSerializer(
            data=request.data,
            context={'tenant_id': tenant_id}
        )
        
        if serializer.is_valid():
            file = serializer.validated_data['file']
            
            # Validate JSON file
            if not file.name.lower().endswith('.json'):
                return Response(
                    {'error': 'Only JSON files are supported currently'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                # Read and validate JSON content
                file_content = file.read().decode('utf-8')
                json_data = json.loads(file_content)
                
                # Ensure it's a list of objects for our use case
                if not isinstance(json_data, list):
                    return Response(
                        {'error': 'JSON file must contain a list of objects'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
            except json.JSONDecodeError as e:
                return Response(
                    {'error': f'Invalid JSON format: {str(e)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            except UnicodeDecodeError:
                return Response(
                    {'error': 'File encoding not supported. Use UTF-8 encoding.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            with transaction.atomic():
                # Generate unique filename
                unique_filename = f"{uuid.uuid4()}.json"
                file_path = f"knowledge_base/{tenant_id}/{unique_filename}"
                
                # Save file to storage
                saved_path = default_storage.save(
                    file_path, 
                    ContentFile(file_content.encode('utf-8'))
                )
                
                # Create document record
                document = KnowledgeBaseDocument.objects.create(
                    tenant_id=tenant_id,
                    category_id=serializer.validated_data['category_id'],
                    uploaded_by_user_id=current_user_id,
                    title=serializer.validated_data['title'],
                    content=file_content,  # Store JSON content directly
                    file_path=saved_path,
                    file_type='json',
                    file_size=len(file_content.encode('utf-8')),
                    language=serializer.validated_data.get('language', 'en'),
                    tags=serializer.validated_data.get('tags', []),
                    metadata={
                        'json_objects_count': len(json_data),
                        'original_filename': file.name
                    },
                    processing_status='pending'
                )
            
            # Return document details
            detail_serializer = DocumentDetailSerializer(document)
            return Response(detail_serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def document_detail(request, document_id):
    """Document detail operations"""
    tenant_id, error_response = get_tenant_from_user(request)
    if error_response:
        return error_response
    
    document = get_object_or_404(
        KnowledgeBaseDocument,
        id=document_id,
        tenant_id=tenant_id
    )
    
    if request.method == 'GET':
        serializer = DocumentDetailSerializer(document)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        # Only allow updating metadata
        allowed_fields = ['title', 'tags', 'metadata', 'is_active']
        update_data = {k: v for k, v in request.data.items() if k in allowed_fields}
        
        for field, value in update_data.items():
            setattr(document, field, value)
        
        document.save()
        
        serializer = DocumentDetailSerializer(document)
        return Response(serializer.data)
    
    elif request.method == 'DELETE':
        with transaction.atomic():
            # Delete file from storage
            if document.file_path:
                try:
                    default_storage.delete(document.file_path)
                except Exception:
                    pass
            
            document.delete()
        
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def process_document_chunks(request, document_id):
    """
    POST /api/knowledge-base/documents/{document_id}/process/
    Process JSON document into chunks
    """
    tenant_id, error_response = get_tenant_from_user(request)
    if error_response:
        return error_response
    
    document = get_object_or_404(
        KnowledgeBaseDocument,
        id=document_id,
        tenant_id=tenant_id
    )
    
    # if document.processing_status == 'processing':
    #     return Response(
    #         {'error': 'Document is already being processed'},
    #         status=status.HTTP_400_BAD_REQUEST
    #     )
    
    # Get processing options
    regenerate_chunks = request.data.get('regenerate_chunks', False)
    
    try:
        processor = SyncDocumentProcessor()
        
        # Use synchronous processing - no async issues
        result = processor.process_json_document(
            document=document,
            regenerate_chunks=regenerate_chunks
        )
        
        return Response(result, status=status.HTTP_200_OK)
    
    except Exception as e:
        print(f"Processing error: {str(e)}")
        return Response(
            {
                'success': False,
                'message': f'Processing failed: {str(e)}',
                'chunks_created': 0,
                'embeddings_created': 0
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_embeddings(request, document_id):
    """
    POST /api/knowledge-base/documents/{document_id}/embeddings/
    Generate embeddings for document chunks
    """
    tenant_id, error_response = get_tenant_from_user(request)
    if error_response:
        return error_response
    
    document = get_object_or_404(
        KnowledgeBaseDocument,
        id=document_id,
        tenant_id=tenant_id
    )
    
    # Check if document has chunks
    chunks = DocumentChunk.objects.filter(document=document)
    if not chunks.exists():
        return Response(
            {'error': 'Document has no chunks. Process chunks first.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    regenerate_embeddings = request.data.get('regenerate_embeddings', False)
    
    try:
        processor = SyncDocumentProcessor()
        
        # Use synchronous processing - no async issues
        result = processor.generate_embeddings_for_document(
            document=document,
            regenerate_embeddings=regenerate_embeddings
        )
        
        return Response(result, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response(
            {
                'success': False,
                'message': f'Embedding generation failed: {str(e)}',
                'embeddings_created': 0
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def document_chunks(request, document_id):
    """Get document chunks"""
    tenant_id, error_response = get_tenant_from_user(request)
    if error_response:
        return error_response
    
    document = get_object_or_404(
        KnowledgeBaseDocument,
        id=document_id,
        tenant_id=tenant_id
    )
    
    chunks = DocumentChunk.objects.filter(
        document=document
    ).order_by('chunk_index')
    
    serializer = DocumentChunkSerializer(chunks, many=True)
    
    return Response({
        'document_id': str(document.id),
        'document_title': document.title,
        'total_chunks': chunks.count(),
        'chunks': serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def processing_status(request):
    """Get processing status for all documents"""
    tenant_id, error_response = get_tenant_from_user(request)
    if error_response:
        return error_response
    
    documents = KnowledgeBaseDocument.objects.filter(tenant_id=tenant_id)
    
    status_counts = documents.values('processing_status').annotate(
        count=Count('id')
    )
    
    return Response({
        'status_breakdown': {
            item['processing_status']: item['count'] 
            for item in status_counts
        },
        'total_documents': documents.count(),
        'total_chunks': DocumentChunk.objects.filter(tenant_id=tenant_id).count(),
        'total_embeddings': DocumentEmbedding.objects.filter(tenant_id=tenant_id).count()
    })