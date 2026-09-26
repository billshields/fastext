from django.conf import settings


def registration(request):
    return {'allow_registration': settings.ALLOW_REGISTRATION}
