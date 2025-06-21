# knowledge_base/serializers.py
from rest_framework import serializers
from .models import KnowledgeBaseCategory, KnowledgeBaseDocument, DocumentChunk, DocumentEmbedding
from django.core.validators import FileExtensionValidator
import os


class KnowledgeBaseCategorySerializer(serializers.ModelSerializer):
    """Serializer for knowledge base categories"""
    document_count = serializers.SerializerMethodField()
    
    class Meta:
        model = KnowledgeBaseCategory
        fields = [
            'id', 'name', 'description', 'color_code', 'is_active',
            'document_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_document_count(self, obj):
        return obj.documents.filter(is_active=True).count()
    
    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Category name is required.")
        
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Category name must be at least 2 characters long.")
        
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
    
    def validate_color_code(self, value):
        if value:
            import re
            if not re.match(r'^#[0-9A-Fa-f]{6}$', value):
                raise serializers.ValidationError("Color code must be in format #RRGGBB")
        return value or "#007bff"  # Default blue color


class DocumentListSerializer(serializers.ModelSerializer):
    """Serializer for listing documents"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    file_size_mb = serializers.SerializerMethodField()
    chunk_count = serializers.SerializerMethodField()
    embedding_count = serializers.SerializerMethodField()
    
    class Meta:
        model = KnowledgeBaseDocument
        fields = [
            'id', 'title', 'file_type', 'file_size', 'file_size_mb',
            'processing_status', 'is_active', 'category_name',
            'chunk_count', 'embedding_count', 'created_at', 'updated_at'
        ]
    
    def get_file_size_mb(self, obj):
        if obj.file_size:
            return round(obj.file_size / (1024 * 1024), 2)
        return 0
    
    def get_chunk_count(self, obj):
        return obj.chunks.count()
    
    def get_embedding_count(self, obj):
        return DocumentEmbedding.objects.filter(document_id=obj.id).count()


class DocumentDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed document view"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    file_size_mb = serializers.SerializerMethodField()
    chunk_count = serializers.SerializerMethodField()
    embedding_count = serializers.SerializerMethodField()
    processing_info = serializers.SerializerMethodField()
    
    class Meta:
        model = KnowledgeBaseDocument
        fields = [
            'id', 'title', 'content', 'file_type', 'file_size', 'file_size_mb',
            'language', 'tags', 'metadata', 'processing_status', 'is_active',
            'category_name', 'chunk_count', 'embedding_count', 'processing_info',
            'created_at', 'updated_at', 'processed_at'
        ]
    
    def get_file_size_mb(self, obj):
        if obj.file_size:
            return round(obj.file_size / (1024 * 1024), 2)
        return 0
    
    def get_chunk_count(self, obj):
        return obj.chunks.count()
    
    def get_embedding_count(self, obj):
        return DocumentEmbedding.objects.filter(document_id=obj.id).count()
    
    def get_processing_info(self, obj):
        return {
            'status': obj.processing_status,
            'processed_at': obj.processed_at,
            'can_reprocess': obj.processing_status in ['failed', 'completed', 'pending'],
            'error_message': obj.metadata.get('error_message') if obj.metadata else None
        }


class DocumentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/uploading new documents"""
    file = serializers.FileField(
        required=True,
        validators=[FileExtensionValidator(allowed_extensions=['json'])]
    )
    category_id = serializers.UUIDField(required=True)
    
    class Meta:
        model = KnowledgeBaseDocument
        fields = ['title', 'category_id', 'language', 'tags', 'file']
    
    def validate_file(self, value):
        # Check file size (max 10MB for JSON)
        max_size = 10 * 1024 * 1024  # 10MB
        if value.size > max_size:
            raise serializers.ValidationError("File size cannot exceed 10MB.")
        
        if value.size == 0:
            raise serializers.ValidationError("File cannot be empty.")
        
        return value
    
    def validate_category_id(self, value):
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
    
    def validate(self, data):
        # Auto-generate title from filename if not provided
        if not data.get('title'):
            file = data.get('file')
            if file:
                filename = os.path.splitext(file.name)[0]
                data['title'] = filename.replace('_', ' ').replace('-', ' ').title()
        
        # Set default language
        if not data.get('language'):
            data['language'] = 'en'
        
        return data


class DocumentChunkSerializer(serializers.ModelSerializer):
    """Serializer for document chunks"""
    has_embeddings = serializers.SerializerMethodField()
    
    class Meta:
        model = DocumentChunk
        fields = [
            'id', 'chunk_index', 'content', 'word_count', 
            'chunk_metadata', 'has_embeddings', 'created_at'
        ]
    
    def get_has_embeddings(self, obj):
        return DocumentEmbedding.objects.filter(chunk_id=obj.id).exists()


class ProcessingRequestSerializer(serializers.Serializer):
    """Serializer for processing requests"""
    regenerate_chunks = serializers.BooleanField(default=False)
    
    def validate(self, data):
        return data


class EmbeddingRequestSerializer(serializers.Serializer):
    """Serializer for embedding generation requests"""
    regenerate_embeddings = serializers.BooleanField(default=False)
    
    def validate(self, data):
        return data