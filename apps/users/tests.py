from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from .models import User, UserPreferences


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
