from django.db import transaction
from django.db.models import OuterRef, Subquery, Value, Case, When, F, FloatField
from django.db.models.functions import Cast
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reading.models import ReadingSession
from .models import Document
from .serializers import DocumentSerializer, DocumentUploadSerializer, DocumentPasteSerializer, DocumentURLSerializer
from .tasks import process_document


class DocumentListView(generics.ListAPIView):
    serializer_class = DocumentSerializer

    def get_queryset(self):
        position_subquery = ReadingSession.objects.filter(
            document=OuterRef('pk'),
            user=self.request.user,
        ).values('current_position')[:1]

        last_read_subquery = ReadingSession.objects.filter(
            document=OuterRef('pk'),
            user=self.request.user,
        ).values('last_read_at')[:1]

        qs = Document.objects.filter(
            user=self.request.user,
        ).annotate(
            current_position=Subquery(position_subquery, default=Value(0)),
            last_read_at=Subquery(last_read_subquery),
            progress=Case(
                When(total_words=0, then=Value(0.0)),
                default=Cast(F('current_position'), FloatField()) / Cast(F('total_words'), FloatField()),
                output_field=FloatField(),
            ),
        )

        # Search filter
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(title__icontains=search)

        # Status filter
        status_filter = self.request.query_params.get('status', '').strip()
        valid_statuses = {choice[0] for choice in Document.Status.choices}
        if status_filter and status_filter in valid_statuses:
            qs = qs.filter(status=status_filter)

        # Sort
        sort_options = {
            'title_asc': 'title',
            'title_desc': '-title',
            'uploaded_newest': '-uploaded_at',
            'uploaded_oldest': 'uploaded_at',
            'last_read': F('last_read_at').desc(nulls_last=True),
            'progress_desc': '-progress',
            'progress_asc': 'progress',
        }
        sort = self.request.query_params.get('sort', 'uploaded_newest').strip()
        ordering = sort_options.get(sort, '-uploaded_at')
        qs = qs.order_by(ordering)

        return qs


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
            doc.sessions.update(current_position=0, completed_at=None)

        return Response({'id': doc.id, 'total_words': doc.total_words})


class DocumentPasteView(APIView):
    def post(self, request):
        from .models import DocumentChunk
        import re

        serializer = DocumentPasteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        title = serializer.validated_data['title']
        text = serializer.validated_data['text']
        words = text.split()

        with transaction.atomic():
            doc = Document.objects.create(
                user=request.user,
                title=title,
                file_type='text',
                file_size=len(text.encode('utf-8')),
                status=Document.Status.COMPLETED,
                total_words=len(words),
                processed_at=timezone.now(),
            )

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

        return Response(
            DocumentSerializer(doc).data,
            status=status.HTTP_201_CREATED,
        )


class DocumentURLView(APIView):
    def post(self, request):
        import re
        import trafilatura
        from .models import DocumentChunk

        serializer = DocumentURLSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        url = serializer.validated_data['url']
        user_title = serializer.validated_data.get('title', '').strip()

        import cloudscraper

        try:
            scraper = cloudscraper.create_scraper()
            resp = scraper.get(url, timeout=20)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            return Response(
                {'detail': f'Could not fetch the URL: {e}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            deduplicate=True,
        )
        if not text or len(text.strip()) < 10:
            return Response(
                {'detail': 'Could not extract readable content from this URL. The site may require JavaScript or block automated access.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user_title:
            metadata = trafilatura.extract_metadata(html)
            user_title = metadata.title if metadata and metadata.title else url.split('/')[-1] or 'Imported Article'

        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        words_with_meta = []
        para_idx = 0
        for paragraph in paragraphs:
            for word in paragraph.split():
                sentence_end = bool(re.search(r'[.!?]["\')\]]?$', word))
                words_with_meta.append((word, para_idx, sentence_end))
            para_idx += 1

        if not words_with_meta:
            return Response(
                {'detail': 'No readable text found at this URL.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            doc = Document.objects.create(
                user=request.user,
                title=user_title,
                original_filename=url,
                file_type='url',
                file_size=len(text.encode('utf-8')),
                status=Document.Status.COMPLETED,
                total_words=len(words_with_meta),
                processed_at=timezone.now(),
            )

            chunks = []
            for i, (word, para, se) in enumerate(words_with_meta):
                chunks.append(DocumentChunk(
                    document=doc,
                    position=i,
                    word=word,
                    chapter_index=0,
                    paragraph_index=para,
                    sentence_end=se,
                ))
                if len(chunks) >= 5000:
                    DocumentChunk.objects.bulk_create(chunks)
                    chunks = []

            if chunks:
                DocumentChunk.objects.bulk_create(chunks)

        return Response(
            DocumentSerializer(doc).data,
            status=status.HTTP_201_CREATED,
        )


class DocumentBulkDeleteView(APIView):
    def post(self, request):
        ids = request.data.get('ids', [])
        if not isinstance(ids, list) or not ids:
            return Response({'detail': 'Provide a non-empty list of document IDs.'}, status=status.HTTP_400_BAD_REQUEST)
        deleted_count, _ = Document.objects.filter(id__in=ids, user=request.user).delete()
        return Response({'deleted': deleted_count})
