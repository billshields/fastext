from django.contrib import admin

from .models import CatalogSource


@admin.register(CatalogSource)
class CatalogSourceAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'platform', 'external_id', 'status', 'total_words')
    list_filter = ('platform', 'status')
    search_fields = ('title', 'author', 'external_id')
    readonly_fields = ('created_at', 'processed_at')
