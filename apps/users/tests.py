from io import StringIO
from unittest import mock

from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status

from apps.catalog.models import CatalogSource
from apps.documents.models import Document
from .models import User, UserPreferences


@override_settings(ALLOW_REGISTRATION=True)
class RegisterTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_success(self):
        resp = self.client.post('/api/auth/register/', {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'testpass123',
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn('tokens', resp.data)
        self.assertIn('access', resp.data['tokens'])
        self.assertIn('refresh', resp.data['tokens'])
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_register_creates_preferences(self):
        self.client.post('/api/auth/register/', {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'testpass123',
        })
        user = User.objects.get(username='newuser')
        self.assertTrue(hasattr(user, 'preferences'))
        self.assertEqual(user.preferences.default_wpm, 300)

    def test_register_short_password(self):
        resp = self.client.post('/api/auth/register/', {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'short',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_duplicate_username(self):
        User.objects.create_user('existinguser', 'a@b.com', 'testpass123')
        resp = self.client.post('/api/auth/register/', {
            'username': 'existinguser',
            'email': 'new@example.com',
            'password': 'testpass123',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_fields(self):
        resp = self.client.post('/api/auth/register/', {'username': 'x'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_page_offers_registration(self):
        self.assertContains(self.client.get('/'), 'id="register-form"')


class RegistrationClosedTests(TestCase):
    def test_register_is_refused(self):
        resp = APIClient().post('/api/auth/register/', {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'testpass123',
        })
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(User.objects.filter(username='newuser').exists())

    def test_login_page_has_no_registration(self):
        resp = self.client.get('/')
        self.assertContains(resp, 'id="login-form"')
        self.assertNotContains(resp, 'register')


class LoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('testuser', 'test@example.com', 'testpass123')

    def test_login_success(self):
        resp = self.client.post('/api/auth/login/', {
            'username': 'testuser',
            'password': 'testpass123',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('access', resp.data)
        self.assertIn('refresh', resp.data)

    def test_login_wrong_password(self):
        resp = self.client.post('/api/auth/login/', {
            'username': 'testuser',
            'password': 'wrongpass',
        })
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_nonexistent_user(self):
        resp = self.client.post('/api/auth/login/', {
            'username': 'noone',
            'password': 'testpass123',
        })
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# Dev settings use a dummy cache, which never throttles
@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user('testuser', 'test@example.com', 'testpass123')

    def login(self, password, address='203.0.113.5'):
        return APIClient().post(
            '/api/auth/login/', {'username': 'testuser', 'password': password}, REMOTE_ADDR=address,
        )

    def test_blocks_guessing_after_ten_attempts(self):
        for _ in range(10):
            self.assertEqual(self.login('wrong').status_code, status.HTTP_401_UNAUTHORIZED)
        # Even the right password is refused until the minute is up
        self.assertEqual(self.login('testpass123').status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_limit_is_per_address(self):
        for _ in range(10):
            self.login('wrong')
        self.assertEqual(self.login('testpass123', address='203.0.113.6').status_code, status.HTTP_200_OK)


class LogoutTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('testuser', 'test@example.com', 'testpass123')
        resp = self.client.post('/api/auth/login/', {
            'username': 'testuser',
            'password': 'testpass123',
        })
        self.access = resp.data['access']
        self.refresh = resp.data['refresh']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access}')

    def test_logout_invalid_token(self):
        resp = self.client.post('/api/auth/logout/', {'refresh': 'garbage'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logout_revokes_refresh_token(self):
        resp = self.client.post('/api/auth/logout/', {'refresh': self.refresh})
        self.assertEqual(resp.status_code, status.HTTP_205_RESET_CONTENT)

        resp = self.client.post('/api/auth/refresh/', {'refresh': self.refresh})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_with_expired_access_token(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer expired.or.invalid')
        resp = self.client.post('/api/auth/logout/', {'refresh': self.refresh})
        self.assertEqual(resp.status_code, status.HTTP_205_RESET_CONTENT)

        resp = self.client.post('/api/auth/refresh/', {'refresh': self.refresh})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_rotation_revokes_old_token(self):
        resp = self.client.post('/api/auth/refresh/', {'refresh': self.refresh})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotEqual(resp.data['refresh'], self.refresh)

        resp = self.client.post('/api/auth/refresh/', {'refresh': self.refresh})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class PreferencesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('testuser', 'test@example.com', 'testpass123')
        resp = self.client.post('/api/auth/login/', {
            'username': 'testuser',
            'password': 'testpass123',
        })
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')

    def test_get_preferences(self):
        resp = self.client.get('/api/auth/preferences/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['default_wpm'], 300)
        self.assertEqual(resp.data['background_color'], '#1a1a2e')

    def test_update_preferences(self):
        resp = self.client.patch('/api/auth/preferences/', {
            'default_wpm': 450,
            'background_color': '#000000',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['default_wpm'], 450)
        self.assertEqual(resp.data['background_color'], '#000000')

    def test_partial_update(self):
        self.client.patch('/api/auth/preferences/', {'font_family': 'Roboto Mono'})
        resp = self.client.get('/api/auth/preferences/')
        self.assertEqual(resp.data['font_family'], 'Roboto Mono')
        self.assertEqual(resp.data['default_wpm'], 300)

    def test_preferences_unauthenticated(self):
        client = APIClient()
        resp = client.get('/api/auth/preferences/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


@override_settings(DEBUG=True)
@mock.patch('apps.users.management.commands.seed_browsertest.process_catalog_source.delay')
class SeedBrowsertestTests(TestCase):
    def seed(self):
        call_command('seed_browsertest', stdout=StringIO())

    def test_creates_account_and_fixtures(self, delay):
        self.seed()
        user = User.objects.get(username='browsertest')
        self.assertEqual(Document.objects.filter(user=user).count(), 2)
        probe = Document.objects.get(user=user, file_type='text')
        self.assertTrue(probe.title.startswith('<img'))
        self.assertEqual(probe.chunks.count(), probe.total_words)
        source = CatalogSource.objects.get(external_id='1342')
        delay.assert_called_once_with(source.id)

        resp = APIClient().post('/api/auth/login/', {'username': 'browsertest', 'password': 'browsertest-pass-123'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_rerun_keeps_data_and_resets_password(self, delay):
        self.seed()
        user = User.objects.get(username='browsertest')
        user.set_password('changed-by-a-test')
        user.save()

        self.seed()
        self.assertEqual(User.objects.filter(username='browsertest').count(), 1)
        self.assertEqual(Document.objects.filter(user=user).count(), 2)
        user.refresh_from_db()
        self.assertTrue(user.check_password('browsertest-pass-123'))

    def test_links_existing_catalog_book_without_downloading(self, delay):
        CatalogSource.objects.create(
            platform='gutenberg', external_id='1342', title='Pride and Prejudice',
            status=CatalogSource.Status.COMPLETED, total_words=100,
        )
        self.seed()
        book = Document.objects.get(user__username='browsertest', file_type='gutenberg')
        self.assertEqual(book.status, Document.Status.COMPLETED)
        self.assertEqual(book.total_words, 100)
        delay.assert_not_called()

    @override_settings(DEBUG=False)
    def test_refuses_without_debug(self, delay):
        with self.assertRaises(CommandError):
            self.seed()
        self.assertFalse(User.objects.filter(username='browsertest').exists())
