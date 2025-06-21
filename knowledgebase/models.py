# knowledge_base/models.py
import uuid
from django.db import models, connection
from django.contrib.postgres.fields import ArrayField
from tenants.models import Tenant, TenantUser
from conversations.models import Conversation, Message
from django.core.exceptions import ValidationError
from pgvector.django import VectorField, L2Distance, CosineDistance
from django.db.models import Value

class KnowledgeBaseCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='knowledge_base_categories')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    color_code = models.CharField(max_length=7)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'knowledge_base_categories'
        unique_together = ['tenant', 'name']
        verbose_name_plural = 'Knowledge Base Categories'

    def __str__(self):
        return f"{self.tenant.business_name} - {self.name}"


class KnowledgeBaseDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='knowledge_base_documents')
    category = models.ForeignKey(KnowledgeBaseCategory, on_delete=models.CASCADE, related_name='documents')
    uploaded_by_user = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='uploaded_documents')
    title = models.CharField(max_length=255)
    content = models.TextField()
    file_path = models.TextField(blank=True)
    file_type = models.CharField(max_length=50, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    language = models.CharField(max_length=10, default='en')
    tags = ArrayField(models.CharField(max_length=50), default=list, blank=True)
    metadata = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    processing_status = models.CharField(max_length=50, default='pending')
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'knowledge_base_documents'

    def __str__(self):
        return f"{self.tenant.business_name} - {self.title}"


class DocumentChunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='document_chunks')
    document = models.ForeignKey(KnowledgeBaseDocument, on_delete=models.CASCADE, related_name='chunks')
    chunk_index = models.IntegerField()
    content = models.TextField()
    content_hash = models.CharField(max_length=64)
    word_count = models.IntegerField()
    chunk_metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'document_chunks'
        unique_together = ['document', 'chunk_index']

    def __str__(self):
        return f"{self.document.title} - Chunk {self.chunk_index}"


from django.db import models
from django.core.exceptions import ValidationError
from pgvector.django import VectorField, L2Distance, CosineDistance
import uuid

class DocumentEmbedding(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='document_embeddings')
    document = models.ForeignKey(KnowledgeBaseDocument, on_delete=models.CASCADE, related_name='embeddings')
    chunk = models.ForeignKey(DocumentChunk, on_delete=models.CASCADE, related_name='embeddings')
    embedding_model = models.CharField(max_length=100)
    
    # Changed from ArrayField to VectorField
    embedding_vector = VectorField(
        dimensions=1536,  # Set to your actual dimension
        null=True,  # Matches your database
        help_text="Vector embeddings for similarity search using pgvector"
    )
    
    vector_dimension = models.IntegerField(
        help_text="Number of dimensions in the embedding vector"
    )
    similarity_threshold = models.DecimalField(
        max_digits=5, 
        decimal_places=4, 
        default=0.7500,
        help_text="Minimum similarity threshold for this embedding"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'document_embeddings'
        unique_together = ['document', 'chunk', 'embedding_model']
        indexes = [
            # Regular indexes for faster lookups
            models.Index(fields=['tenant', 'embedding_model']),
            models.Index(fields=['tenant', 'document']),
            models.Index(fields=['embedding_model', 'vector_dimension']),
            models.Index(fields=['created_at']),
            # pgvector will handle vector similarity indexing
        ]

    def clean(self):
        """Validate the embedding vector"""
        super().clean()
        
        if self.embedding_vector is not None:
            # VectorField handles dimension validation automatically
            # but we can add custom validation if needed
            pass

    def save(self, *args, **kwargs):
        """Override save to auto-set vector_dimension"""
        if self.embedding_vector is not None:
            # For VectorField, we need to check the configured dimension
            self.vector_dimension = 1536  # or len(self.embedding_vector) if it's a list
        
        super().save(*args, **kwargs)

    def cosine_similarity(self, other_vector):
        """
        Calculate cosine similarity with another vector using pgvector
        Returns a value between 0 and 1 (1 = identical, 0 = completely different)
        """
        # Use Django ORM with pgvector
        from django.db.models import Value
        
        result = DocumentEmbedding.objects.filter(
            id=self.id
        ).annotate(
            similarity=1 - CosineDistance('embedding_vector', other_vector)
        ).values('similarity').first()
        
        return result['similarity'] if result else None

    def euclidean_distance(self, other_vector):
        """
        Calculate Euclidean distance with another vector using pgvector
        Lower values indicate higher similarity
        """
        # Use Django ORM with pgvector
        from django.db.models import Value
        
        result = DocumentEmbedding.objects.filter(
            id=self.id
        ).annotate(
            distance=L2Distance('embedding_vector', other_vector)
        ).values('distance').first()
        
        return result['distance'] if result else None

    @classmethod
    def find_similar(cls, query_vector, tenant_id, limit=10, similarity_threshold=0.7, embedding_model=None):
        """
        Find similar embeddings using pgvector similarity search
        
        Args:
            query_vector (list): Vector to search for
            tenant_id: Tenant ID to filter by
            limit (int): Maximum number of results
            similarity_threshold (float): Minimum similarity score (0-1)
            embedding_model (str): Optional model filter
        
        Returns:
            QuerySet of DocumentEmbedding objects with similarity scores
        """
        # Build the query
        queryset = cls.objects.filter(
            tenant_id=tenant_id,
            embedding_vector__isnull=False
        )
        
        if embedding_model:
            queryset = queryset.filter(embedding_model=embedding_model)
        
        # Annotate with similarity score using cosine similarity
        queryset = queryset.annotate(
            similarity_score=1 - CosineDistance('embedding_vector', query_vector)
        ).filter(
            similarity_score__gte=similarity_threshold
        ).order_by(
            '-similarity_score'
        )[:limit]
        
        return queryset
    
    @classmethod
    def find_similar_l2(cls, query_vector, tenant_id, limit=10, max_distance=1.0, embedding_model=None):
        """
        Find similar embeddings using L2 distance (Euclidean)
        
        Args:
            query_vector (list): Vector to search for
            tenant_id: Tenant ID to filter by
            limit (int): Maximum number of results
            max_distance (float): Maximum L2 distance
            embedding_model (str): Optional model filter
        
        Returns:
            QuerySet of DocumentEmbedding objects with distances
        """
        queryset = cls.objects.filter(
            tenant_id=tenant_id,
            embedding_vector__isnull=False
        )
        
        if embedding_model:
            queryset = queryset.filter(embedding_model=embedding_model)
        
        # Annotate with L2 distance
        queryset = queryset.annotate(
            distance=L2Distance('embedding_vector', query_vector)
        ).filter(
            distance__lte=max_distance
        ).order_by(
            'distance'
        )[:limit]
        
        return queryset

    @classmethod
    def find_top_k(
        cls,
        query_vector,
        tenant_id,
        *,
        top_k = 5,
        similarity_threshold = 0.1,   # ⇠ tune for your data
        embedding_model= None,
    ):
        """
        Return the K most-similar rows (cosine distance-based).

        Result objects come back annotated with `.similarity_score`
        so you can inspect or log them.
        """
        # Cast the Python list to a pgvector on the DB side
        query_expr = Value(
            query_vector,
            output_field=VectorField(dimensions=1536)
        )
        print()
        qs = cls.objects.filter(
            tenant_id=tenant_id,
            embedding_vector__isnull=False,
        )
        
        if embedding_model:
            qs = qs.filter(embedding_model=embedding_model)
        print(qs, "wqewqewq")
        return (
            qs.annotate(
                similarity_score=1 - CosineDistance("embedding_vector", query_expr)
            )
            .filter(similarity_score__gte=similarity_threshold)
            .order_by("-similarity_score")[:top_k]
        )


class KnowledgeRetrievalLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='knowledge_retrieval_logs')
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='knowledge_retrieval_logs')
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='knowledge_retrieval_logs')
    query_text = models.TextField()
    query_embedding = ArrayField(models.FloatField(), size=None)
    retrieved_chunks = models.JSONField(default=list)
    similarity_scores = models.JSONField(default=list)
    chunks_used_count = models.IntegerField()
    retrieval_time_ms = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'knowledge_retrieval_logs'

    def __str__(self):
        return f"{self.tenant.business_name} - {self.conversation.id} - {self.chunks_used_count} chunks"