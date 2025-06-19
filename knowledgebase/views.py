# views.py
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.db.models import Count, Sum, Q, Avg
from .models import KnowledgeBaseCategory, KnowledgeBaseDocument, KnowledgeBaseDocument, 
                    KnowledgeBaseCategory, DocumentChunk, DocumentEmbedding
from tenants.models import TenantUser
from .serializers import (
    KnowledgeBaseCategoryListSerializer, KnowledgeBaseCategoryDetailSerializer,
    KnowledgeBaseCategoryCreateUpdateSerializer, DocumentListSerializer, DocumentDetailSerializer, 
    DocumentCreateSerializer,DocumentUpdateSerializer, DocumentChunkSerializer, 
    ProcessingStatusSerializer, EmbeddingStatusSerializer, DocumentReprocessSerializer
)

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from datetime import timedelta
import os
import uuid
import hashlib


@api_view(['GET', 'POST'])
def kb_category_list_create(request):
    """
    GET /api/knowledge-base/categories - List knowledge base categories
    POST /api/knowledge-base/categories - Create new KB category
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    if request.method == 'GET':
        # Get all KB categories for the tenant
        categories = KnowledgeBaseCategory.objects.filter(
            tenant_id=tenant_id
        ).prefetch_related('documents').order_by('name')
        
        # Apply filters
        is_active = request.GET.get('is_active')
        if is_active is not None:
            is_active_bool = is_active.lower() in ('true', '1', 'yes')
            categories = categories.filter(is_active=is_active_bool)
        
        # Filter by categories that have documents
        has_documents = request.GET.get('has_documents')
        if has_documents is not None:
            has_docs_bool = has_documents.lower() in ('true', '1', 'yes')
            if has_docs_bool:
                categories = categories.annotate(
                    doc_count=Count('documents', filter=Q(documents__is_active=True))
                ).filter(doc_count__gt=0)
            else:
                categories = categories.annotate(
                    doc_count=Count('documents', filter=Q(documents__is_active=True))
                ).filter(doc_count=0)
        
        # Search filter
        search = request.GET.get('search')
        if search:
            categories = categories.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search)
            )
        
        # Sort options
        sort_by = request.GET.get('sort_by', 'name')
        valid_sort_fields = ['name', '-name', 'created_at', '-created_at', 'updated_at', '-updated_at']
        
        if sort_by in valid_sort_fields:
            categories = categories.order_by(sort_by)
        elif sort_by == 'document_count':
            categories = categories.annotate(
                doc_count=Count('documents', filter=Q(documents__is_active=True))
            ).order_by('-doc_count')
        elif sort_by == '-document_count':
            categories = categories.annotate(
                doc_count=Count('documents', filter=Q(documents__is_active=True))
            ).order_by('doc_count')
        
        serializer = KnowledgeBaseCategoryListSerializer(categories, many=True)
        
        # Add summary statistics
        total_categories = categories.count()
        active_categories = categories.filter(is_active=True).count()
        
        # Get categories with documents
        categories_with_docs = categories.annotate(
            doc_count=Count('documents', filter=Q(documents__is_active=True))
        ).filter(doc_count__gt=0).count()
        
        # Get total documents and storage across all categories
        total_documents = KnowledgeBaseDocument.objects.filter(
            tenant_id=tenant_id,
            is_active=True
        ).count()
        
        total_storage = KnowledgeBaseDocument.objects.filter(
            tenant_id=tenant_id,
            is_active=True
        ).aggregate(total=Sum('file_size'))['total'] or 0
        
        response_data = {
            'results': serializer.data,
            'summary': {
                'total_categories': total_categories,
                'active_categories': active_categories,
                'categories_with_documents': categories_with_docs,
                'empty_categories': total_categories - categories_with_docs,
                'total_documents': total_documents,
                'total_storage_mb': round(total_storage / (1024 * 1024), 2),
                'avg_documents_per_category': round(total_documents / total_categories, 1) if total_categories > 0 else 0
            },
            'filters_applied': {
                'is_active': is_active,
                'has_documents': has_documents,
                'search': search,
                'sort_by': sort_by
            }
        }
        
        return Response(response_data)
    
    elif request.method == 'POST':
        serializer = KnowledgeBaseCategoryCreateUpdateSerializer(
            data=request.data,
            context={'tenant_id': tenant_id}
        )
        
        if serializer.is_valid():
            with transaction.atomic():
                category = serializer.save(tenant_id=tenant_id)
            
            # Return detailed category data
            detail_serializer = KnowledgeBaseCategoryDetailSerializer(category)
            return Response(detail_serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
def kb_category_detail(request, category_id):
    """
    GET /api/knowledge-base/categories/{category_id} - Get category details
    PUT /api/knowledge-base/categories/{category_id} - Update category
    DELETE /api/knowledge-base/categories/{category_id} - Delete category
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    category = get_object_or_404(
        KnowledgeBaseCategory.objects.prefetch_related('documents'),
        id=category_id,
        tenant_id=tenant_id
    )
    
    if request.method == 'GET':
        serializer = KnowledgeBaseCategoryDetailSerializer(category)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = KnowledgeBaseCategoryCreateUpdateSerializer(
            category,
            data=request.data,
            partial=True,
            context={'tenant_id': tenant_id}
        )
        
        if serializer.is_valid():
            with transaction.atomic():
                updated_category = serializer.save()
            
            # Return updated category details
            detail_serializer = KnowledgeBaseCategoryDetailSerializer(updated_category)
            return Response(detail_serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        # Check if category has documents
        active_documents = category.documents.filter(is_active=True)
        document_count = active_documents.count()
        
        if document_count > 0:
            # Offer options for handling documents
            force_delete = request.GET.get('force', '').lower() in ('true', '1', 'yes')
            move_to_category = request.GET.get('move_to')
            
            if not force_delete and not move_to_category:
                return Response(
                    {
                        'error': f'Cannot delete category. It contains {document_count} active documents.',
                        'document_count': document_count,
                        'options': {
                            'force_delete': 'Add ?force=true to delete category and all documents',
                            'move_documents': 'Add ?move_to=<category_id> to move documents to another category'
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            with transaction.atomic():
                if move_to_category:
                    # Move documents to another category
                    try:
                        target_category = KnowledgeBaseCategory.objects.get(
                            id=move_to_category,
                            tenant_id=tenant_id,
                            is_active=True
                        )
                        
                        # Update all documents to new category
                        moved_count = active_documents.update(category_id=target_category.id)
                        
                        # Delete the empty category
                        category.delete()
                        
                        return Response({
                            'message': f'Category deleted successfully. {moved_count} documents moved to "{target_category.name}".',
                            'moved_documents': moved_count,
                            'target_category': {
                                'id': target_category.id,
                                'name': target_category.name
                            }
                        })
                        
                    except KnowledgeBaseCategory.DoesNotExist:
                        return Response(
                            {'error': 'Target category not found or inactive.'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                
                elif force_delete:
                    # Delete all documents and their related data
                    documents_to_delete = list(active_documents.values_list('id', 'title'))
                    
                    # Delete documents (this should cascade to chunks and embeddings)
                    active_documents.delete()
                    
                    # Delete the category
                    category.delete()
                    
                    return Response({
                        'message': f'Category and {len(documents_to_delete)} documents deleted successfully.',
                        'deleted_documents': [{'id': doc[0], 'title': doc[1]} for doc in documents_to_delete]
                    })
        
        else:
            # Category is empty, safe to delete
            with transaction.atomic():
                category.delete()
            
            return Response({
                'message': 'Empty category deleted successfully.'
            }, status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'POST'])
def document_list_create(request):
    """
    GET /api/knowledge-base/documents - List documents with filters
    POST /api/knowledge-base/documents - Upload new document
    """
    tenant_id = getattr(request, 'tenant_id', None)
    current_user_id = getattr(request, 'user_id', None)
    
    if request.method == 'GET':
        # Get all documents for the tenant
        documents = KnowledgeBaseDocument.objects.filter(
            tenant_id=tenant_id
        ).select_related('category').prefetch_related('chunks')
        
        # Apply filters
        category_id = request.GET.get('category')
        if category_id:
            documents = documents.filter(category_id=category_id)
        
        processing_status = request.GET.get('status')
        if processing_status:
            documents = documents.filter(processing_status=processing_status)
        
        is_active = request.GET.get('is_active')
        if is_active is not None:
            is_active_bool = is_active.lower() in ('true', '1', 'yes')
            documents = documents.filter(is_active=is_active_bool)
        
        file_type = request.GET.get('file_type')
        if file_type:
            documents = documents.filter(file_type=file_type)
        
        language = request.GET.get('language')
        if language:
            documents = documents.filter(language=language)
        
        uploaded_by = request.GET.get('uploaded_by')
        if uploaded_by:
            documents = documents.filter(uploaded_by_user_id=uploaded_by)
        
        # Tag filter
        tags = request.GET.get('tags')
        if tags:
            tag_list = [tag.strip() for tag in tags.split(',')]
            for tag in tag_list:
                documents = documents.filter(tags__contains=[tag])
        
        # Date range filters
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')
        if from_date:
            try:
                from django.utils.dateparse import parse_datetime
                from_datetime = parse_datetime(from_date)
                if from_datetime:
                    documents = documents.filter(created_at__gte=from_datetime)
            except ValueError:
                pass
        
        if to_date:
            try:
                from django.utils.dateparse import parse_datetime
                to_datetime = parse_datetime(to_date)
                if to_datetime:
                    documents = documents.filter(created_at__lte=to_datetime)
            except ValueError:
                pass
        
        # File size filters
        min_size = request.GET.get('min_size')
        max_size = request.GET.get('max_size')
        if min_size:
            try:
                min_size_bytes = int(min_size) * 1024 * 1024  # Convert MB to bytes
                documents = documents.filter(file_size__gte=min_size_bytes)
            except ValueError:
                pass
        
        if max_size:
            try:
                max_size_bytes = int(max_size) * 1024 * 1024  # Convert MB to bytes
                documents = documents.filter(file_size__lte=max_size_bytes)
            except ValueError:
                pass
        
        # Search filter
        search = request.GET.get('search')
        if search:
            documents = documents.filter(
                Q(title__icontains=search) |
                Q(content__icontains=search) |
                Q(tags__contains=[search])
            )
        
        # Processing status filters
        has_chunks = request.GET.get('has_chunks')
        if has_chunks is not None:
            has_chunks_bool = has_chunks.lower() in ('true', '1', 'yes')
            if has_chunks_bool:
                documents = documents.annotate(
                    chunk_count=Count('chunks')
                ).filter(chunk_count__gt=0)
            else:
                documents = documents.annotate(
                    chunk_count=Count('chunks')
                ).filter(chunk_count=0)
        
        has_embeddings = request.GET.get('has_embeddings')
        if has_embeddings is not None:
            has_embeddings_bool = has_embeddings.lower() in ('true', '1', 'yes')
            if has_embeddings_bool:
                documents = documents.filter(
                    chunks__embeddings__isnull=False
                ).distinct()
            else:
                documents = documents.exclude(
                    chunks__embeddings__isnull=False
                ).distinct()
        
        # Sort options
        sort_by = request.GET.get('sort_by', '-created_at')
        valid_sort_fields = [
            'title', '-title', 'created_at', '-created_at', 'updated_at', '-updated_at',
            'file_size', '-file_size', 'processing_status', '-processing_status'
        ]
        
        if sort_by in valid_sort_fields:
            documents = documents.order_by(sort_by)
        elif sort_by == 'file_size_desc':
            documents = documents.order_by('-file_size')
        elif sort_by == 'chunks_count':
            documents = documents.annotate(
                chunk_count=Count('chunks')
            ).order_by('-chunk_count')
        
        # Pagination
        limit = min(int(request.GET.get('limit', 50)), 100)  # Max 100 documents
        offset = int(request.GET.get('offset', 0))
        
        total_count = documents.count()
        documents = documents[offset:offset + limit]
        
        serializer = DocumentListSerializer(documents, many=True)
        
        # Add summary statistics
        all_docs = KnowledgeBaseDocument.objects.filter(tenant_id=tenant_id)
        summary_stats = {
            'total_documents': all_docs.count(),
            'active_documents': all_docs.filter(is_active=True).count(),
            'processing_completed': all_docs.filter(processing_status='completed').count(),
            'processing_failed': all_docs.filter(processing_status='failed').count(),
            'processing_pending': all_docs.filter(processing_status='pending').count(),
            'processing_in_progress': all_docs.filter(processing_status='processing').count(),
            'total_storage_mb': round(
                (all_docs.aggregate(total=Sum('file_size'))['total'] or 0) / (1024 * 1024), 2
            ),
            'file_types': list(
                all_docs.values('file_type').annotate(count=Count('id')).order_by('-count')
            ),
            'languages': list(
                all_docs.values('language').annotate(count=Count('id')).order_by('-count')
            )
        }
        
        response_data = {
            'results': serializer.data,
            'pagination': {
                'total_count': total_count,
                'limit': limit,
                'offset': offset,
                'has_more': (offset + limit) < total_count
            },
            'summary': summary_stats,
            'filters_applied': {
                'category': category_id,
                'status': processing_status,
                'is_active': is_active,
                'file_type': file_type,
                'language': language,
                'uploaded_by': uploaded_by,
                'tags': tags,
                'search': search,
                'sort_by': sort_by
            }
        }
        
        return Response(response_data)
    
    elif request.method == 'POST':
        serializer = DocumentCreateSerializer(
            data=request.data,
            context={'tenant_id': tenant_id}
        )
        
        if serializer.is_valid():
            file = serializer.validated_data['file']
            
            with transaction.atomic():
                # Generate unique filename
                file_extension = os.path.splitext(file.name)[1]
                unique_filename = f"{uuid.uuid4()}{file_extension}"
                
                # Save file to storage
                file_path = f"knowledge_base/{tenant_id}/{unique_filename}"
                saved_path = default_storage.save(file_path, ContentFile(file.read()))
                
                # Create document record
                document = KnowledgeBaseDocument.objects.create(
                    tenant_id=tenant_id,
                    category_id=serializer.validated_data['category_id'],
                    uploaded_by_user_id=current_user_id,
                    title=serializer.validated_data['title'],
                    file_path=saved_path,
                    file_type=file_extension.lower().replace('.', ''),
                    file_size=file.size,
                    language=serializer.validated_data['language'],
                    tags=serializer.validated_data['tags'],
                    metadata=serializer.validated_data.get('metadata', {}),
                    processing_status='pending'
                )
                
                # Queue document for processing
                _queue_document_processing(document)
            
            # Return detailed document data
            detail_serializer = DocumentDetailSerializer(document)
            return Response(detail_serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
def document_detail(request, document_id):
    """
    GET /api/knowledge-base/documents/{document_id} - Get document details
    PUT /api/knowledge-base/documents/{document_id} - Update document metadata
    DELETE /api/knowledge-base/documents/{document_id} - Delete document
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    document = get_object_or_404(
        KnowledgeBaseDocument.objects.select_related('category').prefetch_related('chunks'),
        id=document_id,
        tenant_id=tenant_id
    )
    
    if request.method == 'GET':
        serializer = DocumentDetailSerializer(document)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = DocumentUpdateSerializer(
            document,
            data=request.data,
            partial=True,
            context={'tenant_id': tenant_id}
        )
        
        if serializer.is_valid():
            with transaction.atomic():
                updated_document = serializer.save()
            
            # Return updated document details
            detail_serializer = DocumentDetailSerializer(updated_document)
            return Response(detail_serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        # Check if document is being used in embeddings/retrievals
        has_embeddings = DocumentEmbedding.objects.filter(document_id=document.id).exists()
        
        force_delete = request.GET.get('force', '').lower() in ('true', '1', 'yes')
        
        if has_embeddings and not force_delete:
            return Response(
                {
                    'error': 'Document has associated embeddings. Add ?force=true to delete anyway.',
                    'has_embeddings': True,
                    'embedding_count': DocumentEmbedding.objects.filter(document_id=document.id).count()
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            # Delete file from storage
            if document.file_path:
                try:
                    default_storage.delete(document.file_path)
                except Exception:
                    pass  # File might already be deleted
            
            # Delete document (cascades to chunks and embeddings)
            document.delete()
        
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
def document_reprocess(request, document_id):
    """
    POST /api/knowledge-base/documents/{document_id}/reprocess - Reprocess document for embeddings
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    document = get_object_or_404(
        KnowledgeBaseDocument,
        id=document_id,
        tenant_id=tenant_id
    )
    
    serializer = DocumentReprocessSerializer(data=request.data)
    
    if serializer.is_valid():
        force_reprocess = serializer.validated_data['force_reprocess']
        regenerate_embeddings = serializer.validated_data['regenerate_embeddings']
        chunk_size = serializer.validated_data.get('chunk_size')
        chunk_overlap = serializer.validated_data.get('chunk_overlap')
        
        # Check if reprocessing is allowed
        if document.processing_status == 'processing':
            return Response(
                {'error': 'Document is currently being processed. Please wait for completion.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if document.processing_status == 'completed' and not force_reprocess:
            return Response(
                {
                    'error': 'Document already processed successfully. Use force_reprocess=true to reprocess anyway.',
                    'current_status': document.processing_status
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            # Delete existing chunks and embeddings if regenerating
            if regenerate_embeddings:
                DocumentEmbedding.objects.filter(document_id=document.id).delete()
                DocumentChunk.objects.filter(document_id=document.id).delete()
            
            # Update processing status and metadata
            processing_config = {
                'reprocessing': True,
                'reprocess_timestamp': timezone.now().isoformat(),
                'force_reprocess': force_reprocess,
                'regenerate_embeddings': regenerate_embeddings
            }
            
            if chunk_size:
                processing_config['custom_chunk_size'] = chunk_size
            if chunk_overlap:
                processing_config['custom_chunk_overlap'] = chunk_overlap
            
            document.processing_status = 'pending'
            document.metadata = {**(document.metadata or {}), **processing_config}
            document.save(update_fields=['processing_status', 'metadata', 'updated_at'])
            
            # Queue for reprocessing
            _queue_document_processing(document, is_reprocess=True)
        
        # Return updated document details
        detail_serializer = DocumentDetailSerializer(document)
        return Response({
            'message': 'Document queued for reprocessing.',
            'document': detail_serializer.data
        })
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def document_chunks(request, document_id):
    """
    GET /api/knowledge-base/documents/{document_id}/chunks - Get document chunks
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    document = get_object_or_404(
        KnowledgeBaseDocument,
        id=document_id,
        tenant_id=tenant_id
    )
    
    # Get chunks with pagination
    chunks = DocumentChunk.objects.filter(document_id=document.id).order_by('chunk_index')
    
    # Apply filters
    has_embeddings = request.GET.get('has_embeddings')
    if has_embeddings is not None:
        has_embeddings_bool = has_embeddings.lower() in ('true', '1', 'yes')
        if has_embeddings_bool:
            chunks = chunks.filter(embeddings__isnull=False).distinct()
        else:
            chunks = chunks.filter(embeddings__isnull=True)
    
    min_words = request.GET.get('min_words')
    if min_words:
        try:
            chunks = chunks.filter(word_count__gte=int(min_words))
        except ValueError:
            pass
    
    max_words = request.GET.get('max_words')
    if max_words:
        try:
            chunks = chunks.filter(word_count__lte=int(max_words))
        except ValueError:
            pass
    
    # Pagination
    limit = min(int(request.GET.get('limit', 20)), 100)
    offset = int(request.GET.get('offset', 0))
    
    total_count = chunks.count()
    chunks = chunks[offset:offset + limit]
    
    serializer = DocumentChunkSerializer(chunks, many=True)
    
    # Add chunk statistics
    all_chunks = DocumentChunk.objects.filter(document_id=document.id)
    chunk_stats = {
        'total_chunks': all_chunks.count(),
        'chunks_with_embeddings': all_chunks.filter(embeddings__isnull=False).distinct().count(),
        'avg_word_count': all_chunks.aggregate(avg=Avg('word_count'))['avg'] or 0,
        'total_words': all_chunks.aggregate(total=Sum('word_count'))['total'] or 0
    }
    
    response_data = {
        'results': serializer.data,
        'pagination': {
            'total_count': total_count,
            'limit': limit,
            'offset': offset,
            'has_more': (offset + limit) < total_count
        },
        'chunk_statistics': chunk_stats,
        'document': {
            'id': document.id,
            'title': document.title,
            'processing_status': document.processing_status
        }
    }
    
    return Response(response_data)


@api_view(['GET'])
def processing_status(request):
    """
    GET /api/knowledge-base/processing-status - Get processing queue status
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    # Get processing statistics
    documents = KnowledgeBaseDocument.objects.filter(tenant_id=tenant_id)
    
    status_counts = documents.values('processing_status').annotate(
        count=Count('id')
    )
    
    # Get recent processing activity
    recent_activity = documents.filter(
        updated_at__gte=timezone.now() - timedelta(hours=24)
    ).order_by('-updated_at')[:10]
    
    # Calculate processing queue metrics
    pending_docs = documents.filter(processing_status='pending')
    processing_docs = documents.filter(processing_status='processing')
    
    # Estimate queue time (simplified calculation)
    avg_processing_time = _calculate_avg_processing_time(tenant_id)
    estimated_queue_time = (pending_docs.count() + processing_docs.count()) * avg_processing_time
    
    processing_data = {
        'queue_status': {
            'pending': pending_docs.count(),
            'processing': processing_docs.count(),
            'completed': documents.filter(processing_status='completed').count(),
            'failed': documents.filter(processing_status='failed').count()
        },
        'status_breakdown': {item['processing_status']: item['count'] for item in status_counts},
        'queue_metrics': {
            'estimated_wait_time_minutes': round(estimated_queue_time / 60, 1),
            'avg_processing_time_minutes': round(avg_processing_time / 60, 1),
            'total_in_queue': pending_docs.count() + processing_docs.count()
        },
        'recent_activity': [{
            'document_id': doc.id,
            'title': doc.title,
            'status': doc.processing_status,
            'updated_at': doc.updated_at,
            'processing_time': _calculate_processing_time(doc)
        } for doc in recent_activity],
        'system_metrics': {
            'total_documents': documents.count(),
            'total_chunks': DocumentChunk.objects.filter(tenant_id=tenant_id).count(),
            'total_embeddings': DocumentEmbedding.objects.filter(tenant_id=tenant_id).count(),
            'storage_used_mb': round(
                (documents.aggregate(total=Sum('file_size'))['total'] or 0) / (1024 * 1024), 2
            )
        }
    }
    
    return Response(processing_data)


@api_view(['GET'])
def embedding_status(request):
    """
    GET /api/knowledge-base/embeddings/status - Get embedding generation status
    """
    tenant_id = getattr(request, 'tenant_id', None)
    
    # Get embedding statistics
    embeddings = DocumentEmbedding.objects.filter(tenant_id=tenant_id)
    chunks = DocumentChunk.objects.filter(tenant_id=tenant_id)
    
    # Group by embedding model
    model_stats = embeddings.values('embedding_model').annotate(
        count=Count('id'),
        avg_dimension=Avg('vector_dimension')
    ).order_by('-count')
    
    # Calculate coverage
    total_chunks = chunks.count()
    chunks_with_embeddings = chunks.filter(embeddings__isnull=False).distinct().count()
    coverage_percentage = (chunks_with_embeddings / total_chunks) * 100 if total_chunks > 0 else 0
    
    # Get recent embedding activity
    recent_embeddings = embeddings.order_by('-created_at')[:10]
    
    # Performance metrics
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_embeddings_count = embeddings.filter(created_at__gte=thirty_days_ago).count()
    
    embedding_data = {
        'overview': {
            'total_embeddings': embeddings.count(),
            'total_chunks': total_chunks,
            'chunks_with_embeddings': chunks_with_embeddings,
            'coverage_percentage': round(coverage_percentage, 2),
            'embedding_models_count': len(model_stats)
        },
        'model_breakdown': [{
            'model': item['embedding_model'],
            'embedding_count': item['count'],
            'avg_dimension': round(item['avg_dimension'] or 0, 0),
            'percentage': round((item['count'] / embeddings.count()) * 100, 1) if embeddings.count() > 0 else 0
        } for item in model_stats],
        'recent_activity': [{
            'document_title': embedding.document.title if embedding.document else 'Unknown',
            'chunk_index': embedding.chunk.chunk_index if embedding.chunk else 0,
            'model': embedding.embedding_model,
            'dimension': embedding.vector_dimension,
            'created_at': embedding.created_at
        } for embedding in recent_embeddings],
        'performance_metrics': {
            'embeddings_last_30_days': recent_embeddings_count,
            'avg_embeddings_per_day': round(recent_embeddings_count / 30, 1),
            'total_vector_storage_estimate_mb': round(
                (embeddings.aggregate(
                    total_vectors=Count('id'),
                    avg_dimension=Avg('vector_dimension')
                )['total_vectors'] or 0) * 
                (embeddings.aggregate(avg_dimension=Avg('vector_dimension'))['avg_dimension'] or 0) * 
                4 / (1024 * 1024), 2  # Assuming 4 bytes per float
            )
        },
        'health_status': {
            'coverage_health': 'good' if coverage_percentage > 80 else 'warning' if coverage_percentage > 50 else 'poor',
            'processing_health': 'good',  # Would be determined by processing metrics
            'storage_health': 'good'  # Would be determined by storage metrics
        }
    }
    
    return Response(embedding_data)


def _queue_document_processing(document, is_reprocess=False):
    """Queue document for processing (placeholder for actual queue implementation)"""
    # This would typically enqueue the document for processing by a background worker
    # For now, we'll just update the status to indicate it's queued
    
    # In a real implementation, you might use:
    # - Celery task queue
    # - AWS SQS
    # - Redis queue
    # - Database-based job queue
    
    pass


def _calculate_avg_processing_time(tenant_id):
    """Calculate average processing time for completed documents"""
    completed_docs = KnowledgeBaseDocument.objects.filter(
        tenant_id=tenant_id,
        processing_status='completed',
        processed_at__isnull=False
    )
    
    total_time = 0
    count = 0
    
    for doc in completed_docs:
        if doc.processed_at and doc.created_at:
            processing_time = (doc.processed_at - doc.created_at).total_seconds()
            total_time += processing_time
            count += 1
    
    return total_time / count if count > 0 else 300  # Default 5 minutes


def _calculate_processing_time(document):
    """Calculate processing time for a document"""
    if document.processed_at and document.created_at:
        delta = document.processed_at - document.created_at
        return round(delta.total_seconds() / 60, 1)  # Return in minutes
    return None