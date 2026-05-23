from django.db.models import F, Min
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import Document, DocumentChunk
from apps.stats.models import DailyReadingLog
from .models import ReadingSession
from .serializers import ReadingSessionSerializer, ProgressSerializer, SessionUpdateSerializer


class ReadView(APIView):
    """Get or create a reading session, return session info + first batch of words."""

    def get(self, request, doc_id):
        try:
            doc = Document.objects.get(pk=doc_id, user=request.user, status=Document.Status.COMPLETED)
        except Document.DoesNotExist:
            return Response({'error': 'Document not found or not ready'}, status=status.HTTP_404_NOT_FOUND)

        session, _ = ReadingSession.objects.get_or_create(
            user=request.user,
            document=doc,
            defaults={
                'wpm': request.user.preferences.default_wpm,
                'chunk_size': request.user.preferences.chunk_size,
            },
        )

        # Always load from position 0 up to current_position + 500
        # so rewinding after reload always works
        words = list(
            DocumentChunk.objects.filter(
                document=doc,
                position__lt=session.current_position + 500,
            ).values('position', 'word', 'sentence_end')
        )

        return Response({
            'session': ReadingSessionSerializer(session).data,
            'words': [{'pos': w['position'], 'word': w['word'], 'se': w['sentence_end']} for w in words],
        })


class WordsView(APIView):
    """Return a range of words for a document."""

    def get(self, request, doc_id):
        start = int(request.query_params.get('start', 0))
        count = min(int(request.query_params.get('count', 500)), 1000)

        try:
            doc = Document.objects.get(pk=doc_id, user=request.user)
        except Document.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        words = list(
            DocumentChunk.objects.filter(
                document=doc,
                position__gte=start,
                position__lt=start + count,
            ).values('position', 'word', 'sentence_end')
        )

        return Response({
            'document_id': doc.id,
            'start': start,
            'count': len(words),
            'total_words': doc.total_words,
            'words': [{'pos': w['position'], 'word': w['word'], 'se': w['sentence_end']} for w in words],
        })


class ProgressView(APIView):
    """Save reading progress."""

    def post(self, request, doc_id):
        serializer = ProgressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            session = ReadingSession.objects.get(user=request.user, document_id=doc_id)
        except ReadingSession.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        old_position = session.current_position
        new_position = serializer.validated_data['position']
        words_advanced = max(0, new_position - old_position)
        reading_time = serializer.validated_data.get('reading_time', 0)

        session.current_position = new_position
        if reading_time:
            session.total_reading_time += reading_time
        session.save(update_fields=['current_position', 'total_reading_time', 'last_read_at'])

        # Log daily reading stats
        today = timezone.now().date()
        DailyReadingLog.objects.update_or_create(
            user=request.user, document_id=doc_id, date=today,
            defaults={},
        )
        DailyReadingLog.objects.filter(
            user=request.user, document_id=doc_id, date=today,
        ).update(
            reading_time=F('reading_time') + reading_time,
            words_read=F('words_read') + words_advanced,
            ending_wpm=session.wpm,
            sessions_count=F('sessions_count') + 1,
        )

        # Check completion
        if (new_position >= session.document.total_words - session.chunk_size
                and not session.completed_at):
            session.completed_at = timezone.now()
            session.save(update_fields=['completed_at'])

        return Response({'position': session.current_position})


class ChaptersView(APIView):
    """Return chapter boundaries for a document."""

    def get(self, request, doc_id):
        try:
            doc = Document.objects.get(pk=doc_id, user=request.user)
        except Document.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        chapters = list(
            DocumentChunk.objects.filter(document=doc)
            .values('chapter_index')
            .annotate(start_position=Min('position'))
            .order_by('chapter_index')
        )

        if len(chapters) <= 1:
            return Response({'chapters': []})

        # Get the first word of each chapter as a label preview
        start_positions = [c['start_position'] for c in chapters]
        first_words = {
            chunk['position']: chunk['word']
            for chunk in DocumentChunk.objects.filter(
                document=doc, position__in=start_positions
            ).values('position', 'word')
        }

        return Response({
            'chapters': [
                {
                    'index': c['chapter_index'],
                    'start': c['start_position'],
                    'label': f"Chapter {c['chapter_index'] + 1}",
                    'first_word': first_words.get(c['start_position'], ''),
                }
                for c in chapters
            ],
        })


class SessionUpdateView(APIView):
    """Update session settings (WPM, chunk size)."""

    def patch(self, request, doc_id):
        serializer = SessionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            session = ReadingSession.objects.get(user=request.user, document_id=doc_id)
        except ReadingSession.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        update_fields = []
        if 'wpm' in serializer.validated_data:
            session.wpm = serializer.validated_data['wpm']
            update_fields.append('wpm')
        if 'chunk_size' in serializer.validated_data:
            session.chunk_size = serializer.validated_data['chunk_size']
            update_fields.append('chunk_size')

        if update_fields:
            session.save(update_fields=update_fields)

        return Response(ReadingSessionSerializer(session).data)
