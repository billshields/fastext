from django.urls import path
from . import views

urlpatterns = [
    path('stats/overview/', views.StatsOverviewView.as_view(), name='stats-overview'),
    path('stats/reading-time/', views.ReadingTimeView.as_view(), name='stats-reading-time'),
    path('stats/wpm-history/', views.WpmHistoryView.as_view(), name='stats-wpm-history'),
    path('stats/documents/', views.DocumentStatsView.as_view(), name='stats-documents'),
]
