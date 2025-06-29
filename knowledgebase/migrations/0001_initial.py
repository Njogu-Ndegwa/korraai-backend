# Generated by Django 5.2.3 on 2025-06-20 10:37

import django.contrib.postgres.fields
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('conversations', '0001_initial'),
        ('tenants', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='KnowledgeBaseCategory',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True)),
                ('color_code', models.CharField(max_length=7)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='knowledge_base_categories', to='tenants.tenant')),
            ],
            options={
                'verbose_name_plural': 'Knowledge Base Categories',
                'db_table': 'knowledge_base_categories',
                'unique_together': {('tenant', 'name')},
            },
        ),
        migrations.CreateModel(
            name='KnowledgeBaseDocument',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=255)),
                ('content', models.TextField()),
                ('file_path', models.TextField(blank=True)),
                ('file_type', models.CharField(blank=True, max_length=50)),
                ('file_size', models.BigIntegerField(blank=True, null=True)),
                ('language', models.CharField(default='en', max_length=10)),
                ('tags', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=50), blank=True, default=list, size=None)),
                ('metadata', models.JSONField(default=dict)),
                ('is_active', models.BooleanField(default=True)),
                ('processing_status', models.CharField(default='pending', max_length=50)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='knowledgebase.knowledgebasecategory')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='knowledge_base_documents', to='tenants.tenant')),
                ('uploaded_by_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='uploaded_documents', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'knowledge_base_documents',
            },
        ),
        migrations.CreateModel(
            name='DocumentChunk',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('chunk_index', models.IntegerField()),
                ('content', models.TextField()),
                ('content_hash', models.CharField(max_length=64)),
                ('word_count', models.IntegerField()),
                ('chunk_metadata', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='document_chunks', to='tenants.tenant')),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chunks', to='knowledgebase.knowledgebasedocument')),
            ],
            options={
                'db_table': 'document_chunks',
                'unique_together': {('document', 'chunk_index')},
            },
        ),
        migrations.CreateModel(
            name='KnowledgeRetrievalLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('query_text', models.TextField()),
                ('query_embedding', django.contrib.postgres.fields.ArrayField(base_field=models.FloatField(), size=None)),
                ('retrieved_chunks', models.JSONField(default=list)),
                ('similarity_scores', models.JSONField(default=list)),
                ('chunks_used_count', models.IntegerField()),
                ('retrieval_time_ms', models.IntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='knowledge_retrieval_logs', to='conversations.conversation')),
                ('message', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='knowledge_retrieval_logs', to='conversations.message')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='knowledge_retrieval_logs', to='tenants.tenant')),
            ],
            options={
                'db_table': 'knowledge_retrieval_logs',
            },
        ),
        migrations.CreateModel(
            name='DocumentEmbedding',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('embedding_model', models.CharField(max_length=100)),
                ('embedding_vector', django.contrib.postgres.fields.ArrayField(base_field=models.FloatField(), help_text='Vector embeddings for similarity search using pgvector', size=None)),
                ('vector_dimension', models.IntegerField(help_text='Number of dimensions in the embedding vector')),
                ('similarity_threshold', models.DecimalField(decimal_places=4, default=0.75, help_text='Minimum similarity threshold for this embedding', max_digits=5)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('chunk', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='embeddings', to='knowledgebase.documentchunk')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='document_embeddings', to='tenants.tenant')),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='embeddings', to='knowledgebase.knowledgebasedocument')),
            ],
            options={
                'db_table': 'document_embeddings',
                'indexes': [models.Index(fields=['tenant', 'embedding_model'], name='document_em_tenant__cbbcad_idx'), models.Index(fields=['tenant', 'document'], name='document_em_tenant__af7f5f_idx'), models.Index(fields=['embedding_model', 'vector_dimension'], name='document_em_embeddi_73d7ca_idx'), models.Index(fields=['created_at'], name='document_em_created_702258_idx')],
                'unique_together': {('document', 'chunk', 'embedding_model')},
            },
        ),
    ]
