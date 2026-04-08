from rest_framework import serializers

from .models import ReadingSession


class ReadingSessionSerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(source='document.title', read_only=True)
    total_words = serializers.IntegerField(source='document.total_words', read_only=True)

    class Meta:
        model = ReadingSession
        fields = [
            'id', 'document', 'document_title', 'current_position',
            'wpm', 'chunk_size', 'total_words', 'total_reading_time',
            'started_at', 'last_read_at',
        ]
        read_only_fields = ['id', 'document', 'started_at', 'last_read_at']


class ProgressSerializer(serializers.Serializer):
    position = serializers.IntegerField(min_value=0)
    reading_time = serializers.IntegerField(min_value=0, required=False, default=0)


class SessionUpdateSerializer(serializers.Serializer):
    wpm = serializers.IntegerField(min_value=50, max_value=2000, required=False)
    chunk_size = serializers.IntegerField(min_value=1, max_value=5, required=False)
