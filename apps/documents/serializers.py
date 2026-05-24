from rest_framework import serializers

from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    current_position = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Document
        fields = [
            'id', 'title', 'original_filename', 'file_type', 'file_size',
            'status', 'total_words', 'error_message', 'uploaded_at', 'processed_at',
            'current_position',
        ]
        read_only_fields = fields


class DocumentPasteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=500)
    text = serializers.CharField(min_length=1, max_length=5_000_000)


class DocumentURLSerializer(serializers.Serializer):
    url = serializers.URLField()
    title = serializers.CharField(max_length=500, required=False, allow_blank=True)


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    title = serializers.CharField(max_length=500, required=False)

    def validate_file(self, value):
        ext = value.name.rsplit('.', 1)[-1].lower() if '.' in value.name else ''
        if ext not in ('pdf', 'epub'):
            raise serializers.ValidationError("Only PDF and EPUB files are supported.")
        if value.size > 52428800:
            raise serializers.ValidationError("File size exceeds 50MB limit.")
        return value
