from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from core.api.responses import ok, fail
from core.utils.context import build_ctx  # Assuming you have this helper, or reimplement
from core.utils.query import parse_iso_datetime_or_date

from analytics.services import get_agent_performance, get_pipeline_stats, get_response_metrics, get_lost_analysis,get_daily_leaderboard, get_stage_aging_analysis
from core.api.exceptions import PermissionDeniedError

def build_ctx_helper(request):
    # Quick helper if not imported
    from core.utils.context import RequestContext
    return RequestContext(
        actor=request.user,
        request_id="analytics",
        source="api",
        ip=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT')
    )

class AgentPerformanceAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from = parse_iso_datetime_or_date(request.query_params.get('date_from'))
        date_to = parse_iso_datetime_or_date(request.query_params.get('date_to'))
        
        try:
            data = get_agent_performance(build_ctx_helper(request), date_from, date_to)
            return ok(data=data)
        except PermissionDeniedError as e:
            return fail(errors=[{"code": e.code, "message": e.message}], status=403)

class PipelineStatsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            data = get_pipeline_stats(build_ctx_helper(request))
            return ok(data=data)
        except PermissionDeniedError as e:
            return fail(errors=[{"code": e.code, "message": e.message}], status=403)

class ResponseMetricsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from = parse_iso_datetime_or_date(request.query_params.get('date_from'))
        date_to = parse_iso_datetime_or_date(request.query_params.get('date_to'))

        try:
            data = get_response_metrics(build_ctx_helper(request), date_from, date_to)
            return ok(data=data)
        except PermissionDeniedError as e:
            return fail(errors=[{"code": e.code, "message": e.message}], status=403)
        
        
        
class LostAnalysisAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from = parse_iso_datetime_or_date(request.query_params.get('date_from'))
        date_to = parse_iso_datetime_or_date(request.query_params.get('date_to'))

        try:
            data = get_lost_analysis(build_ctx(request), date_from, date_to)
            return ok(data=data)
        except PermissionDeniedError as e:
            return fail(errors=[{"code": e.code, "message": e.message}], status=403)
        
        

class DailyLeaderboardAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_str = request.query_params.get('date')
        target_date = parse_iso_datetime_or_date(date_str)
        
        try:
            data = get_daily_leaderboard(build_ctx(request), target_date)
            return ok(data=data)
        except PermissionDeniedError as e:
            return fail(errors=[{"code": e.code, "message": e.message}], status=403)

class BottleneckAnalysisAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            data = get_stage_aging_analysis(build_ctx(request))
            return ok(data=data)
        except PermissionDeniedError as e:
            return fail(errors=[{"code": e.code, "message": e.message}], status=403)