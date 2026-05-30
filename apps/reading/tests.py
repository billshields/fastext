from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from apps.users.models import User
from apps.documents.models import Document, DocumentChunk
from .models import ReadingSession


def create_authed_client(username='testuser'):
    client = APIClient()
    user = User.objects.create_user(username, f'{username}@example.com', 'testpass123')
    resp = client.post('/api/auth/login/', {
        'username': username,
        'password': 'testpass123',
    })
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')
    return client, user


def create_document_with_chapters(user, title='Test Doc'):
    words = []
    # Chapter 0: 10 words, Chapter 1: 10 words
    for ch in range(2):
        for i in range(10):
            w = f'ch{ch}word{i}'
            if i == 9:
                w += '.'
            words.append((w, ch))

    doc = Document.objects.create(
        user=user, title=title, file_type='text',
        status=Document.Status.COMPLETED, total_words=len(words),
    )
    chunks = []
    for i, (word, chapter) in enumerate(words):
        chunks.append(DocumentChunk(
            document=doc, position=i, word=word,
            chapter_index=chapter, paragraph_index=0,
            sentence_end=word.endswith('.'),
        ))
    DocumentChunk.objects.bulk_create(chunks)
    return doc


def create_simple_document(user, title='Test Doc', word_count=20):
    words = [f'word{i}' for i in range(word_count)]
    words[-1] += '.'
    doc = Document.objects.create(
        user=user, title=title, file_type='text',
        status=Document.Status.COMPLETED, total_words=len(words),
    )
    chunks = [
        DocumentChunk(
            document=doc, position=i, word=w,
            chapter_index=0, paragraph_index=0,
            sentence_end=w.endswith('.'),
        )
        for i, w in enumerate(words)
    ]
    DocumentChunk.objects.bulk_create(chunks)
    return doc


class ReadViewTests(TestCase):
    def setUp(self):
        self.client, self.user = create_authed_client()
        self.doc = create_simple_document(self.user)

    def test_read_creates_session(self):
        resp = self.client.get(f'/api/documents/{self.doc.id}/read/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('session', resp.data)
        self.assertIn('words', resp.data)
        self.assertEqual(resp.data['session']['current_position'], 0)
        self.assertTrue(ReadingSession.objects.filter(user=self.user, document=self.doc).exists())

    def test_read_returns_existing_session(self):
        self.client.get(f'/api/documents/{self.doc.id}/read/')
        session = ReadingSession.objects.get(user=self.user, document=self.doc)
        session.current_position = 10
        session.save()
        resp = self.client.get(f'/api/documents/{self.doc.id}/read/')
        self.assertEqual(resp.data['session']['current_position'], 10)

    def test_read_inherits_user_preferences(self):
        self.user.preferences.default_wpm = 500
        self.user.preferences.chunk_size = 3
        self.user.preferences.save()
        resp = self.client.get(f'/api/documents/{self.doc.id}/read/')
        self.assertEqual(resp.data['session']['wpm'], 500)
        self.assertEqual(resp.data['session']['chunk_size'], 3)

    def test_read_not_found(self):
        resp = self.client.get('/api/documents/99999/read/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_read_pending_document(self):
        doc = Document.objects.create(
            user=self.user, title='Pending', file_type='pdf', status=Document.Status.PENDING,
        )
        resp = self.client.get(f'/api/documents/{doc.id}/read/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_read_other_users_document(self):
        _, other_user = create_authed_client('otheruser')
        other_doc = create_simple_document(other_user, 'Other Doc')
        resp = self.client.get(f'/api/documents/{other_doc.id}/read/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class WordsViewTests(TestCase):
    def setUp(self):
        self.client, self.user = create_authed_client()
        self.doc = create_simple_document(self.user, word_count=50)

    def test_get_words_default(self):
        resp = self.client.get(f'/api/documents/{self.doc.id}/words/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['total_words'], 50)
        self.assertEqual(len(resp.data['words']), 50)

    def test_get_words_range(self):
        resp = self.client.get(f'/api/documents/{self.doc.id}/words/', {
            'start': 10, 'count': 5,
        })
        self.assertEqual(len(resp.data['words']), 5)
        self.assertEqual(resp.data['words'][0]['pos'], 10)

    def test_get_words_count_capped(self):
        resp = self.client.get(f'/api/documents/{self.doc.id}/words/', {
            'count': 5000,
        })
        self.assertLessEqual(len(resp.data['words']), 1000)

    def test_get_words_not_found(self):
        resp = self.client.get('/api/documents/99999/words/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class ProgressViewTests(TestCase):
    def setUp(self):
        self.client, self.user = create_authed_client()
        self.doc = create_simple_document(self.user, word_count=100)
        self.client.get(f'/api/documents/{self.doc.id}/read/')

    def test_save_progress(self):
        resp = self.client.post(
            f'/api/documents/{self.doc.id}/progress/',
            {'position': 50, 'reading_time': 30},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['position'], 50)
        session = ReadingSession.objects.get(user=self.user, document=self.doc)
        self.assertEqual(session.current_position, 50)
        self.assertEqual(session.total_reading_time, 30)

    def test_progress_accumulates_reading_time(self):
        self.client.post(
            f'/api/documents/{self.doc.id}/progress/',
            {'position': 20, 'reading_time': 10},
            format='json',
        )
        self.client.post(
            f'/api/documents/{self.doc.id}/progress/',
            {'position': 40, 'reading_time': 15},
            format='json',
        )
        session = ReadingSession.objects.get(user=self.user, document=self.doc)
        self.assertEqual(session.total_reading_time, 25)

    def test_progress_marks_completion(self):
        self.client.post(
            f'/api/documents/{self.doc.id}/progress/',
            {'position': 100},
            format='json',
        )
        session = ReadingSession.objects.get(user=self.user, document=self.doc)
        self.assertIsNotNone(session.completed_at)

    def test_progress_no_session(self):
        doc2 = create_simple_document(self.user, 'Other')
        resp = self.client.post(
            f'/api/documents/{doc2.id}/progress/',
            {'position': 5},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_progress_invalid_position(self):
        resp = self.client.post(
            f'/api/documents/{self.doc.id}/progress/',
            {'position': -1},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class ChaptersViewTests(TestCase):
    def setUp(self):
        self.client, self.user = create_authed_client()
        self.doc = create_document_with_chapters(self.user)

    def test_get_chapters(self):
        resp = self.client.get(f'/api/documents/{self.doc.id}/chapters/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        chapters = resp.data['chapters']
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0]['start'], 0)
        self.assertEqual(chapters[1]['start'], 10)

    def test_no_chapters_single_chapter_doc(self):
        doc = create_simple_document(self.user, 'Single Chapter')
        resp = self.client.get(f'/api/documents/{doc.id}/chapters/')
        self.assertEqual(resp.data['chapters'], [])


class SessionUpdateTests(TestCase):
    def setUp(self):
        self.client, self.user = create_authed_client()
        self.doc = create_simple_document(self.user)
        self.client.get(f'/api/documents/{self.doc.id}/read/')

    def test_update_wpm(self):
        resp = self.client.patch(
            f'/api/documents/{self.doc.id}/session/',
            {'wpm': 500},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['wpm'], 500)

    def test_update_chunk_size(self):
        resp = self.client.patch(
            f'/api/documents/{self.doc.id}/session/',
            {'chunk_size': 3},
            format='json',
        )
        self.assertEqual(resp.data['chunk_size'], 3)

    def test_update_wpm_out_of_range(self):
        resp = self.client.patch(
            f'/api/documents/{self.doc.id}/session/',
            {'wpm': 10},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_no_session(self):
        doc2 = create_simple_document(self.user, 'Other')
        resp = self.client.patch(
            f'/api/documents/{doc2.id}/session/',
            {'wpm': 300},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
