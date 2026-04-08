from django.urls import path

from . import views

urlpatterns = [
    path('documents/<int:doc_id>/read/', views.ReadView.as_view(), name='read'),
    path('documents/<int:doc_id>/words/', views.WordsView.as_view(), name='words'),
    path('documents/<int:doc_id>/progress/', views.ProgressView.as_view(), name='progress'),
    path('documents/<int:doc_id>/session/', views.SessionUpdateView.as_view(), name='session-update'),
]
