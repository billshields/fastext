from django.db import models
from django.conf import settings


class ReadingSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reading_sessions')
    document = models.ForeignKey('documents.Document', on_delete=models.CASCADE, related_name='sessions')
    current_position = models.PositiveIntegerField(default=0)
    wpm = models.PositiveIntegerField(default=300)
    chunk_size = models.PositiveSmallIntegerField(default=1)
    total_reading_time = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    last_read_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'reading_sessions'
        indexes = [
            models.Index(fields=['user', 'document']),
            models.Index(fields=['user', '-last_read_at']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['user', 'document'], name='one_session_per_doc'),
        ]

    def __str__(self):
        return f"{self.user.username} reading {self.document.title} @ {self.current_position}"
