from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.users.urls')),
    path('api/', include('apps.documents.urls')),
    path('api/', include('apps.reading.urls')),
    # Web views
    path('', TemplateView.as_view(template_name='index.html'), name='index'),
    path('library/', TemplateView.as_view(template_name='library.html'), name='library'),
    path('read/<int:doc_id>/', TemplateView.as_view(template_name='reader.html'), name='reader'),
    path('edit/<int:doc_id>/', TemplateView.as_view(template_name='editor.html'), name='editor'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
