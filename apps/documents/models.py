from django.db import models
from django.conf import settings


class Document(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending'
        PROCESSING = 'processing'
        COMPLETED = 'completed'
        FAILED = 'failed'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=500)
    original_filename = models.CharField(max_length=500)
    file = models.FileField(upload_to='uploads/%Y/%m/')
    file_type = models.CharField(max_length=10)
    file_size = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total_words = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default='')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'documents'
        indexes = [
            models.Index(fields=['user', '-uploaded_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return self.title


class DocumentChunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='chunks')
    position = models.PositiveIntegerField()
    word = models.CharField(max_length=200)
    chapter_index = models.PositiveSmallIntegerField(default=0)
    paragraph_index = models.PositiveIntegerField(default=0)
    sentence_end = models.BooleanField(default=False)

    class Meta:
        db_table = 'document_chunks'
        indexes = [
            models.Index(fields=['document', 'position']),
        ]
        ordering = ['position']
        constraints = [
            models.UniqueConstraint(fields=['document', 'position'], name='unique_doc_position'),
        ]

    def __str__(self):
        return f"{self.document_id}:{self.position} {self.word}"
