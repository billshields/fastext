from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import CatalogSource
from apps.catalog.tasks import process_catalog_source
from apps.catalog.views import requeue_failed_source
from apps.documents.extractors import SENTENCE_END_RE
from apps.documents.models import Document, DocumentChunk
from apps.users.models import User

# Dev-only credentials for the shared browser-testing account
USERNAME = 'browsertest'
PASSWORD = 'browsertest-pass-123'
EMAIL = 'browsertest@example.com'

# Its title is an XSS probe: if escapeHtml() is ever skipped, the image fails to
# load and bumps window.__xss instead of opening an alert that blocks automation
XSS_TITLE = '<img src=x onerror="window.__xss=(window.__xss||0)+1">Evil Title'
XSS_TEXT = 'This document tests that titles are escaped. It is short on purpose. The end.'

# Long, with chapters, for testing the scrubber, chapter navigation and prefetch
BOOK_ID = '1342'
BOOK_TITLE = 'Pride and Prejudice'
BOOK_AUTHOR = 'Austen, Jane'


class Command(BaseCommand):
    help = 'Create or repair the browsertest account and its fixture documents (dev only).'

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('seed_browsertest only runs with DEBUG on.')

        user, created = User.objects.get_or_create(username=USERNAME, defaults={'email': EMAIL})
        # Reset every run, so the credentials above always work
        user.set_password(PASSWORD)
        user.save()
        self.stdout.write(f'{"Created" if created else "Found"} user {USERNAME}')

        if not Document.objects.filter(user=user, title=XSS_TITLE).exists():
            self.create_text_document(user, XSS_TITLE, XSS_TEXT)
            self.stdout.write('Created the XSS probe document')

        if not Document.objects.filter(
            user=user, catalog_source__platform='gutenberg', catalog_source__external_id=BOOK_ID,
        ).exists():
            self.add_catalog_book(user)

        self.stdout.write(self.style.SUCCESS('browsertest is ready'))

    def create_text_document(self, user, title, text):
        words = text.split()
        with transaction.atomic():
            doc = Document.objects.create(
                user=user,
                title=title,
                file_type='text',
                file_size=len(text.encode('utf-8')),
                status=Document.Status.COMPLETED,
                total_words=len(words),
                processed_at=timezone.now(),
            )
            DocumentChunk.objects.bulk_create(
                DocumentChunk(document=doc, position=i, word=word, sentence_end=bool(SENTENCE_END_RE.search(word)))
                for i, word in enumerate(words)
            )

    def add_catalog_book(self, user):
        source, created = CatalogSource.objects.get_or_create(
            platform='gutenberg',
            external_id=BOOK_ID,
            defaults={
                'title': BOOK_TITLE,
                'author': BOOK_AUTHOR,
                'source_url': f'https://www.gutenberg.org/cache/epub/{BOOK_ID}/pg{BOOK_ID}.txt',
            },
        )
        if created:
            process_catalog_source.delay(source.id)
        elif source.status == CatalogSource.Status.FAILED:
            requeue_failed_source(source)

        ready = source.status == CatalogSource.Status.COMPLETED
        Document.objects.create(
            user=user,
            title=source.title,
            file_type='gutenberg',
            status=Document.Status.COMPLETED if ready else Document.Status.PROCESSING,
            total_words=source.total_words,
            processed_at=source.processed_at,
            catalog_source=source,
        )
        self.stdout.write(f'Added {BOOK_TITLE}' + ('' if ready else ' (downloading; needs the Celery worker)'))
