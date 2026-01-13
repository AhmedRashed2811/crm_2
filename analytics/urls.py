from django.urls import path
from .views import AgentPerformanceAPI, PipelineStatsAPI, ResponseMetricsAPI, LostAnalysisAPI,DailyLeaderboardAPI, BottleneckAnalysisAPI

urlpatterns = [
    path('v1/analytics/performance/', AgentPerformanceAPI.as_view(), name='analytics_performance'),
    path('v1/analytics/pipeline/', PipelineStatsAPI.as_view(), name='analytics_pipeline'),
    path('v1/analytics/efficiency/', ResponseMetricsAPI.as_view(), name='analytics_efficiency'),
    path('v1/analytics/lost-reasons/', LostAnalysisAPI.as_view(), name='analytics_lost_reasons'),
    
    path('v1/analytics/leaderboard/', DailyLeaderboardAPI.as_view(), name='analytics_leaderboard'),
    path('v1/analytics/bottlenecks/', BottleneckAnalysisAPI.as_view(), name='analytics_bottlenecks'),
]