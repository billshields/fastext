import requests
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import Document
from apps.documents.serializers import DocumentSerializer
from .models import CatalogSource
from .serializers import CatalogImportSerializer
from .gutenberg import search_gutenberg
from .tasks import process_catalog_source


class CatalogSearchView(APIView):
    def get(self, request):
        query = request.query_params.get('q', '').strip()
        page = int(request.query_params.get('page', 1))
        sort = request.query_params.get('sort', 'popular').strip()
        topic = request.query_params.get('topic', '').strip()

        try:
            data = search_gutenberg(query=query, page=page, sort=sort, topic=topic)
        except requests.RequestException as e:
            return Response(
                {'detail': f'Search service unavailable: {e}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        gutenberg_ids = [str(r['gutenberg_id']) for r in data['results']]

        # Which of these does the user already have in their library?
        user_library_ids = set(
            Document.objects.filter(
                user=request.user,
                catalog_source__platform='gutenberg',
                catalog_source__external_id__in=gutenberg_ids,
            ).values_list('catalog_source__external_id', flat=True)
        )

        # What's the processing status of ones we already have locally?
        catalog_statuses = dict(
            CatalogSource.objects.filter(
                platform='gutenberg',
                external_id__in=gutenberg_ids,
            ).values_list('external_id', 'status')
        )

        for result in data['results']:
            ext_id = str(result['gutenberg_id'])
            result['in_library'] = ext_id in user_library_ids
            result['catalog_status'] = catalog_statuses.get(ext_id)

        return Response(data)


class CatalogImportView(APIView):
    def post(self, request):
        serializer = CatalogImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        platform = serializer.validated_data['platform']
        external_id = serializer.validated_data['external_id']
        title = serializer.validated_data['title']
        author = serializer.validated_data.get('author', '')

        # Check if user already has this book
        existing = Document.objects.filter(
            user=request.user,
            catalog_source__platform=platform,
            catalog_source__external_id=external_id,
        ).first()
        if existing:
            return Response(
                {'detail': 'This book is already in your library.', 'document_id': existing.id},
                status=status.HTTP_409_CONFLICT,
            )

        # Get or create the shared catalog source
        source_url = f'https://www.gutenberg.org/cache/epub/{external_id}/pg{external_id}.txt'
        catalog_source, created = CatalogSource.objects.get_or_create(
            platform=platform,
            external_id=external_id,
            defaults={
                'title': title,
                'author': author,
                'source_url': source_url,
                'status': CatalogSource.Status.PENDING,
            },
        )

        if created:
            process_catalog_source.delay(catalog_source.id)

        # Determine document status based on catalog source status
        if catalog_source.status == CatalogSource.Status.COMPLETED:
            doc_status = Document.Status.COMPLETED
        else:
            doc_status = Document.Status.PROCESSING

        doc = Document.objects.create(
            user=request.user,
            title=catalog_source.title,
            file_type='gutenberg',
            status=doc_status,
            total_words=catalog_source.total_words,
            processed_at=catalog_source.processed_at,
            catalog_source=catalog_source,
        )

        resp_status = status.HTTP_201_CREATED if doc_status == Document.Status.COMPLETED else status.HTTP_202_ACCEPTED
        return Response(DocumentSerializer(doc).data, status=resp_status)
