# urls.py
from django.urls import path
from . import views

app_name = 'lead_stages'

urlpatterns = [
    # Lead stages management endpoints
    path('lead-stages/', views.lead_stage_list_create, name='lead-stage-list-create'),
    path('lead-stages/<uuid:stage_id>/', views.lead_stage_detail, name='lead-stage-detail'),
    path('lead-categories/', views.lead_category_list_create, name='lead-category-list-create'),
    path('lead-categories/<uuid:category_id>/', views.lead_category_detail, name='lead-category-detail'),
    path('leads/', views.lead_list_create, name='lead-list-create'),
    path('leads/<uuid:lead_id>/', views.lead_detail, name='lead-detail'),
    path('leads/<uuid:lead_id>/stage/', views.lead_stage_update, name='lead-stage-update'),
]