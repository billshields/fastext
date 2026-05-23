from django.contrib import admin
from .models import DailyReadingLog


@admin.register(DailyReadingLog)
class DailyReadingLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'document', 'date', 'reading_time', 'words_read', 'ending_wpm')
    list_filter = ('date',)
    raw_id_fields = ('user', 'document')
