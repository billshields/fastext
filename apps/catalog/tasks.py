import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def process_catalog_source(self, catalog_source_id):
    from .models import CatalogSource, CatalogChunk
    from .gutenberg import download_gutenberg_text, strip_gutenberg_boilerplate, parse_and_chunk

    try:
        source = CatalogSource.objects.get(pk=catalog_source_id)
    except CatalogSource.DoesNotExist:
        logger.error('CatalogSource %s not found', catalog_source_id)
        return

    source.status = CatalogSource.Status.PROCESSING
    source.save(update_fields=['status'])

    try:
        raw_text = download_gutenberg_text(source.external_id)
        text = strip_gutenberg_boilerplate(raw_text)

        chunks = []
        position = 0
        for word, chapter_idx, para_idx, sentence_end in parse_and_chunk(text):
            chunks.append(CatalogChunk(
                source=source,
                position=position,
                word=word,
                chapter_index=chapter_idx,
                paragraph_index=para_idx,
                sentence_end=sentence_end,
            ))
            position += 1

            if len(chunks) >= 5000:
                CatalogChunk.objects.bulk_create(chunks)
                chunks = []

        if chunks:
            CatalogChunk.objects.bulk_create(chunks)

        now = timezone.now()
        source.status = CatalogSource.Status.COMPLETED
        source.total_words = position
        source.processed_at = now
        source.save(update_fields=['status', 'total_words', 'processed_at'])

        source.documents.update(
            status='completed',
            total_words=position,
            processed_at=now,
        )

    except Exception as exc:
        error_msg = str(exc)[:1000]
        source.status = CatalogSource.Status.FAILED
        source.error_message = error_msg
        source.save(update_fields=['status', 'error_message'])

        source.documents.update(
            status='failed',
            error_message=error_msg,
        )

        raise self.retry(exc=exc, countdown=60)
