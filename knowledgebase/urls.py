# knowledge_base/urls.py
from django.urls import path
from . import views

app_name = 'knowledge_base'

urlpatterns = [
    # Knowledge base category management
    path('knowledge-base/categories/', views.kb_category_list_create, name='kb-category-list-create'),
    path('knowledge-base/categories/<uuid:category_id>/', views.kb_category_detail, name='kb-category-detail'),
    
    # Document management
    path('knowledge-base/documents/', views.document_list_create, name='document-list-create'),
    path('knowledge-base/documents/<uuid:document_id>/', views.document_detail, name='document-detail'),
    
    # Document processing
    path('knowledge-base/documents/<uuid:document_id>/process/', views.process_document_chunks, name='process-document'),
    path('knowledge-base/documents/<uuid:document_id>/embeddings/', views.generate_embeddings, name='generate-embeddings'),
    path('knowledge-base/documents/<uuid:document_id>/chunks/', views.document_chunks, name='document-chunks'),
    
    # Status monitoring
    path('knowledge-base/processing-status/', views.processing_status, name='processing-status'),
]