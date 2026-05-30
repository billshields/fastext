from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.users.models import User
from apps.documents.models import Document, DocumentChunk
from apps.reading.models import ReadingSession
from .models import DailyReadingLog


def create_authed_client(username='testuser'):
    client = APIClient()
    user = User.objects.create_user(username, f'{username}@example.com', 'testpass123')
    resp = client.post('/api/auth/login/', {
        'username': username,
        'password': 'testpass123',
    })
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')
    return client, user


def create_simple_document(user, title='Test Doc', word_count=100):
    doc = Document.objects.create(
        user=user, title=title, file_type='text',
        status=Document.Status.COMPLETED, total_words=word_count,
    )
    chunks = [
        DocumentChunk(
            document=doc, position=i, word=f'word{i}',
            chapter_index=0, paragraph_index=0, sentence_end=False,
        )
        for i in range(word_count)
    ]
    DocumentChunk.objects.bulk_create(chunks)
    return doc


class StatsOverviewTests(TestCase):
    def setUp(self):
        self.client, self.user = create_authed_client()
        self.doc = create_simple_document(self.user)
        today = timezone.now().date()
        DailyReadingLog.objects.create(
            user=self.user, document=self.doc, date=today,
            reading_time=120, words_read=500, ending_wpm=300, sessions_count=2,
        )

    def test_overview(self):
        resp = self.client.get('/api/stats/overview/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['total_reading_time'], 120)
        self.assertEqual(resp.data['total_words_read'], 500)
        self.assertEqual(resp.data['today_reading_time'], 120)

    def test_overview_empty(self):
        client, _ = create_authed_client('newuser')
        resp = client.get('/api/stats/overview/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['total_reading_time'], 0)
        self.assertEqual(resp.data['total_words_read'], 0)

    def test_overview_streak(self):
        today = timezone.now().date()
        DailyReadingLog.objects.create(
            user=self.user, document=self.doc, date=today - timedelta(days=1),
            reading_time=60, words_read=200, ending_wpm=300, sessions_count=1,
        )
        resp = self.client.get('/api/stats/overview/')
        self.assertEqual(resp.data['current_streak'], 2)

    def test_overview_completed_docs(self):
        session = ReadingSession.objects.create(
            user=self.user, document=self.doc,
            current_position=100, completed_at=timezone.now(),
        )
        resp = self.client.get('/api/stats/overview/')
        self.assertEqual(resp.data['documents_completed'], 1)


class ReadingTimeTests(TestCase):
    def setUp(self):
        self.client, self.user = create_authed_client()
        self.doc = create_simple_document(self.user)
        today = timezone.now().date()
        for i in range(7):
            DailyReadingLog.objects.create(
                user=self.user, document=self.doc, date=today - timedelta(days=i),
                reading_time=60, words_read=200, ending_wpm=300, sessions_count=1,
            )

    def test_reading_time_week(self):
        resp = self.client.get('/api/stats/reading-time/', {'period': 'week'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['period'], 'week')
        self.assertEqual(len(resp.data['data']), 7)

    def test_reading_time_month(self):
        resp = self.client.get('/api/stats/reading-time/', {'period': 'month'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['period'], 'month')


class WpmHistoryTests(TestCase):
    def setUp(self):
        self.client, self.user = create_authed_client()
        self.doc = create_simple_document(self.user)
        today = timezone.now().date()
        DailyReadingLog.objects.create(
            user=self.user, document=self.doc, date=today,
            reading_time=60, words_read=300, ending_wpm=300, sessions_count=1,
        )
        DailyReadingLog.objects.create(
            user=self.user, document=self.doc, date=today - timedelta(days=1),
            reading_time=60, words_read=350, ending_wpm=350, sessions_count=1,
        )

    def test_wpm_history(self):
        resp = self.client.get('/api/stats/wpm-history/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['data']), 2)

    def test_wpm_history_filtered_by_document(self):
        resp = self.client.get('/api/stats/wpm-history/', {'document_id': self.doc.id})
        self.assertEqual(len(resp.data['data']), 2)


class DocumentStatsTests(TestCase):
    def setUp(self):
        self.client, self.user = create_authed_client()
        self.doc = create_simple_document(self.user)
        ReadingSession.objects.create(
            user=self.user, document=self.doc, current_position=50,
        )
        DailyReadingLog.objects.create(
            user=self.user, document=self.doc, date=timezone.now().date(),
            reading_time=120, words_read=50, ending_wpm=300, sessions_count=1,
        )

    def test_document_stats(self):
        resp = self.client.get('/api/stats/documents/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['title'], 'Test Doc')
        self.assertEqual(resp.data[0]['words_read'], 50)
        self.assertEqual(resp.data[0]['reading_time'], 120)
        self.assertAlmostEqual(resp.data[0]['progress'], 0.5, places=2)

    def test_document_stats_unauthenticated(self):
        client = APIClient()
        resp = client.get('/api/stats/documents/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
