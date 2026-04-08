from django.db import transaction
from django.db.models import OuterRef, Subquery, Value
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reading.models import ReadingSession
from .models import Document
from .serializers import DocumentSerializer, DocumentUploadSerializer
from .tasks import process_document


class DocumentListView(generics.ListAPIView):
    serializer_class = DocumentSerializer

    def get_queryset(self):
        position_subquery = ReadingSession.objects.filter(
            document=OuterRef('pk'),
            user=self.request.user,
        ).values('current_position')[:1]

        return Document.objects.filter(
            user=self.request.user,
        ).annotate(
            current_position=Subquery(position_subquery, default=Value(0)),
        ).order_by('-uploaded_at')


class DocumentUploadView(APIView):
    def post(self, request):
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data['file']
        ext = uploaded_file.name.rsplit('.', 1)[-1].lower()
        title = serializer.validated_data.get('title') or uploaded_file.name.rsplit('.', 1)[0]

        doc = Document.objects.create(
            user=request.user,
            title=title,
            original_filename=uploaded_file.name,
            file=uploaded_file,
            file_type=ext,
            file_size=uploaded_file.size,
        )
        process_document.delay(doc.id)

        return Response(
            DocumentSerializer(doc).data,
            status=status.HTTP_201_CREATED,
        )


class DocumentDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = DocumentSerializer

    def get_queryset(self):
        return Document.objects.filter(user=self.request.user)


class DocumentStatusView(APIView):
    def get(self, request, pk):
        try:
            doc = Document.objects.get(pk=pk, user=request.user)
        except Document.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response({
            'id': doc.id,
            'status': doc.status,
            'total_words': doc.total_words,
            'error_message': doc.error_message,
        })


class DocumentTextView(APIView):
    def get(self, request, pk):
        try:
            doc = Document.objects.get(pk=pk, user=request.user, status=Document.Status.COMPLETED)
        except Document.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        chunks = doc.chunks.order_by('position').values_list('word', flat=True)
        text = ' '.join(chunks)
        return Response({'id': doc.id, 'title': doc.title, 'text': text})

    def put(self, request, pk):
        from .models import DocumentChunk
        import re

        try:
            doc = Document.objects.get(pk=pk, user=request.user, status=Document.Status.COMPLETED)
        except Document.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        text = request.data.get('text', '').strip()
        if not text:
            return Response({'detail': 'Text cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)

        # Re-chunk the edited text
        words = text.split()

        with transaction.atomic():
            DocumentChunk.objects.filter(document=doc).delete()

            chunks = []
            for i, word in enumerate(words):
                sentence_end = bool(re.search(r'[.!?]["\')\]]?$', word))
                chunks.append(DocumentChunk(
                    document=doc,
                    position=i,
                    word=word,
                    chapter_index=0,
                    paragraph_index=0,
                    sentence_end=sentence_end,
                ))
                if len(chunks) >= 5000:
                    DocumentChunk.objects.bulk_create(chunks)
                    chunks = []

            if chunks:
                DocumentChunk.objects.bulk_create(chunks)

            doc.total_words = len(words)
            doc.save(update_fields=['total_words'])

            # Reset any reading sessions to the beginning
            doc.sessions.update(current_position=0)

        return Response({'id': doc.id, 'total_words': doc.total_words})
