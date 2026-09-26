from .base import *  # noqa: F401, F403

DEBUG = True
ALLOWED_HOSTS = ['*']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'speedreading',
        'USER': 'speedreader',
        'PASSWORD': 'speedreader_dev',
        'HOST': 'localhost',
        'PORT': '3306',
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}

CORS_ALLOW_ALL_ORIGINS = True

# No cache in dev, which also turns off login throttling. Otherwise every test that
# logs in, all from the same address, would count toward one limit.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}
