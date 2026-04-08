from django.urls import path

from . import views

urlpatterns = [
    path('documents/', views.DocumentListView.as_view(), name='document-list'),
    path('documents/upload/', views.DocumentUploadView.as_view(), name='document-upload'),
    path('documents/<int:pk>/', views.DocumentDetailView.as_view(), name='document-detail'),
    path('documents/<int:pk>/status/', views.DocumentStatusView.as_view(), name='document-status'),
    path('documents/<int:pk>/text/', views.DocumentTextView.as_view(), name='document-text'),
]
