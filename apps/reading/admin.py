from django.contrib import admin

from .models import ReadingSession


@admin.register(ReadingSession)
class ReadingSessionAdmin(admin.ModelAdmin):
    list_display = ['user', 'document', 'current_position', 'wpm', 'last_read_at']
