from celery import shared_task
from django.db import transaction
from django.utils import timezone


@shared_task(bind=True, max_retries=2)
def process_document(self, document_id):
    from .models import Document, DocumentChunk
    from .extractors import extract_pdf, extract_epub

    doc = Document.objects.get(id=document_id)
    doc.status = Document.Status.PROCESSING
    doc.save(update_fields=['status'])

    try:
        extractor = extract_pdf if doc.file_type == 'pdf' else extract_epub
        chunks = []
        position = 0

        for chapter_idx, para_idx, word, sentence_end in extractor(doc.file.path):
            chunks.append(DocumentChunk(
                document=doc,
                position=position,
                word=word,
                chapter_index=chapter_idx,
                paragraph_index=para_idx,
                sentence_end=sentence_end,
            ))
            position += 1

        with transaction.atomic():
            DocumentChunk.objects.filter(document=doc).delete()

            for i in range(0, len(chunks), 5000):
                DocumentChunk.objects.bulk_create(chunks[i:i + 5000])

            doc.total_words = position
            doc.status = Document.Status.COMPLETED
            doc.processed_at = timezone.now()
            doc.save(update_fields=['total_words', 'status', 'processed_at'])

    except Exception as exc:
        doc.status = Document.Status.FAILED
        doc.error_message = str(exc)[:1000]
        doc.save(update_fields=['status', 'error_message'])
        raise self.retry(exc=exc, countdown=30)
