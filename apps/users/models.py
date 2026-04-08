from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    pass


class UserPreferences(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='preferences')
    default_wpm = models.PositiveIntegerField(default=300)
    chunk_size = models.PositiveSmallIntegerField(default=1)
    background_color = models.CharField(max_length=7, default='#1a1a2e')
    text_color = models.CharField(max_length=7, default='#e0e0e0')
    ui_color = models.CharField(max_length=7, default='#0f3460')
    font_family = models.CharField(max_length=50, default='Georgia')
    font_size = models.PositiveSmallIntegerField(default=48)
    pivot_highlight = models.BooleanField(default=False)
    focus_line = models.BooleanField(default=False)
    sentence_pause = models.BooleanField(default=False)
    long_word_pause = models.BooleanField(default=False)
    tts_enabled = models.BooleanField(default=False)
    tts_voice = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_preferences'

    def __str__(self):
        return f"Preferences for {self.user.username}"
