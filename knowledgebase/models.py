# knowledge_base/models.py
import uuid
from django.db import models, connection
from django.contrib.postgres.fields import ArrayField
from tenants.models import Tenant, TenantUser
from conversations.models import Conversation, Message
from django.core.exceptions import ValidationError



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


class DocumentEmbedding(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='document_embeddings')
    document = models.ForeignKey(KnowledgeBaseDocument, on_delete=models.CASCADE, related_name='embeddings')
    chunk = models.ForeignKey(DocumentChunk, on_delete=models.CASCADE, related_name='embeddings')
    embedding_model = models.CharField(max_length=100)
    
    # Optimized vector field for pgvector
    embedding_vector = ArrayField(
        models.FloatField(),
        size=None,  # Dynamic size based on embedding model
        help_text="Vector embeddings for similarity search using pgvector",
        db_index=False  # We'll create custom vector index
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
            # Note: Vector similarity index will be created in migration
        ]

    def clean(self):
        """Validate the embedding vector"""
        super().clean()
        
        if self.embedding_vector:
            # Validate vector dimension matches actual vector length
            if len(self.embedding_vector) != self.vector_dimension:
                raise ValidationError(
                    f"Vector dimension mismatch: expected {self.vector_dimension}, "
                    f"got {len(self.embedding_vector)}"
                )
            
            # Validate vector contains only finite numbers
            if not all(isinstance(x, (int, float)) and not (x != x or x == float('inf') or x == float('-inf')) 
                      for x in self.embedding_vector):
                raise ValidationError("Vector contains invalid values (NaN or infinity)")

    def save(self, *args, **kwargs):
        """Override save to auto-set vector_dimension and validate"""
        if self.embedding_vector:
            self.vector_dimension = len(self.embedding_vector)
        
        self.full_clean()  # Run validation
        super().save(*args, **kwargs)

    def cosine_similarity(self, other_vector):
        """
        Calculate cosine similarity with another vector using pgvector
        Returns a value between 0 and 1 (1 = identical, 0 = completely different)
        """
        if not isinstance(other_vector, list):
            raise ValueError("other_vector must be a list of floats")
        
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 - (%s::vector <=> %s::vector) as similarity",
                [self.embedding_vector, other_vector]
            )
            return cursor.fetchone()[0]

    def euclidean_distance(self, other_vector):
        """
        Calculate Euclidean distance with another vector using pgvector
        Lower values indicate higher similarity
        """
        if not isinstance(other_vector, list):
            raise ValueError("other_vector must be a list of floats")
        
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT %s::vector <-> %s::vector as distance",
                [self.embedding_vector, other_vector]
            )
            return cursor.fetchone()[0]

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
        from django.db import connection
        
        sql = """
            SELECT 
                de.*,
                1 - (de.embedding_vector <=> %s::vector) as similarity_score
            FROM document_embeddings de
            WHERE de.tenant_id = %s
            AND (1 - (de.embedding_vector <=> %s::vector)) >= %s
        """
        
        params = [query_vector, tenant_id, query_vector, similarity_threshold]
        
        if embedding_model:
            sql += " AND de.embedding_model = %s"
            params.append(embedding_model)
        
        sql += """
            ORDER BY de.embedding_vector <=> %s::vector
            LIMIT %s
        """
        params.extend([query_vector, limit])
        
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            
            # Convert results to model instances with similarity scores
            results = []
            for row in cursor.fetchall():
                # Create model instance from row data
                embedding = cls(
                    id=row[0],
                    tenant_id=row[1],
                    document_id=row[2],
                    chunk_id=row[3],
                    embedding_model=row[4],
                    embedding_vector=row[5],
                    vector_dimension=row[6],
                    similarity_threshold=row[7],
                    created_at=row[8],
                    updated_at=row[9]
                )
                # Add similarity score as attribute
                embedding.similarity_score = row[10]
                results.append(embedding)
            
            return results

    @classmethod
    def bulk_create_embeddings(cls, embeddings_data, batch_size=100):
        """
        Efficiently create multiple embeddings
        
        Args:
            embeddings_data (list): List of dicts with embedding data
            batch_size (int): Batch size for bulk operations
        """
        embeddings = []
        for data in embeddings_data:
            embedding = cls(
                tenant_id=data['tenant_id'],
                document_id=data['document_id'],
                chunk_id=data['chunk_id'],
                embedding_model=data['embedding_model'],
                embedding_vector=data['embedding_vector'],
                vector_dimension=len(data['embedding_vector'])
            )
            embeddings.append(embedding)
        
        return cls.objects.bulk_create(embeddings, batch_size=batch_size)

    def __str__(self):
        return f"{self.document.title} - {self.chunk.chunk_index} - {self.embedding_model} ({self.vector_dimension}D)"

    def __repr__(self):
        return (f"DocumentEmbedding(id={self.id}, document_id={self.document_id}, "
                f"chunk_id={self.chunk_id}, model={self.embedding_model}, "
                f"dimensions={self.vector_dimension})")


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