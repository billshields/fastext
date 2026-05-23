from datetime import timedelta

from django.db.models import Sum, Avg
from django.db.models.functions import TruncWeek
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reading.models import ReadingSession
from .models import DailyReadingLog


def calculate_streaks(user):
    dates = list(
        DailyReadingLog.objects.filter(user=user)
        .values_list('date', flat=True)
        .distinct()
        .order_by('-date')
    )
    if not dates:
        return 0, 0

    today = timezone.now().date()

    # Current streak: must include today or yesterday
    current_streak = 0
    expected = today
    for d in dates:
        if d == expected:
            current_streak += 1
            expected -= timedelta(days=1)
        elif d == expected - timedelta(days=1) and current_streak == 0:
            current_streak = 1
            expected = d - timedelta(days=1)
        else:
            break

    # Longest streak
    dates_asc = sorted(set(dates))
    longest = 1
    run = 1
    for i in range(1, len(dates_asc)):
        if dates_asc[i] - dates_asc[i - 1] == timedelta(days=1):
            run += 1
            longest = max(longest, run)
        else:
            run = 1

    return current_streak, max(longest, current_streak)


class StatsOverviewView(APIView):
    def get(self, request):
        user = request.user
        today = timezone.now().date()

        totals = DailyReadingLog.objects.filter(user=user).aggregate(
            total_reading_time=Sum('reading_time'),
            total_words_read=Sum('words_read'),
        )
        today_totals = DailyReadingLog.objects.filter(user=user, date=today).aggregate(
            today_reading_time=Sum('reading_time'),
            today_words_read=Sum('words_read'),
        )

        documents_completed = ReadingSession.objects.filter(
            user=user, completed_at__isnull=False,
        ).count()
        documents_in_progress = ReadingSession.objects.filter(
            user=user, completed_at__isnull=True,
        ).count()

        current_streak, longest_streak = calculate_streaks(user)

        return Response({
            'total_reading_time': totals['total_reading_time'] or 0,
            'total_words_read': totals['total_words_read'] or 0,
            'documents_completed': documents_completed,
            'documents_in_progress': documents_in_progress,
            'current_streak': current_streak,
            'longest_streak': longest_streak,
            'today_reading_time': today_totals['today_reading_time'] or 0,
            'today_words_read': today_totals['today_words_read'] or 0,
        })


class ReadingTimeView(APIView):
    def get(self, request):
        user = request.user
        period = request.query_params.get('period', 'week')
        today = timezone.now().date()

        if period == 'week':
            start_date = today - timedelta(days=6)
        elif period == 'month':
            start_date = today - timedelta(days=29)
        else:
            start_date = today - timedelta(days=364)

        qs = DailyReadingLog.objects.filter(
            user=user, date__gte=start_date, date__lte=today,
        )

        if period == 'year':
            data = list(
                qs.annotate(week=TruncWeek('date'))
                .values('week')
                .annotate(
                    reading_time=Sum('reading_time'),
                    words_read=Sum('words_read'),
                )
                .order_by('week')
            )
            result = [
                {
                    'date': row['week'].strftime('%Y-%m-%d'),
                    'reading_time': row['reading_time'] or 0,
                    'words_read': row['words_read'] or 0,
                }
                for row in data
            ]
        else:
            data = list(
                qs.values('date')
                .annotate(
                    reading_time=Sum('reading_time'),
                    words_read=Sum('words_read'),
                )
                .order_by('date')
            )
            result = [
                {
                    'date': row['date'].strftime('%Y-%m-%d'),
                    'reading_time': row['reading_time'] or 0,
                    'words_read': row['words_read'] or 0,
                }
                for row in data
            ]

        return Response({'period': period, 'data': result})


class WpmHistoryView(APIView):
    def get(self, request):
        user = request.user
        document_id = request.query_params.get('document_id')

        qs = DailyReadingLog.objects.filter(user=user)
        if document_id:
            qs = qs.filter(document_id=document_id)
            data = list(
                qs.values('date')
                .annotate(wpm=Avg('ending_wpm'))
                .order_by('date')
            )
        else:
            data = list(
                qs.values('date')
                .annotate(wpm=Avg('ending_wpm'))
                .order_by('date')
            )

        result = [
            {
                'date': row['date'].strftime('%Y-%m-%d'),
                'wpm': round(row['wpm'] or 0),
            }
            for row in data
        ]

        return Response({'data': result})


class DocumentStatsView(APIView):
    def get(self, request):
        user = request.user

        sessions = ReadingSession.objects.filter(user=user).select_related('document')
        result = []

        for session in sessions:
            doc = session.document
            logs = DailyReadingLog.objects.filter(user=user, document=doc).aggregate(
                total_reading_time=Sum('reading_time'),
                total_words_read=Sum('words_read'),
                avg_wpm=Avg('ending_wpm'),
            )
            progress = session.current_position / doc.total_words if doc.total_words else 0

            result.append({
                'document_id': doc.id,
                'title': doc.title,
                'total_words': doc.total_words,
                'words_read': logs['total_words_read'] or 0,
                'reading_time': logs['total_reading_time'] or 0,
                'avg_wpm': round(logs['avg_wpm'] or 0),
                'completed_at': session.completed_at,
                'progress': round(progress, 4),
            })

        return Response(result)
