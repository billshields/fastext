from django.db import models


class CatalogSource(models.Model):
    class Platform(models.TextChoices):
        GUTENBERG = 'gutenberg'

    class Status(models.TextChoices):
        PENDING = 'pending'
        PROCESSING = 'processing'
        COMPLETED = 'completed'
        FAILED = 'failed'

    platform = models.CharField(max_length=20, choices=Platform.choices)
    external_id = models.CharField(max_length=100)
    title = models.CharField(max_length=500)
    author = models.CharField(max_length=500, blank=True, default='')
    language = models.CharField(max_length=10, default='en')
    subjects = models.JSONField(default=list, blank=True)
    cover_url = models.URLField(max_length=500, blank=True, default='')
    source_url = models.URLField(max_length=500, blank=True, default='')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total_words = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'catalog_sources'
        constraints = [
            models.UniqueConstraint(
                fields=['platform', 'external_id'],
                name='unique_platform_ext_id',
            ),
        ]
        indexes = [
            models.Index(fields=['platform', 'external_id']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.title} ({self.platform}:{self.external_id})'


class CatalogChunk(models.Model):
    source = models.ForeignKey(CatalogSource, on_delete=models.CASCADE, related_name='chunks')
    position = models.PositiveIntegerField()
    word = models.CharField(max_length=200)
    chapter_index = models.PositiveSmallIntegerField(default=0)
    paragraph_index = models.PositiveIntegerField(default=0)
    sentence_end = models.BooleanField(default=False)

    class Meta:
        db_table = 'catalog_chunks'
        ordering = ['position']
        indexes = [
            models.Index(fields=['source', 'position']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'position'],
                name='unique_catalog_position',
            ),
        ]
