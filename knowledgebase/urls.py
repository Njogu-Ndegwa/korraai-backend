# urls.py
from django.urls import path
from . import views

app_name = 'knowledge_base_categories'

urlpatterns = [
    # Knowledge base category management
    path('knowledge-base/categories/', views.kb_category_list_create, name='kb-category-list-create'),
    path('knowledge-base/categories/<uuid:category_id>/', views.kb_category_detail, name='kb-category-detail'),
    path('knowledge-base/documents/', views.document_list_create, name='document-list-create'),
    path('knowledge-base/documents/<uuid:document_id>/', views.document_detail, name='document-detail'),
    path('knowledge-base/documents/<uuid:document_id>/reprocess/', views.document_reprocess, name='document-reprocess'),
    path('knowledge-base/documents/<uuid:document_id>/chunks/', views.document_chunks, name='document-chunks'),
    path('knowledge-base/processing-status/', views.processing_status, name='processing-status'),
    path('knowledge-base/embeddings/status/', views.embedding_status, name='embedding-status'),
]