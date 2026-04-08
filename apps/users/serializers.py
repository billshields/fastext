from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import UserPreferences

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password']

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreferences
        fields = [
            'default_wpm', 'chunk_size',
            'background_color', 'text_color', 'ui_color',
            'font_family', 'font_size',
            'pivot_highlight', 'focus_line',
            'sentence_pause', 'long_word_pause',
            'tts_enabled', 'tts_voice',
        ]
