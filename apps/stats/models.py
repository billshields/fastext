from django.db import models
from django.conf import settings


class DailyReadingLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='daily_logs')
    document = models.ForeignKey('documents.Document', on_delete=models.CASCADE, related_name='daily_logs')
    date = models.DateField()
    reading_time = models.PositiveIntegerField(default=0)
    words_read = models.PositiveIntegerField(default=0)
    ending_wpm = models.PositiveIntegerField(default=0)
    sessions_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'daily_reading_logs'
        constraints = [
            models.UniqueConstraint(fields=['user', 'document', 'date'], name='one_log_per_doc_per_day'),
        ]
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['user', 'document', 'date']),
        ]

    def __str__(self):
        return f"{self.user_id} {self.document_id} {self.date}"
