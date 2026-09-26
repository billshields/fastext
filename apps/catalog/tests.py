from unittest import mock

import requests
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from apps.users.models import User
from apps.documents.models import Document
from .models import CatalogChunk, CatalogSource
from .tasks import process_catalog_source


SAMPLE_BOOK = """The Project Gutenberg eBook of Test Book

*** START OF THE PROJECT GUTENBERG EBOOK TEST BOOK ***

CHAPTER I

It was a dark night. The end came.

CHAPTER II

Morning arrived at last.

*** END OF THE PROJECT GUTENBERG EBOOK TEST BOOK ***
License text that should be stripped.
"""


def create_authed_client(username='testuser'):
    client = APIClient()
    user = User.objects.create_user(username, f'{username}@example.com', 'testpass123')
    resp = client.post('/api/auth/login/', {
        'username': username,
        'password': 'testpass123',
    })
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')
    return client, user


def create_source(**kwargs):
    defaults = {'platform': 'gutenberg', 'external_id': '1342', 'title': 'Pride and Prejudice'}
    defaults.update(kwargs)
    return CatalogSource.objects.create(**defaults)


@mock.patch('apps.catalog.views.process_catalog_source.delay')
class CatalogImportTests(TestCase):
    def setUp(self):
        self.client, self.user = create_authed_client()
        self.payload = {
            'platform': 'gutenberg',
            'external_id': '1342',
            'title': 'Pride and Prejudice',
            'author': 'Jane Austen',
        }

    def test_import_new_book_queues_processing(self, delay):
        resp = self.client.post('/api/catalog/import/', self.payload)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(resp.data['status'], 'processing')
        source = CatalogSource.objects.get(external_id='1342')
        delay.assert_called_once_with(source.id)

    def test_import_completed_book_is_ready_immediately(self, delay):
        create_source(status=CatalogSource.Status.COMPLETED, total_words=100)
        resp = self.client.post('/api/catalog/import/', self.payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['status'], 'completed')
        self.assertEqual(resp.data['total_words'], 100)
        delay.assert_not_called()

    def test_import_failed_book_requeues_it(self, delay):
        source = create_source(status=CatalogSource.Status.FAILED, error_message='timed out')
        resp = self.client.post('/api/catalog/import/', self.payload)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(resp.data['status'], 'processing')
        delay.assert_called_once_with(source.id)
        source.refresh_from_db()
        self.assertEqual(source.status, CatalogSource.Status.PENDING)
        self.assertEqual(source.error_message, '')

    def test_import_failed_book_resets_other_users_copies(self, delay):
        source = create_source(status=CatalogSource.Status.FAILED)
        other = User.objects.create_user('other', 'other@example.com', 'testpass123')
        other_doc = Document.objects.create(
            user=other, title='Pride and Prejudice', file_type='gutenberg',
            status=Document.Status.FAILED, error_message='timed out', catalog_source=source,
        )
        self.client.post('/api/catalog/import/', self.payload)
        other_doc.refresh_from_db()
        self.assertEqual(other_doc.status, Document.Status.PROCESSING)
        self.assertEqual(other_doc.error_message, '')

    def test_reimport_own_failed_book_retries_it(self, delay):
        self.client.post('/api/catalog/import/', self.payload)
        source = CatalogSource.objects.get(external_id='1342')
        source.status = CatalogSource.Status.FAILED
        source.save()
        source.documents.update(status=Document.Status.FAILED, error_message='timed out')
        delay.reset_mock()

        resp = self.client.post('/api/catalog/import/', self.payload)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(resp.data['status'], 'processing')
        delay.assert_called_once_with(source.id)
        doc = Document.objects.get(user=self.user)
        self.assertEqual(doc.id, resp.data['id'])
        self.assertEqual(doc.error_message, '')

    def test_import_book_already_processing_does_not_requeue(self, delay):
        create_source(status=CatalogSource.Status.PROCESSING)
        resp = self.client.post('/api/catalog/import/', self.payload)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        delay.assert_not_called()

    def test_import_duplicate_for_same_user(self, delay):
        self.client.post('/api/catalog/import/', self.payload)
        resp = self.client.post('/api/catalog/import/', self.payload)
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)


class CatalogSearchTests(TestCase):
    def setUp(self):
        self.client, self.user = create_authed_client()

    @mock.patch('apps.catalog.views.search_gutenberg')
    def test_search_invalid_page(self, search):
        resp = self.client.get('/api/catalog/search/?page=abc')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        search.assert_not_called()


class ProcessCatalogSourceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('reader', 'reader@example.com', 'testpass123')
        self.source = create_source(external_id='1')
        self.doc = Document.objects.create(
            user=self.user, title='Test Book', file_type='gutenberg',
            status=Document.Status.PROCESSING, catalog_source=self.source,
        )

    @mock.patch('apps.catalog.gutenberg.download_gutenberg_text', return_value=SAMPLE_BOOK)
    def test_processes_book_into_chunks(self, _download):
        process_catalog_source.apply(args=[self.source.id])

        self.source.refresh_from_db()
        self.doc.refresh_from_db()
        words = list(CatalogChunk.objects.filter(source=self.source).values_list('word', flat=True))
        self.assertEqual(self.source.status, CatalogSource.Status.COMPLETED)
        self.assertEqual(words[:3], ['CHAPTER', 'I', 'It'])
        self.assertNotIn('License', words)
        self.assertEqual(self.source.total_words, len(words))
        self.assertEqual(self.doc.status, Document.Status.COMPLETED)
        self.assertEqual(self.doc.total_words, len(words))

    @mock.patch('apps.catalog.gutenberg.download_gutenberg_text', return_value=SAMPLE_BOOK)
    def test_rerun_replaces_existing_chunks(self, _download):
        process_catalog_source.apply(args=[self.source.id])
        first_count = CatalogChunk.objects.filter(source=self.source).count()

        result = process_catalog_source.apply(args=[self.source.id])

        self.assertTrue(result.successful())
        self.assertEqual(CatalogChunk.objects.filter(source=self.source).count(), first_count)

    @mock.patch('apps.catalog.gutenberg.download_gutenberg_text',
                side_effect=requests.ConnectionError('gutenberg is down'))
    def test_marks_failed_only_after_retries_run_out(self, download):
        result = process_catalog_source.apply(args=[self.source.id])

        self.assertTrue(result.failed())
        self.assertEqual(download.call_count, process_catalog_source.max_retries + 1)
        self.source.refresh_from_db()
        self.doc.refresh_from_db()
        self.assertEqual(self.source.status, CatalogSource.Status.FAILED)
        self.assertIn('gutenberg is down', self.source.error_message)
        self.assertEqual(self.doc.status, Document.Status.FAILED)
