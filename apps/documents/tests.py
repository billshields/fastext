import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import requests
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient
from rest_framework import status

from apps.users.models import User
from . import fetch
from .fetch import BlockedAddressError, FetchError, ResponseTooLargeError
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


ARTICLE_HTML = b"""<html><head><title>Test Article</title></head><body><article>
<h1>Test Article</h1>
<p>Speed reading is a collection of techniques that aim to raise reading speed without losing comprehension.</p>
<p>Rapid serial visual presentation shows one word at a time in a fixed spot, so the eyes never have to move.</p>
<p>Readers usually start around three hundred words per minute and build up from there over several weeks.</p>
</article></body></html>"""


class IsPublicIpTests(SimpleTestCase):
    def test_blocks_internal_addresses(self):
        for address in [
            '127.0.0.1', '10.0.0.1', '172.16.0.1', '192.168.1.1', '169.254.169.254', '100.64.0.1',
            '0.0.0.0', '224.0.0.1', '::1', '::', 'fe80::1', 'fc00::1', 'ff02::1',
            '::ffff:127.0.0.1', '::127.0.0.1', '64:ff9b::7f00:1', 'not-an-ip',
        ]:
            with self.subTest(address=address):
                self.assertFalse(fetch.is_public_ip(address))

    def test_allows_public_addresses(self):
        for address in ['8.8.8.8', '1.1.1.1', '2606:4700::1111', '::ffff:8.8.8.8', '64:ff9b::808:808']:
            with self.subTest(address=address):
                self.assertTrue(fetch.is_public_ip(address))


class TestPageHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        routes = {
            '/article': (200, ARTICLE_HTML, None),
            '/redirect-to-article': (302, b'', '/article'),
            '/redirect-to-private': (302, b'', 'http://10.0.0.1/'),
            '/huge': (200, b'x' * 5000, None),
            '/huge-redirect': (302, b'x' * 5000, '/article'),
        }
        code, body, location = routes.get(self.path, (404, b'not found', None))
        self.send_response(code)
        if location:
            self.send_header('Location', location)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


REAL_GETADDRINFO = socket.getaddrinfo
REAL_IS_PUBLIC_IP = fetch.is_public_ip


class FetchPageTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), TestPageHandler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        super().tearDownClass()

    def setUp(self):
        # Fake DNS. A host with several answers gives the next one on each lookup.
        self.dns = {'site.test': ['127.0.0.1'], 'internal.test': ['10.0.0.1']}
        self.lookups = []
        patcher = mock.patch('socket.getaddrinfo', side_effect=self.fake_getaddrinfo)
        patcher.start()
        self.addCleanup(patcher.stop)

        # The test server listens on loopback, so let its address count as public
        patcher = mock.patch.object(fetch, 'is_public_ip', side_effect=lambda a: a == '127.0.0.1' or REAL_IS_PUBLIC_IP(a))
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_getaddrinfo(self, host, port, *args, **kwargs):
        if host not in self.dns:
            return REAL_GETADDRINFO(host, port, *args, **kwargs)
        self.lookups.append(host)
        answers = self.dns[host]
        address = answers.pop(0) if len(answers) > 1 else answers[0]
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (address, port))]

    def url(self, path, host='site.test'):
        return f'http://{host}:{self.port}{path}'

    def test_fetches_public_page(self):
        self.assertEqual(fetch.fetch_page(self.url('/article')), ARTICLE_HTML)

    def test_follows_redirect_to_public_page(self):
        self.assertEqual(fetch.fetch_page(self.url('/redirect-to-article')), ARTICLE_HTML)

    def test_blocks_loopback_address(self):
        with mock.patch.object(fetch, 'is_public_ip', REAL_IS_PUBLIC_IP):
            with self.assertRaises(BlockedAddressError):
                fetch.fetch_page(self.url('/article', host='127.0.0.1'))

    def test_blocks_hostname_resolving_to_private_address(self):
        with self.assertRaises(BlockedAddressError):
            fetch.fetch_page(self.url('/article', host='internal.test'))

    def test_blocks_redirect_to_private_address(self):
        with self.assertRaises(BlockedAddressError):
            fetch.fetch_page(self.url('/redirect-to-private'))

    def test_connects_to_the_address_it_checked(self):
        # A rebinding DNS server answers public first, then private
        self.dns['rebind.test'] = ['127.0.0.1', '10.0.0.1']
        self.assertEqual(fetch.fetch_page(self.url('/article', host='rebind.test')), ARTICLE_HTML)
        self.assertEqual(self.lookups.count('rebind.test'), 1)

    def test_ignores_proxy_settings_from_environment(self):
        proxy = 'http://10.0.0.1:9'
        with mock.patch.dict(os.environ, {'HTTP_PROXY': proxy, 'http_proxy': proxy, 'NO_PROXY': '', 'no_proxy': ''}):
            self.assertEqual(fetch.fetch_page(self.url('/article')), ARTICLE_HTML)

    def test_rejects_oversized_response(self):
        with mock.patch.object(fetch, 'MAX_RESPONSE_BYTES', 1000):
            with self.assertRaises(ResponseTooLargeError):
                fetch.fetch_page(self.url('/huge'))

    def test_rejects_oversized_redirect_body(self):
        with mock.patch.object(fetch, 'MAX_RESPONSE_BYTES', 1000):
            with self.assertRaises(ResponseTooLargeError):
                fetch.fetch_page(self.url('/huge-redirect'))

    def test_gives_up_after_deadline(self):
        with mock.patch.object(fetch, 'DEADLINE_SECONDS', -1):
            with self.assertRaisesMessage(FetchError, 'took too long'):
                fetch.fetch_page(self.url('/article'))

    def test_error_status_raises_http_error(self):
        with self.assertRaises(requests.HTTPError):
            fetch.fetch_page(self.url('/missing'))


@mock.patch('apps.documents.fetch.fetch_page')
class DocumentURLImportTests(TestCase):
    def setUp(self):
        self.client, self.user = create_authed_client()

    def post(self, url='https://example.com/article'):
        return self.client.post('/api/documents/url/', {'url': url}, format='json')

    def test_imports_article(self, fetch_page):
        fetch_page.return_value = ARTICLE_HTML
        resp = self.post()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['title'], 'Test Article')
        doc = Document.objects.get(id=resp.data['id'])
        self.assertGreater(doc.total_words, 0)
        self.assertEqual(doc.chunks.count(), doc.total_words)

    def test_blocked_address_is_explained(self, fetch_page):
        fetch_page.side_effect = BlockedAddressError('This URL points to a private or local network address.')
        with self.assertLogs('apps.documents.views', 'WARNING'):
            resp = self.post('http://10.0.0.1/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('private or local network', resp.data['detail'])
        self.assertFalse(Document.objects.exists())

    def test_unexpected_error_details_stay_in_the_log(self, fetch_page):
        fetch_page.side_effect = requests.ConnectionError('connection to 10.1.2.3:6379 refused')
        with self.assertLogs('apps.documents.views', 'WARNING') as logs:
            resp = self.post()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn('10.1.2.3', resp.data['detail'])
        self.assertIn('10.1.2.3', str(logs.records[0].exc_info[1]))

    def test_error_status_is_reported(self, fetch_page):
        response = requests.Response()
        response.status_code = 404
        fetch_page.side_effect = requests.HTTPError(response=response)
        resp = self.post()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('404', resp.data['detail'])

    def test_rejects_non_http_urls(self, fetch_page):
        resp = self.post('ftp://example.com/file.txt')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['url'], ['Only http and https URLs can be imported.'])
        fetch_page.assert_not_called()
