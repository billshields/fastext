"""Production settings. Values come from the environment or the .env file next to manage.py.

See deploy/README.md for the full list and deploy/env.example for a template.
"""
from decouple import Csv, config

from .base import *  # noqa: F401, F403
from .base import BASE_DIR, REST_FRAMEWORK

DEBUG = False

SECRET_KEY = config('SECRET_KEY')
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())
CSRF_TRUSTED_ORIGINS = [f'https://{host}' for host in ALLOWED_HOSTS]
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='', cast=Csv())

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': config('DB_NAME', default='fastext'),
        'USER': config('DB_USER', default='fastext'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
        'CONN_MAX_AGE': 60,
    }
}

# Shared by all gunicorn workers, so the login throttle counts every attempt
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': config('CACHE_URL', default='redis://localhost:6379/1'),
    }
}

# nginx terminates TLS and passes requests on over a local socket
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# Every request arrives from nginx, so take the client address for throttling from X-Forwarded-For
REST_FRAMEWORK = {**REST_FRAMEWORK, 'NUM_PROXIES': 1}

STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    # Hashed filenames: browsers can cache static files for a year and still pick up each deploy
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage',
    },
}

# To stderr, which systemd's journal collects: `journalctl -u fastext-web`
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
}
