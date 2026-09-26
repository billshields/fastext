import zoneinfo

from django.utils import timezone


class BrowserTimezoneMiddleware:
    """Activate the timezone the frontend sends in the X-Timezone header, so
    timezone.localdate() buckets reading stats by the reader's day, not UTC."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tz_name = request.headers.get('X-Timezone', '')
        try:
            timezone.activate(zoneinfo.ZoneInfo(tz_name))
        except (zoneinfo.ZoneInfoNotFoundError, ValueError, OSError):
            timezone.deactivate()
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()
