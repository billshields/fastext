from django.urls import path

from . import views

urlpatterns = [
    path('catalog/search/', views.CatalogSearchView.as_view(), name='catalog-search'),
    path('catalog/import/', views.CatalogImportView.as_view(), name='catalog-import'),
]
