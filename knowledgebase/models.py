# knowledge_base/models.py
import uuid
from django.db import models
from django.contrib.postgres.fields import ArrayField
from tenants.models import Tenant, TenantUser
from conversations.models import Conversation, Message


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
    embedding_vector = ArrayField(models.FloatField(), size=None)
    vector_dimension = models.IntegerField()
    similarity_threshold = models.DecimalField(max_digits=5, decimal_places=4, default=0.7500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'document_embeddings'
        unique_together = ['document', 'chunk', 'embedding_model']

    def __str__(self):
        return f"{self.document.title} - {self.chunk.chunk_index} - {self.embedding_model}"


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