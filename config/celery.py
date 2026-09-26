import os

from celery import Celery
from decouple import config

os.environ.setdefault('DJANGO_SETTINGS_MODULE', config('DJANGO_SETTINGS_MODULE', default='config.settings.dev'))

app = Celery('fastext')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
