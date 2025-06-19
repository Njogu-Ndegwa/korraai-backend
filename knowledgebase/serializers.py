# serializers.py
from rest_framework import serializers
from .models import KnowledgeBaseCategory, KnowledgeBaseDocument, DocumentChunk, DocumentEmbedding
from django.db.models import Count, Sum, Avg
from django.utils import timezone
from datetime import timedelta
from .models import (
    KnowledgeBaseDocument, KnowledgeBaseCategory, DocumentChunk, 
    DocumentEmbedding, TenantUser
)
from django.core.validators import FileExtensionValidator
import os


class KnowledgeBaseCategoryListSerializer(serializers.ModelSerializer):
    """Serializer for listing knowledge base categories"""
    document_count = serializers.SerializerMethodField()
    total_chunks = serializers.SerializerMethodField()
    total_size_mb = serializers.SerializerMethodField()
    last_updated = serializers.SerializerMethodField()
    usage_count = serializers.SerializerMethodField()
    
    class Meta:
        model = KnowledgeBaseCategory
        fields = [
            'id', 'name', 'description', 'color_code', 'is_active',
            'document_count', 'total_chunks', 'total_size_mb',
            'last_updated', 'usage_count', 'created_at', 'updated_at'
        ]
    
    def get_document_count(self, obj):
        """Get count of documents in this category"""
        return obj.documents.filter(is_active=True).count()
    
    def get_total_chunks(self, obj):
        """Get total number of chunks across all documents"""
        return DocumentChunk.objects.filter(
            document__category_id=obj.id,
            document__is_active=True
        ).count()
    
    def get_total_size_mb(self, obj):
        """Get total size of all documents in MB"""
        total_bytes = obj.documents.filter(
            is_active=True
        ).aggregate(
            total=Sum('file_size')
        )['total'] or 0
        
        return round(total_bytes / (1024 * 1024), 2)
    
    def get_last_updated(self, obj):
        """Get timestamp of most recently updated document"""
        latest_doc = obj.documents.filter(
            is_active=True
        ).order_by('-updated_at').first()
        
        return latest_doc.updated_at if latest_doc else obj.updated_at
    
    def get_usage_count(self, obj):
        """Get usage count in last 30 days from knowledge retrieval logs"""
        thirty_days_ago = timezone.now() - timedelta(days=30)
        
        # This would come from KnowledgeRetrievalLogs
        from .models import KnowledgeRetrievalLog
        return KnowledgeRetrievalLog.objects.filter(
            tenant_id=obj.tenant_id,
            retrieved_chunks__contains=[{'document_id__in': obj.documents.values_list('id', flat=True)}],
            created_at__gte=thirty_days_ago
        ).count()


class KnowledgeBaseCategoryDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed knowledge base category view"""
    document_statistics = serializers.SerializerMethodField()
    content_breakdown = serializers.SerializerMethodField()
    recent_documents = serializers.SerializerMethodField()
    usage_analytics = serializers.SerializerMethodField()
    performance_metrics = serializers.SerializerMethodField()
    storage_info = serializers.SerializerMethodField()
    
    class Meta:
        model = KnowledgeBaseCategory
        fields = [
            'id', 'name', 'description', 'color_code', 'is_active',
            'document_statistics', 'content_breakdown', 'recent_documents',
            'usage_analytics', 'performance_metrics', 'storage_info',
            'created_at', 'updated_at'
        ]
    
    def get_document_statistics(self, obj):
        """Get comprehensive document statistics"""
        documents = obj.documents.filter(is_active=True)
        
        # Count by processing status
        status_counts = documents.values('processing_status').annotate(
            count=Count('id')
        )
        
        # Count by file type
        type_counts = documents.values('file_type').annotate(
            count=Count('id')
        )
        
        # Count by language
        language_counts = documents.values('language').annotate(
            count=Count('id')
        )
        
        return {
            'total_documents': documents.count(),
            'processing_status': {item['processing_status']: item['count'] for item in status_counts},
            'file_types': {item['file_type']: item['count'] for item in type_counts},
            'languages': {item['language']: item['count'] for item in language_counts},
            'processed_documents': documents.filter(processing_status='completed').count(),
            'failed_documents': documents.filter(processing_status='failed').count(),
            'pending_documents': documents.filter(processing_status='pending').count()
        }
    
    def get_content_breakdown(self, obj):
        """Get content analysis breakdown"""
        documents = obj.documents.filter(is_active=True, processing_status='completed')
        
        if not documents.exists():
            return {
                'total_chunks': 0,
                'avg_chunk_size': 0,
                'total_word_count': 0,
                'avg_words_per_chunk': 0,
                'chunk_distribution': {}
            }
        
        # Get chunk statistics
        chunks = DocumentChunk.objects.filter(document__in=documents)
        total_chunks = chunks.count()
        
        if total_chunks == 0:
            return {
                'total_chunks': 0,
                'avg_chunk_size': 0,
                'total_word_count': 0,
                'avg_words_per_chunk': 0,
                'chunk_distribution': {}
            }
        
        total_words = chunks.aggregate(total=Sum('word_count'))['total'] or 0
        avg_words = chunks.aggregate(avg=Avg('word_count'))['avg'] or 0
        
        # Chunk size distribution
        chunk_ranges = {
            'small': (0, 100),
            'medium': (100, 300),
            'large': (300, 500),
            'extra_large': (500, float('inf'))
        }
        
        distribution = {}
        for range_name, (min_words, max_words) in chunk_ranges.items():
            if max_words == float('inf'):
                count = chunks.filter(word_count__gte=min_words).count()
            else:
                count = chunks.filter(word_count__gte=min_words, word_count__lt=max_words).count()
            distribution[range_name] = count
        
        return {
            'total_chunks': total_chunks,
            'avg_chunk_size': round(avg_words, 1),
            'total_word_count': total_words,
            'avg_words_per_chunk': round(avg_words, 1),
            'chunk_distribution': distribution
        }
    
    def get_recent_documents(self, obj):
        """Get recently added/updated documents"""
        recent_docs = obj.documents.filter(
            is_active=True
        ).order_by('-updated_at')[:5]
        
        return [{
            'id': doc.id,
            'title': doc.title,
            'file_type': doc.file_type,
            'file_size': doc.file_size,
            'processing_status': doc.processing_status,
            'language': doc.language,
            'uploaded_by': self._get_user_name(doc.uploaded_by_user_id),
            'updated_at': doc.updated_at,
            'processed_at': doc.processed_at
        } for doc in recent_docs]
    
    def get_usage_analytics(self, obj):
        """Get usage analytics for this category"""
        thirty_days_ago = timezone.now() - timedelta(days=30)
        seven_days_ago = timezone.now() - timedelta(days=7)
        
        from .models import KnowledgeRetrievalLog
        
        # Get document IDs for this category
        doc_ids = list(obj.documents.values_list('id', flat=True))
        
        if not doc_ids:
            return {
                'retrievals_30d': 0,
                'retrievals_7d': 0,
                'unique_queries': 0,
                'avg_similarity_score': 0.0,
                'most_retrieved_document': None,
                'usage_trend': 'stable'
            }
        
        # Count retrievals where documents from this category were used
        retrievals_30d = KnowledgeRetrievalLog.objects.filter(
            tenant_id=obj.tenant_id,
            created_at__gte=thirty_days_ago
        ).extra(
            where=["retrieved_chunks::text LIKE ANY(%s)"],
            params=[['%"document_id": "' + str(doc_id) + '"%' for doc_id in doc_ids]]
        ).count()
        
        retrievals_7d = KnowledgeRetrievalLog.objects.filter(
            tenant_id=obj.tenant_id,
            created_at__gte=seven_days_ago
        ).extra(
            where=["retrieved_chunks::text LIKE ANY(%s)"],
            params=[['%"document_id": "' + str(doc_id) + '"%' for doc_id in doc_ids]]
        ).count()
        
        # Calculate trend
        prev_7d = retrievals_30d - retrievals_7d
        trend = 'stable'
        if retrievals_7d > prev_7d:
            trend = 'increasing'
        elif retrievals_7d < prev_7d:
            trend = 'decreasing'
        
        # Get unique queries count (approximation)
        unique_queries = KnowledgeRetrievalLog.objects.filter(
            tenant_id=obj.tenant_id,
            created_at__gte=thirty_days_ago
        ).values('query_text').distinct().count()
        
        # Get average similarity score
        avg_similarity = KnowledgeRetrievalLog.objects.filter(
            tenant_id=obj.tenant_id,
            created_at__gte=thirty_days_ago
        ).aggregate(avg=Avg('similarity_scores'))['avg'] or 0.0
        
        # Get most retrieved document
        most_retrieved_doc = None
        if doc_ids:
            # This is a simplified approach - in practice you'd analyze the retrieved_chunks JSON
            most_retrieved_doc = obj.documents.filter(is_active=True).order_by('-updated_at').first()
            if most_retrieved_doc:
                most_retrieved_doc = {
                    'id': most_retrieved_doc.id,
                    'title': most_retrieved_doc.title,
                    'retrieval_count': 0  # Would be calculated from actual logs
                }
        
        return {
            'retrievals_30d': retrievals_30d,
            'retrievals_7d': retrievals_7d,
            'unique_queries': unique_queries,
            'avg_similarity_score': round(avg_similarity, 3),
            'most_retrieved_document': most_retrieved_doc,
            'usage_trend': trend
        }
    
    def get_performance_metrics(self, obj):
        """Get performance metrics for this category"""
        documents = obj.documents.filter(is_active=True, processing_status='completed')
        
        if not documents.exists():
            return {
                'avg_processing_time': 0,
                'success_rate': 0.0,
                'avg_embeddings_per_doc': 0,
                'index_coverage': 0.0
            }
        
        # Calculate average processing time
        processed_docs = documents.filter(processed_at__isnull=False)
        avg_processing_time = 0
        if processed_docs.exists():
            processing_times = []
            for doc in processed_docs:
                if doc.processed_at and doc.created_at:
                    delta = doc.processed_at - doc.created_at
                    processing_times.append(delta.total_seconds())
            
            if processing_times:
                avg_processing_time = sum(processing_times) / len(processing_times)
        
        # Calculate success rate
        total_docs = obj.documents.count()
        successful_docs = documents.count()
        success_rate = (successful_docs / total_docs) * 100 if total_docs > 0 else 0
        
        # Calculate average embeddings per document
        total_embeddings = DocumentEmbedding.objects.filter(
            document__in=documents
        ).count()
        avg_embeddings = total_embeddings / documents.count() if documents.count() > 0 else 0
        
        # Index coverage (percentage of chunks that have embeddings)
        total_chunks = DocumentChunk.objects.filter(document__in=documents).count()
        chunks_with_embeddings = DocumentChunk.objects.filter(
            document__in=documents,
            embeddings__isnull=False
        ).distinct().count()
        
        index_coverage = (chunks_with_embeddings / total_chunks) * 100 if total_chunks > 0 else 0
        
        return {
            'avg_processing_time': round(avg_processing_time, 2),
            'success_rate': round(success_rate, 2),
            'avg_embeddings_per_doc': round(avg_embeddings, 1),
            'index_coverage': round(index_coverage, 2)
        }
    
    def get_storage_info(self, obj):
        """Get storage information for this category"""
        documents = obj.documents.filter(is_active=True)
        
        total_size = documents.aggregate(total=Sum('file_size'))['total'] or 0
        
        # Size breakdown by file type
        size_by_type = documents.values('file_type').annotate(
            total_size=Sum('file_size'),
            count=Count('id')
        ).order_by('-total_size')
        
        # Convert to MB and add percentage
        size_breakdown = []
        for item in size_by_type:
            size_mb = item['total_size'] / (1024 * 1024) if item['total_size'] else 0
            percentage = (item['total_size'] / total_size) * 100 if total_size > 0 else 0
            
            size_breakdown.append({
                'file_type': item['file_type'],
                'size_mb': round(size_mb, 2),
                'count': item['count'],
                'percentage': round(percentage, 1)
            })
        
        return {
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'total_size_gb': round(total_size / (1024 * 1024 * 1024), 3),
            'breakdown_by_type': size_breakdown,
            'avg_file_size_mb': round((total_size / documents.count()) / (1024 * 1024), 2) if documents.count() > 0 else 0
        }
    
    def _get_user_name(self, user_id):
        """Helper to get user name"""
        if user_id:
            try:
                from .models import TenantUser
                user = TenantUser.objects.get(id=user_id)
                return f"{user.first_name} {user.last_name}".strip()
            except TenantUser.DoesNotExist:
                return "Unknown User"
        return None


class KnowledgeBaseCategoryCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating knowledge base categories"""
    
    class Meta:
        model = KnowledgeBaseCategory
        fields = [
            'name', 'description', 'color_code', 'is_active'
        ]
    
    def validate_name(self, value):
        """Validate category name"""
        if not value or not value.strip():
            raise serializers.ValidationError("Category name is required.")
        
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Category name must be at least 2 characters long.")
        
        if len(value) > 100:
            raise serializers.ValidationError("Category name cannot exceed 100 characters.")
        
        # Check uniqueness within tenant
        tenant_id = self.context.get('tenant_id')
        instance = getattr(self, 'instance', None)
        
        queryset = KnowledgeBaseCategory.objects.filter(
            tenant_id=tenant_id,
            name__iexact=value.strip()
        )
        
        if instance:
            queryset = queryset.exclude(id=instance.id)
        
        if queryset.exists():
            raise serializers.ValidationError("A category with this name already exists.")
        
        return value.strip()
    
    def validate_description(self, value):
        """Validate category description"""
        if value and len(value) > 500:
            raise serializers.ValidationError("Description cannot exceed 500 characters.")
        
        return value.strip() if value else value
    
    def validate_color_code(self, value):
        """Validate color code format"""
        if value:
            import re
            if not re.match(r'^#[0-9A-Fa-f]{6}$', value):
                raise serializers.ValidationError("Color code must be in format #RRGGBB")
        
        return value
    
    def validate(self, data):
        """Cross-field validation"""
        # Set default color if not provided
        if not data.get('color_code'):
            # Generate a default color based on name hash
            import hashlib
            name = data.get('name', '')
            hash_obj = hashlib.md5(name.encode())
            color_int = int(hash_obj.hexdigest()[:6], 16)
            data['color_code'] = f"#{color_int:06x}"
        
        return data




class DocumentListSerializer(serializers.ModelSerializer):
    """Serializer for listing documents with essential info"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_color = serializers.CharField(source='category.color_code', read_only=True)
    uploaded_by_name = serializers.SerializerMethodField()
    file_size_mb = serializers.SerializerMethodField()
    chunk_count = serializers.SerializerMethodField()
    embedding_count = serializers.SerializerMethodField()
    processing_progress = serializers.SerializerMethodField()
    last_accessed = serializers.SerializerMethodField()
    
    class Meta:
        model = KnowledgeBaseDocument
        fields = [
            'id', 'title', 'file_type', 'file_size', 'file_size_mb',
            'language', 'processing_status', 'is_active', 'category_name',
            'category_color', 'uploaded_by_name', 'chunk_count', 'embedding_count',
            'processing_progress', 'last_accessed', 'created_at', 'updated_at',
            'processed_at'
        ]
    
    def get_uploaded_by_name(self, obj):
        """Get uploader's name"""
        if obj.uploaded_by_user_id:
            try:
                user = TenantUser.objects.get(id=obj.uploaded_by_user_id)
                return f"{user.first_name} {user.last_name}".strip()
            except TenantUser.DoesNotExist:
                return "Unknown User"
        return None
    
    def get_file_size_mb(self, obj):
        """Convert file size to MB"""
        if obj.file_size:
            return round(obj.file_size / (1024 * 1024), 2)
        return 0
    
    def get_chunk_count(self, obj):
        """Get number of chunks for this document"""
        return obj.chunks.count()
    
    def get_embedding_count(self, obj):
        """Get number of embeddings for this document"""
        return DocumentEmbedding.objects.filter(document_id=obj.id).count()
    
    def get_processing_progress(self, obj):
        """Calculate processing progress percentage"""
        if obj.processing_status == 'completed':
            return 100
        elif obj.processing_status == 'failed':
            return 0
        elif obj.processing_status == 'processing':
            # Estimate based on chunks vs embeddings
            total_chunks = obj.chunks.count()
            if total_chunks > 0:
                embeddings_count = DocumentEmbedding.objects.filter(document_id=obj.id).count()
                return min(round((embeddings_count / total_chunks) * 100, 1), 99)
            return 10  # Just started processing
        else:  # pending
            return 0
    
    def get_last_accessed(self, obj):
        """Get last access time from knowledge retrieval logs"""
        # This would come from KnowledgeRetrievalLog
        from .models import KnowledgeRetrievalLog
        last_retrieval = KnowledgeRetrievalLog.objects.filter(
            tenant_id=obj.tenant_id,
            retrieved_chunks__contains=[{'document_id': str(obj.id)}]
        ).order_by('-created_at').first()
        
        return last_retrieval.created_at if last_retrieval else None


class DocumentDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed document view"""
    category_details = serializers.SerializerMethodField()
    uploaded_by_details = serializers.SerializerMethodField()
    file_info = serializers.SerializerMethodField()
    processing_info = serializers.SerializerMethodField()
    content_analysis = serializers.SerializerMethodField()
    embedding_statistics = serializers.SerializerMethodField()
    usage_statistics = serializers.SerializerMethodField()
    related_documents = serializers.SerializerMethodField()
    
    class Meta:
        model = KnowledgeBaseDocument
        fields = [
            'id', 'title', 'content', 'file_path', 'file_type', 'file_size',
            'language', 'tags', 'metadata', 'processing_status', 'is_active',
            'category_details', 'uploaded_by_details', 'file_info', 'processing_info',
            'content_analysis', 'embedding_statistics', 'usage_statistics',
            'related_documents', 'created_at', 'updated_at', 'processed_at'
        ]
    
    def get_category_details(self, obj):
        """Get category information"""
        if obj.category:
            return {
                'id': obj.category.id,
                'name': obj.category.name,
                'description': obj.category.description,
                'color_code': obj.category.color_code,
                'is_active': obj.category.is_active
            }
        return None
    
    def get_uploaded_by_details(self, obj):
        """Get uploader information"""
        if obj.uploaded_by_user_id:
            try:
                user = TenantUser.objects.get(id=obj.uploaded_by_user_id)
                return {
                    'id': user.id,
                    'name': f"{user.first_name} {user.last_name}".strip(),
                    'email': user.email,
                    'role': user.role
                }
            except TenantUser.DoesNotExist:
                return {'name': 'Unknown User'}
        return None
    
    def get_file_info(self, obj):
        """Get comprehensive file information"""
        file_extension = os.path.splitext(obj.file_path or '')[1].lower()
        
        return {
            'original_filename': os.path.basename(obj.file_path) if obj.file_path else None,
            'file_extension': file_extension,
            'file_size_bytes': obj.file_size,
            'file_size_mb': round(obj.file_size / (1024 * 1024), 2) if obj.file_size else 0,
            'file_size_human': self._format_file_size(obj.file_size),
            'mime_type': self._get_mime_type(file_extension),
            'is_text_file': file_extension in ['.txt', '.md', '.rtf'],
            'is_document': file_extension in ['.pdf', '.doc', '.docx'],
            'is_spreadsheet': file_extension in ['.xls', '.xlsx', '.csv']
        }
    
    def get_processing_info(self, obj):
        """Get processing information"""
        processing_time = None
        if obj.processed_at and obj.created_at:
            delta = obj.processed_at - obj.created_at
            processing_time = delta.total_seconds()
        
        return {
            'status': obj.processing_status,
            'processing_time_seconds': processing_time,
            'processing_time_human': self._format_duration(processing_time) if processing_time else None,
            'processed_at': obj.processed_at,
            'error_message': obj.metadata.get('error_message') if obj.metadata else None,
            'retry_count': obj.metadata.get('retry_count', 0) if obj.metadata else 0,
            'can_reprocess': obj.processing_status in ['failed', 'completed']
        }
    
    def get_content_analysis(self, obj):
        """Get content analysis information"""
        chunks = obj.chunks.all()
        
        if not chunks.exists():
            return {
                'total_chunks': 0,
                'total_words': 0,
                'avg_words_per_chunk': 0,
                'content_preview': obj.content[:200] + '...' if obj.content and len(obj.content) > 200 else obj.content,
                'estimated_reading_time': 0
            }
        
        total_words = sum(chunk.word_count for chunk in chunks if chunk.word_count)
        avg_words = total_words / chunks.count() if chunks.count() > 0 else 0
        
        # Estimate reading time (average 200 words per minute)
        reading_time_minutes = total_words / 200 if total_words > 0 else 0
        
        return {
            'total_chunks': chunks.count(),
            'total_words': total_words,
            'avg_words_per_chunk': round(avg_words, 1),
            'content_preview': obj.content[:200] + '...' if obj.content and len(obj.content) > 200 else obj.content,
            'estimated_reading_time': round(reading_time_minutes, 1),
            'chunk_size_distribution': self._get_chunk_distribution(chunks)
        }
    
    def get_embedding_statistics(self, obj):
        """Get embedding statistics"""
        embeddings = DocumentEmbedding.objects.filter(document_id=obj.id)
        chunks = obj.chunks.all()
        
        if not embeddings.exists():
            return {
                'total_embeddings': 0,
                'chunks_with_embeddings': 0,
                'coverage_percentage': 0,
                'embedding_models_used': [],
                'avg_vector_dimension': 0
            }
        
        chunks_with_embeddings = embeddings.values('chunk_id').distinct().count()
        coverage = (chunks_with_embeddings / chunks.count()) * 100 if chunks.count() > 0 else 0
        
        models_used = embeddings.values_list('embedding_model', flat=True).distinct()
        avg_dimension = embeddings.aggregate(avg=Avg('vector_dimension'))['avg'] or 0
        
        return {
            'total_embeddings': embeddings.count(),
            'chunks_with_embeddings': chunks_with_embeddings,
            'coverage_percentage': round(coverage, 1),
            'embedding_models_used': list(models_used),
            'avg_vector_dimension': round(avg_dimension, 0)
        }
    
    def get_usage_statistics(self, obj):
        """Get usage statistics from knowledge retrieval logs"""
        from .models import KnowledgeRetrievalLog
        from datetime import timedelta
        
        thirty_days_ago = timezone.now() - timedelta(days=30)
        
        # Count retrievals that used chunks from this document
        total_retrievals = KnowledgeRetrievalLog.objects.filter(
            tenant_id=obj.tenant_id,
            retrieved_chunks__contains=[{'document_id': str(obj.id)}]
        ).count()
        
        recent_retrievals = KnowledgeRetrievalLog.objects.filter(
            tenant_id=obj.tenant_id,
            retrieved_chunks__contains=[{'document_id': str(obj.id)}],
            created_at__gte=thirty_days_ago
        ).count()
        
        # Get average similarity scores
        avg_similarity = KnowledgeRetrievalLog.objects.filter(
            tenant_id=obj.tenant_id,
            retrieved_chunks__contains=[{'document_id': str(obj.id)}]
        ).aggregate(avg=Avg('similarity_scores'))['avg'] or 0
        
        return {
            'total_retrievals': total_retrievals,
            'recent_retrievals_30d': recent_retrievals,
            'avg_similarity_score': round(avg_similarity, 3),
            'last_retrieved': self._get_last_retrieval_date(obj),
            'popularity_rank': 0  # Would be calculated relative to other documents
        }
    
    def get_related_documents(self, obj):
        """Get documents in the same category or with similar tags"""
        related = KnowledgeBaseDocument.objects.filter(
            tenant_id=obj.tenant_id,
            category=obj.category,
            is_active=True
        ).exclude(id=obj.id).order_by('-created_at')[:5]
        
        return [{
            'id': doc.id,
            'title': doc.title,
            'file_type': doc.file_type,
            'similarity_score': 0.85,  # Placeholder - would use ML similarity
            'created_at': doc.created_at
        } for doc in related]
    
    def _format_file_size(self, size_bytes):
        """Format file size in human readable format"""
        if not size_bytes:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def _format_duration(self, seconds):
        """Format duration in human readable format"""
        if seconds < 60:
            return f"{seconds:.1f} seconds"
        elif seconds < 3600:
            return f"{seconds/60:.1f} minutes"
        else:
            return f"{seconds/3600:.1f} hours"
    
    def _get_mime_type(self, extension):
        """Get MIME type from file extension"""
        mime_types = {
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.csv': 'text/csv',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        }
        return mime_types.get(extension, 'application/octet-stream')
    
    def _get_chunk_distribution(self, chunks):
        """Get chunk size distribution"""
        distribution = {'small': 0, 'medium': 0, 'large': 0, 'extra_large': 0}
        
        for chunk in chunks:
            word_count = chunk.word_count or 0
            if word_count < 100:
                distribution['small'] += 1
            elif word_count < 300:
                distribution['medium'] += 1
            elif word_count < 500:
                distribution['large'] += 1
            else:
                distribution['extra_large'] += 1
        
        return distribution
    
    def _get_last_retrieval_date(self, obj):
        """Get last retrieval date for this document"""
        from .models import KnowledgeRetrievalLog
        
        last_retrieval = KnowledgeRetrievalLog.objects.filter(
            tenant_id=obj.tenant_id,
            retrieved_chunks__contains=[{'document_id': str(obj.id)}]
        ).order_by('-created_at').first()
        
        return last_retrieval.created_at if last_retrieval else None


class DocumentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/uploading new documents"""
    file = serializers.FileField(
        required=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=[
                    'pdf', 'doc', 'docx', 'txt', 'md', 'rtf',
                    'csv', 'xls', 'xlsx', 'ppt', 'pptx'
                ]
            )
        ]
    )
    
    class Meta:
        model = KnowledgeBaseDocument
        fields = [
            'title', 'category_id', 'language', 'tags', 'metadata', 'file'
        ]
    
    def validate_file(self, value):
        """Validate uploaded file"""
        # Check file size (max 50MB)
        max_size = 50 * 1024 * 1024  # 50MB
        if value.size > max_size:
            raise serializers.ValidationError("File size cannot exceed 50MB.")
        
        # Check if file is not empty
        if value.size == 0:
            raise serializers.ValidationError("File cannot be empty.")
        
        return value
    
    def validate_category_id(self, value):
        """Validate category exists and is active"""
        tenant_id = self.context.get('tenant_id')
        try:
            category = KnowledgeBaseCategory.objects.get(
                id=value,
                tenant_id=tenant_id,
                is_active=True
            )
        except KnowledgeBaseCategory.DoesNotExist:
            raise serializers.ValidationError("Category not found or inactive.")
        
        return value
    
    def validate_tags(self, value):
        """Validate tags format"""
        if value:
            if not isinstance(value, list):
                raise serializers.ValidationError("Tags must be a list.")
            
            for tag in value:
                if not isinstance(tag, str):
                    raise serializers.ValidationError("Each tag must be a string.")
                
                if len(tag.strip()) < 2:
                    raise serializers.ValidationError("Tags must be at least 2 characters long.")
        
        return value or []
    
    def validate(self, data):
        """Cross-field validation"""
        # Auto-generate title from filename if not provided
        if not data.get('title'):
            file = data.get('file')
            if file:
                # Remove extension and clean up filename
                filename = os.path.splitext(file.name)[0]
                data['title'] = filename.replace('_', ' ').replace('-', ' ').title()
        
        # Set default language if not provided
        if not data.get('language'):
            data['language'] = 'en'
        
        return data


class DocumentUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating document metadata"""
    
    class Meta:
        model = KnowledgeBaseDocument
        fields = [
            'title', 'category_id', 'language', 'tags', 'metadata', 'is_active'
        ]
    
    def validate_category_id(self, value):
        """Validate category exists and is active"""
        tenant_id = self.context.get('tenant_id')
        try:
            KnowledgeBaseCategory.objects.get(
                id=value,
                tenant_id=tenant_id,
                is_active=True
            )
        except KnowledgeBaseCategory.DoesNotExist:
            raise serializers.ValidationError("Category not found or inactive.")
        
        return value
    
    def validate_tags(self, value):
        """Validate tags format"""
        if value:
            if not isinstance(value, list):
                raise serializers.ValidationError("Tags must be a list.")
            
            for tag in value:
                if not isinstance(tag, str):
                    raise serializers.ValidationError("Each tag must be a string.")
                
                if len(tag.strip()) < 2:
                    raise serializers.ValidationError("Tags must be at least 2 characters long.")
        
        return value or []


class DocumentChunkSerializer(serializers.ModelSerializer):
    """Serializer for document chunks"""
    has_embeddings = serializers.SerializerMethodField()
    embedding_info = serializers.SerializerMethodField()
    
    class Meta:
        model = DocumentChunk
        fields = [
            'id', 'chunk_index', 'content', 'word_count', 'chunk_metadata',
            'has_embeddings', 'embedding_info', 'created_at'
        ]
    
    def get_has_embeddings(self, obj):
        """Check if chunk has embeddings"""
        return DocumentEmbedding.objects.filter(chunk_id=obj.id).exists()
    
    def get_embedding_info(self, obj):
        """Get embedding information for this chunk"""
        embeddings = DocumentEmbedding.objects.filter(chunk_id=obj.id)
        
        if not embeddings.exists():
            return None
        
        return {
            'count': embeddings.count(),
            'models': list(embeddings.values_list('embedding_model', flat=True).distinct()),
            'latest_created': embeddings.order_by('-created_at').first().created_at
        }


class ProcessingStatusSerializer(serializers.Serializer):
    """Serializer for processing queue status"""
    def to_representation(self, data):
        return data


class EmbeddingStatusSerializer(serializers.Serializer):
    """Serializer for embedding generation status"""
    def to_representation(self, data):
        return data


class DocumentReprocessSerializer(serializers.Serializer):
    """Serializer for document reprocessing requests"""
    force_reprocess = serializers.BooleanField(
        default=False,
        help_text="Force reprocess even if already completed"
    )
    regenerate_embeddings = serializers.BooleanField(
        default=True,
        help_text="Regenerate embeddings after reprocessing"
    )
    chunk_size = serializers.IntegerField(
        required=False,
        min_value=100,
        max_value=2000,
        help_text="Custom chunk size for reprocessing"
    )
    chunk_overlap = serializers.IntegerField(
        required=False,
        min_value=0,
        max_value=500,
        help_text="Custom chunk overlap for reprocessing"
    )