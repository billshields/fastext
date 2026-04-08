from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, UserPreferences


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    pass


@admin.register(UserPreferences)
class UserPreferencesAdmin(admin.ModelAdmin):
    list_display = ['user', 'default_wpm', 'font_family']
