from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from apps.users.models import User
from .models import Document, DocumentChunk


def create_authed_client(username='testuser'):
    client = APIClient()
    user = User.objects.create_user(username, f'{username}@example.com', 'testpass123')
    resp = client.post('/api/auth/login/', {
        'username': username,
        'password': 'testpass123',
    })
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')
    return client, user


def create_document_with_words(user, title='Test Doc', words=None):
    if words is None:
        words = ['Hello', 'world.', 'This', 'is', 'a', 'test.']
    doc = Document.objects.create(
        user=user,
        title=title,
        file_type='text',
        status=Document.Status.COMPLETED,
        total_words=len(words),
    )
    chunks = []
    for i, word in enumerate(words):
        chunks.append(DocumentChunk(
            document=doc,
            position=i,
            word=word,
            chapter_index=0,
            paragraph_index=0,
            sentence_end=word.endswith('.'),
        ))
    DocumentChunk.objects.bulk_create(chunks)
    return doc


class DocumentPasteTests(TestCase):
    def setUp(self):
        self.client, self.user = create_authed_client()

    def test_paste_success(self):
        resp = self.client.post('/api/documents/paste/', {
            'title': 'My Paste',
            'text': 'Hello world. This is a test.',
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['title'], 'My Paste')
        self.assertEqual(resp.data['total_words'], 6)
        self.assertEqual(resp.data['status'], 'completed')

    def test_paste_creates_chunks(self):
        self.client.post('/api/documents/paste/', {
            'title': 'My Paste',
            'text': 'Word one two three.',
        })
        doc = Document.objects.get(title='My Paste')
        self.assertEqual(doc.chunks.count(), 4)
        first_chunk = doc.chunks.get(position=0)
        self.assertEqual(first_chunk.word, 'Word')
        last_chunk = doc.chunks.get(position=3)
        self.assertTrue(last_chunk.sentence_end)

    def test_paste_empty_text(self):
        resp = self.client.post('/api/documents/paste/', {
            'title': 'Empty',
            'text': '',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_paste_missing_title(self):
        resp = self.client.post('/api/documents/paste/', {
            'text': 'some words here',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_paste_unauthenticated(self):
        client = APIClient()
        resp = client.post('/api/documents/paste/', {
            'title': 'No Auth',
            'text': 'hello world',
        })
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class DocumentListTests(TestCase):
    def setUp(self):
        self.client, self.user = create_authed_client()
        self.doc1 = create_document_with_words(self.user, 'Alpha Doc')
        self.doc2 = create_document_with_words(self.user, 'Beta Doc')

    def test_list_documents(self):
        resp = self.client.get('/api/documents/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 2)

    def test_list_search(self):
        resp = self.client.get('/api/documents/', {'search': 'Alpha'})
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['title'], 'Alpha Doc')

    def test_list_status_filter(self):
        Document.objects.create(
            user=self.user, title='Pending', file_type='pdf', status=Document.Status.PENDING,
        )
        resp = self.client.get('/api/documents/', {'status': 'pending'})
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['title'], 'Pending')

    def test_list_sort_title(self):
        resp = self.client.get('/api/documents/', {'sort': 'title_asc'})
        titles = [d['title'] for d in resp.data]
        self.assertEqual(titles, ['Alpha Doc', 'Beta Doc'])

    def test_list_isolated_by_user(self):
        other_client, other_user = create_authed_client('otheruser')
        create_document_with_words(other_user, 'Other Doc')
        resp = self.client.get('/api/documents/')
        self.assertEqual(len(resp.data), 2)
        resp2 = other_client.get('/api/documents/')
        self.assertEqual(len(resp2.data), 1)


class DocumentDetailTests(TestCase):
    def setUp(self):
        self.client, self.user = create_authed_client()
        self.doc = create_document_with_words(self.user)

    def test_get_document(self):
        resp = self.client.get(f'/api/documents/{self.doc.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['title'], 'Test Doc')

    def test_get_other_users_document(self):
        _, other_user = create_authed_client('otheruser')
        other_doc = create_document_with_words(other_user, 'Secret')
        resp = self.client.get(f'/api/documents/{other_doc.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_document(self):
        resp = self.client.delete(f'/api/documents/{self.doc.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Document.objects.filter(id=self.doc.id).exists())

    def test_delete_cascades_chunks(self):
        doc_id = self.doc.id
        self.assertEqual(DocumentChunk.objects.filter(document_id=doc_id).count(), 6)
        self.client.delete(f'/api/documents/{doc_id}/')
        self.assertEqual(DocumentChunk.objects.filter(document_id=doc_id).count(), 0)


class DocumentStatusTests(TestCase):
    def setUp(self):
        self.client, self.user = create_authed_client()
        self.doc = create_document_with_words(self.user)

    def test_get_status(self):
        resp = self.client.get(f'/api/documents/{self.doc.id}/status/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'completed')
        self.assertEqual(resp.data['total_words'], 6)

    def test_status_not_found(self):
        resp = self.client.get('/api/documents/99999/status/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class DocumentTextTests(TestCase):
    def setUp(self):
        self.client, self.user = create_authed_client()
        self.doc = create_document_with_words(self.user, words=['Hello', 'world.'])

    def test_get_text(self):
        resp = self.client.get(f'/api/documents/{self.doc.id}/text/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['text'], 'Hello world.')

    def test_edit_text(self):
        resp = self.client.put(
            f'/api/documents/{self.doc.id}/text/',
            {'text': 'New content here now.'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['total_words'], 4)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.total_words, 4)
        self.assertEqual(self.doc.chunks.count(), 4)

    def test_edit_empty_text(self):
        resp = self.client.put(
            f'/api/documents/{self.doc.id}/text/',
            {'text': ''},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_text_pending_doc(self):
        doc = Document.objects.create(
            user=self.user, title='Pending', file_type='pdf', status=Document.Status.PENDING,
        )
        resp = self.client.get(f'/api/documents/{doc.id}/text/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class DocumentBulkDeleteTests(TestCase):
    def setUp(self):
        self.client, self.user = create_authed_client()
        self.doc1 = create_document_with_words(self.user, 'Doc A')
        self.doc2 = create_document_with_words(self.user, 'Doc B')
        self.doc3 = create_document_with_words(self.user, 'Doc C')

    def test_bulk_delete(self):
        resp = self.client.post(
            '/api/documents/bulk-delete/',
            {'ids': [self.doc1.id, self.doc2.id]},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(resp.data['deleted'], 2)
        self.assertEqual(Document.objects.filter(user=self.user).count(), 1)

    def test_bulk_delete_other_users_docs(self):
        _, other_user = create_authed_client('otheruser')
        other_doc = create_document_with_words(other_user, 'Other')
        resp = self.client.post(
            '/api/documents/bulk-delete/',
            {'ids': [other_doc.id]},
            format='json',
        )
        self.assertEqual(resp.data['deleted'], 0)
        self.assertTrue(Document.objects.filter(id=other_doc.id).exists())

    def test_bulk_delete_empty_ids(self):
        resp = self.client.post(
            '/api/documents/bulk-delete/',
            {'ids': []},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
