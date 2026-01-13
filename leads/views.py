from __future__ import annotations

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from core.api.responses import ok, fail
from core.utils.context import RequestContext
from leads.models import Lead
from leads.serializers import LeadCreateSerializer, LeadListSerializer, LeadDetailSerializer
from leads.services.leads_service import create_lead
from drf_spectacular.utils import extend_schema
from core.api.exceptions import PermissionDeniedError, ValidationError


from core.api.exceptions import ValidationError, NotFoundError, WorkflowRejectedError
from leads.serializers import (
    LeadAssignCommandSerializer,
    LeadChangeStageCommandSerializer,
    LeadAddTimelineEventCommandSerializer,
)
from leads.services.leads_service import assign_lead, change_stage, add_timeline_event

from django.db.models import Q
from django.utils import timezone

from core.utils.query import parse_int, parse_iso_datetime_or_date
from leads.utils.listing import apply_lead_list_scope



from core.utils.query import parse_int
from leads.utils.security import ensure_can_read_lead
from workflow.models import WorkflowInstance
from workflow.services.read import allowed_next_states
from leads.serializers import LeadTimelineEventSerializer, LeadTaskSerializer, WorkflowEventSerializer
from workflow.models import WorkflowEvent
from leads.models import LeadTimelineEvent, LeadTask

from leads.models import LeadIdentityPoint
from leads.utils.security import ensure_can_read_lead

from leads.serializers import LeadMergeCommandSerializer
from leads.services.leads_service import merge_leads
from core.api.exceptions import PermissionDeniedError


from leads.models import ReasonCode
from leads.serializers import ReasonCodeListSerializer


from leads.models import ScoringRule, ScoreBucket
from leads.serializers import ScoringRuleSerializer, ScoreBucketSerializer


def build_ctx(request) -> RequestContext:
    return RequestContext(
        actor=request.user if request.user.is_authenticated else None,
        request_id=getattr(request, "request_id", ""),
        source="api",
        ip=request.META.get("REMOTE_ADDR", ""),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:256],
    )



class LeadListCreateAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=LeadListSerializer(many=True),
    )
    def get(self, request):
        qs = Lead.objects.filter(is_deleted=False)

        ctx = build_ctx(request)
        qs = apply_lead_list_scope(ctx, qs)

        # ---------- Filters ----------
        stage = (request.query_params.get("stage") or "").strip().upper()
        if stage:
            qs = qs.filter(stage=stage)

        source = (request.query_params.get("source") or "").strip()
        if source:
            qs = qs.filter(source=source)

        do_not_contact = request.query_params.get("do_not_contact")
        if do_not_contact in ["true", "false"]:
            qs = qs.filter(do_not_contact=(do_not_contact == "true"))

        marketing_opt_in = request.query_params.get("marketing_opt_in")
        if marketing_opt_in in ["true", "false"]:
            qs = qs.filter(marketing_opt_in=(marketing_opt_in == "true"))

        owner_id = request.query_params.get("owner_id")
        if owner_id:
            # NOTE: owner_id is integer with default Django User model
            try:
                qs = qs.filter(owner_id=int(owner_id))
            except ValueError:
                return fail(errors=[{"code": "validation_error", "message": "owner_id must be an integer"}], status=400)

        created_from = parse_iso_datetime_or_date(request.query_params.get("created_from"))
        if created_from:
            if timezone.is_naive(created_from):
                created_from = timezone.make_aware(created_from, timezone.get_current_timezone())
            qs = qs.filter(created_at__gte=created_from)

        created_to = parse_iso_datetime_or_date(request.query_params.get("created_to"))
        if created_to:
            if timezone.is_naive(created_to):
                created_to = timezone.make_aware(created_to, timezone.get_current_timezone())
            qs = qs.filter(created_at__lte=created_to)

        # ---------- Search ----------
        q = (request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(full_name__icontains=q)
                | Q(primary_phone__icontains=q)
                | Q(primary_email__icontains=q)
            )

        # ---------- Ordering ----------
        order_by = (request.query_params.get("order_by") or "-created_at").strip()
        allowed = {
            "created_at": "created_at",
            "-created_at": "-created_at",
            "updated_at": "updated_at",
            "-updated_at": "-updated_at",
            "stage": "stage",
            "-stage": "-stage",
        }
        qs = qs.order_by(allowed.get(order_by, "-created_at"))

        # ---------- Pagination ----------
        page = parse_int(request.query_params.get("page"), default=1, min_value=1)
        page_size = parse_int(request.query_params.get("page_size"), default=20, min_value=1, max_value=100)

        total = qs.count()
        start = (page - 1) * page_size
        end = start + page_size
        items = qs[start:end]

        data = LeadListSerializer(items, many=True).data

        return ok(
            data=data,
            meta={
                "page": page,
                "page_size": page_size,
                "total": total,
                "order_by": allowed.get(order_by, "-created_at"),
                "filters": {
                    "stage": stage or None,
                    "source": source or None,
                    "owner_id": int(owner_id) if owner_id and owner_id.isdigit() else None,
                    "do_not_contact": do_not_contact if do_not_contact in ["true", "false"] else None,
                    "marketing_opt_in": marketing_opt_in if marketing_opt_in in ["true", "false"] else None,
                    "created_from": request.query_params.get("created_from"),
                    "created_to": request.query_params.get("created_to"),
                    "q": q or None,
                },
            },
            status=200,
        )


    @extend_schema(
        request=LeadCreateSerializer,                 # ✅ this makes Swagger show fields
        responses=LeadDetailSerializer,               # ✅ response shape
    )
    
    def post(self, request):
        ser = LeadCreateSerializer(data=request.data)
        if not ser.is_valid():
            return fail(
                errors=[{"code": "validation_error", "message": "Invalid payload", "details": ser.errors}],
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            lead_dict = create_lead(build_ctx(request), ser.validated_data)
        except ValidationError as e:
            # ✅ duplicates come here
            return fail(
                errors=[{"code": e.code, "message": e.message, "details": e.details}],
                status=status.HTTP_409_CONFLICT,
            )

        return ok(data=lead_dict, status=status.HTTP_201_CREATED)



class LeadDetailAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=LeadDetailSerializer(many=False),
    )
    def get(self, request, lead_id):
        lead = Lead.objects.filter(id=lead_id, is_deleted=False).first()
        if not lead:
            return fail(errors=[{"code": "not_found", "message": "Lead not found"}], status=404)
        return ok(data=LeadDetailSerializer(lead).data)




class LeadAssignCommandAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LeadAssignCommandSerializer)
    def post(self, request, lead_id):
        ser = LeadAssignCommandSerializer(data=request.data)
        if not ser.is_valid():
            return fail(errors=[{"code": "validation_error", "message": "Invalid payload", "details": ser.errors}], status=400)

        try:
            data = assign_lead(
                        build_ctx(request),
                        lead_id=lead_id,
                        owner_id=ser.validated_data["owner_id"],
                        lock=ser.validated_data.get("lock", True),
                        reason=ser.validated_data.get("reason", ""),
                        override=ser.validated_data.get("override", False),
                        override_reason=ser.validated_data.get("override_reason", ""),
                    )
            return ok(data=data, status=200)
        except NotFoundError as e:
            return fail(errors=[{"code": e.code, "message": e.message, "details": e.details}], status=404)
        except ValidationError as e:
            return fail(errors=[{"code": e.code, "message": e.message, "details": e.details}], status=400)
        
        except PermissionDeniedError as e:
            return fail(errors=[{"code": e.code, "message": e.message, "details": e.details}], status=403)



class LeadChangeStageCommandAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LeadChangeStageCommandSerializer)
    def post(self, request, lead_id):
        ser = LeadChangeStageCommandSerializer(data=request.data)
        if not ser.is_valid():
            return fail(errors=[{"code": "validation_error", "message": "Invalid payload", "details": ser.errors}], status=400)

        print(f'ser.validated_data.get("payload") = {ser.validated_data.get("payload")}')
        print(f'data=request.data = {request.data}') 
        try:
            data = change_stage(
                build_ctx(request),
                lead_id=lead_id,
                action=ser.validated_data["action"],
                to_stage=ser.validated_data["to_stage"],
                payload=ser.validated_data.get("payload") or {},
            )
            return ok(data=data, status=200)
        except NotFoundError as e:
            return fail(errors=[{"code": e.code, "message": e.message, "details": e.details}], status=404)
        except WorkflowRejectedError as e:
            # 422 is perfect for guard/transition rejection
            return fail(errors=[{"code": e.code, "message": e.message, "details": e.details}], status=422)
        except ValidationError as e:
            return fail(errors=[{"code": e.code, "message": e.message, "details": e.details}], status=400)
        
        except PermissionDeniedError as e:
            return fail(errors=[{"code": e.code, "message": e.message, "details": e.details}], status=403)



class LeadAddTimelineEventCommandAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LeadAddTimelineEventCommandSerializer)
    def post(self, request, lead_id):
        ser = LeadAddTimelineEventCommandSerializer(data=request.data)
        if not ser.is_valid():
            return fail(errors=[{"code": "validation_error", "message": "Invalid payload", "details": ser.errors}], status=400)

        try:
            data = add_timeline_event(
                build_ctx(request),
                lead_id=lead_id,
                event_type=ser.validated_data["type"],
                title=ser.validated_data.get("title", ""),
                body=ser.validated_data.get("body", ""),
                payload=ser.validated_data.get("payload") or {},
            )
            return ok(data=data, status=201)
        except NotFoundError as e:
            return fail(errors=[{"code": e.code, "message": e.message, "details": e.details}], status=404)
        
        except PermissionDeniedError as e:
            return fail(errors=[{"code": e.code, "message": e.message, "details": e.details}], status=403)




class ReasonCodeListAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = ReasonCode.objects.filter(is_deleted=False, is_active=True).order_by("type", "code")
        return ok(data=ReasonCodeListSerializer(qs, many=True).data)



class LeadTimelineAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=LeadTimelineEventSerializer(many=True))
    def get(self, request, lead_id):
        lead = Lead.objects.filter(id=lead_id, is_deleted=False).first()
        if not lead:
            return fail(errors=[{"code": "not_found", "message": "Lead not found"}], status=404)

        ctx = build_ctx(request)
        ensure_can_read_lead(ctx, lead)

        page = parse_int(request.query_params.get("page"), default=1, min_value=1)
        page_size = parse_int(request.query_params.get("page_size"), default=20, min_value=1, max_value=100)

        qs = LeadTimelineEvent.objects.filter(lead_id=lead.id, is_deleted=False).order_by("-created_at")
        total = qs.count()
        items = qs[(page - 1) * page_size : (page - 1) * page_size + page_size]

        data = LeadTimelineEventSerializer(items, many=True).data
        return ok(data=data, meta={"page": page, "page_size": page_size, "total": total})


class LeadTasksAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=LeadTaskSerializer(many=True)) 
    def get(self, request, lead_id):
        lead = Lead.objects.filter(id=lead_id, is_deleted=False).first()
        if not lead:
            return fail(errors=[{"code": "not_found", "message": "Lead not found"}], status=404)

        ctx = build_ctx(request)
        ensure_can_read_lead(ctx, lead)

        qs = LeadTask.objects.filter(lead_id=lead.id, is_deleted=False).order_by("-created_at")
        return ok(data=LeadTaskSerializer(qs, many=True).data)



# leads/views.py

from leads.serializers import LeadTaskCreateCommandSerializer, LeadTaskMarkDoneCommandSerializer
from leads.services.leads_service import create_task, mark_task_done

class LeadTaskCreateCommandAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LeadTaskCreateCommandSerializer)
    def post(self, request, lead_id):
        ser = LeadTaskCreateCommandSerializer(data=request.data)
        if not ser.is_valid():
            return fail(errors=[{"code": "validation_error", "message": "Invalid payload", "details": ser.errors}], status=400)

        try:
            data = create_task(
                build_ctx(request),
                lead_id=lead_id,
                title=ser.validated_data["title"],
                due_at=ser.validated_data.get("due_at"),
                assigned_to_id=ser.validated_data.get("assigned_to_id"),
            )
            return ok(data=data, status=201)
        except NotFoundError as e:
            return fail(errors=[{"code": e.code, "message": e.message, "details": e.details}], status=404)
        except ValidationError as e:
            return fail(errors=[{"code": e.code, "message": e.message, "details": e.details}], status=400)


class LeadTaskMarkDoneCommandAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LeadTaskMarkDoneCommandSerializer)
    def post(self, request, lead_id, task_id):
        # We accept lead_id in URL for consistency, even if service finds task by task_id
        ser = LeadTaskMarkDoneCommandSerializer(data=request.data)
        if not ser.is_valid():
             return fail(errors=[{"code": "validation_error", "message": "Invalid payload", "details": ser.errors}], status=400)

        try:
            data = mark_task_done(
                build_ctx(request),
                task_id=task_id,
                note=ser.validated_data.get("note", "")
            )
            return ok(data=data, status=200)
        except NotFoundError as e:
            return fail(errors=[{"code": e.code, "message": e.message, "details": e.details}], status=404)




class LeadWorkflowAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, lead_id):
        lead = Lead.objects.filter(id=lead_id, is_deleted=False).first()
        if not lead:
            return fail(errors=[{"code": "not_found", "message": "Lead not found"}], status=404)

        ctx = build_ctx(request)
        ensure_can_read_lead(ctx, lead)

        instance = WorkflowInstance.objects.filter(entity_type="leads.Lead", entity_id=lead.id).first()
        if not instance:
            # v1: if missing, just return empty (we auto-create on transition anyway)
            return ok(data={"has_instance": False, "state": lead.stage, "events": [], "allowed_next_states": []})

        events = WorkflowEvent.objects.filter(instance=instance).order_by("-created_at")[:50]
        return ok(
            data={
                "has_instance": True,
                "workflow_key": instance.definition.key,
                "workflow_version": instance.definition.version,
                "state": instance.state,
                "allowed_next_states": allowed_next_states(instance),
                "events": WorkflowEventSerializer(events, many=True).data,
            }
        )


class LeadDuplicatesAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, lead_id):
        lead = Lead.objects.filter(id=lead_id, is_deleted=False).first()
        if not lead:
            return fail(errors=[{"code": "not_found", "message": "Lead not found"}], status=404)

        ctx = build_ctx(request)
        ensure_can_read_lead(ctx, lead)

        # get identity points (phone/email)
        points = LeadIdentityPoint.objects.filter(
            lead_id=lead.id,
            is_deleted=False,
            type__in=["phone", "email"],
        ).values_list("type", "value")

        pairs = list(points)
        if not pairs:
            return ok(data=[])

        q = Q()
        for t, v in pairs:
            q |= Q(type=t, value=v)

        dup_lead_ids = (
            LeadIdentityPoint.objects.filter(is_deleted=False)
            .filter(q)
            .exclude(lead_id=lead.id)
            .values_list("lead_id", flat=True)
            .distinct()
        )

        dups = Lead.objects.filter(id__in=dup_lead_ids, is_deleted=False).order_by("-created_at")
        return ok(data=LeadListSerializer(dups, many=True).data)



class LeadMergeCommandAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LeadMergeCommandSerializer)
    def post(self, request, lead_id):
        ser = LeadMergeCommandSerializer(data=request.data)
        if not ser.is_valid():
            return fail(errors=[{"code": "validation_error", "message": "Invalid payload", "details": ser.errors}], status=400)

        try:
            data = merge_leads(
                build_ctx(request),
                primary_lead_id=lead_id,
                secondary_lead_ids=ser.validated_data["secondary_lead_ids"],
                reason=ser.validated_data.get("reason", ""),
            )
            return ok(data=data, status=200)
        except PermissionDeniedError as e:
            return fail(errors=[{"code": e.code, "message": e.message, "details": e.details}], status=403)
        except NotFoundError as e:
            return fail(errors=[{"code": e.code, "message": e.message, "details": e.details}], status=404)
        except ValidationError as e:
            return fail(errors=[{"code": e.code, "message": e.message, "details": e.details}], status=400)



class ScoringRuleListCreateAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=ScoringRuleSerializer(many=True),
        request=ScoringRuleSerializer
    )
    def get(self, request):
        qs = ScoringRule.objects.filter(is_deleted=False).order_by('category', '-points')
        return ok(data=ScoringRuleSerializer(qs, many=True).data)

    @extend_schema(request=ScoringRuleSerializer)
    def post(self, request):
        ser = ScoringRuleSerializer(data=request.data)
        if not ser.is_valid():
            return fail(errors=[{"code": "validation_error", "message": "Invalid payload", "details": ser.errors}], status=400)
        
        # FIX: Removed created_by=request.user
        rule = ser.save() 
        return ok(data=ScoringRuleSerializer(rule).data, status=201)

class ScoringRuleDetailAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ScoringRuleSerializer)
    def put(self, request, rule_id):
        rule = ScoringRule.objects.filter(id=rule_id, is_deleted=False).first()
        if not rule:
            return fail(errors=[{"code": "not_found", "message": "Rule not found"}], status=404)
        
        ser = ScoringRuleSerializer(rule, data=request.data, partial=True)
        if not ser.is_valid():
            return fail(errors=[{"code": "validation_error", "message": "Invalid payload", "details": ser.errors}], status=400)

        # FIX: Removed updated_by=request.user
        rule = ser.save()
        return ok(data=ScoringRuleSerializer(rule).data)

    def delete(self, request, rule_id):
        rule = ScoringRule.objects.filter(id=rule_id, is_deleted=False).first()
        if not rule:
            return fail(errors=[{"code": "not_found", "message": "Rule not found"}], status=404)
        
        # Soft delete doesn't require user if model doesn't support it, 
        # but let's check if soft_delete accepts it. 
        # BaseUUIDModel.soft_delete() usually just sets is_deleted=True.
        rule.soft_delete() 
        return ok(data={"message": "Rule deleted"})


# --- Score Bucket Views (FIXED) ---

class ScoreBucketListCreateAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=ScoreBucketSerializer(many=True),
        request=ScoreBucketSerializer
    )
    def get(self, request):
        qs = ScoreBucket.objects.filter(is_deleted=False).order_by('-min_score')
        return ok(data=ScoreBucketSerializer(qs, many=True).data)

    @extend_schema(request=ScoreBucketSerializer)
    def post(self, request):
        ser = ScoreBucketSerializer(data=request.data)
        if not ser.is_valid():
            return fail(errors=[{"code": "validation_error", "message": "Invalid payload", "details": ser.errors}], status=400)
        
        # FIX: Removed created_by
        bucket = ser.save()
        return ok(data=ScoreBucketSerializer(bucket).data, status=201)

class ScoreBucketDetailAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ScoreBucketSerializer)
    def put(self, request, bucket_id):
        bucket = ScoreBucket.objects.filter(id=bucket_id, is_deleted=False).first()
        if not bucket:
            return fail(errors=[{"code": "not_found", "message": "Bucket not found"}], status=404)
        
        ser = ScoreBucketSerializer(bucket, data=request.data, partial=True)
        if not ser.is_valid():
            return fail(errors=[{"code": "validation_error", "message": "Invalid payload", "details": ser.errors}], status=400)

        # FIX: Removed updated_by
        bucket = ser.save()
        return ok(data=ScoreBucketSerializer(bucket).data)

    def delete(self, request, bucket_id):
        bucket = ScoreBucket.objects.filter(id=bucket_id, is_deleted=False).first()
        if not bucket:
            return fail(errors=[{"code": "not_found", "message": "Bucket not found"}], status=404)
        
        bucket.soft_delete()
        return ok(data={"message": "Bucket deleted"})
  
  
    
# ... existing imports ...
from leads.serializers import (
    CallLogSerializer, CallLogCreateSerializer,
    SiteVisitSerializer, SiteVisitCreateSerializer, SiteVisitUpdateSerializer
)
from leads.services.interaction_service import log_call, schedule_site_visit, update_site_visit
from leads.models import CallLog, SiteVisit

class LeadCallLogListCreateAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=CallLogSerializer(many=True))
    def get(self, request, lead_id):
        # List calls for a lead
        qs = CallLog.objects.filter(lead_id=lead_id).order_by('-created_at')
        return ok(data=CallLogSerializer(qs, many=True).data)

    @extend_schema(request=CallLogCreateSerializer)
    def post(self, request, lead_id):
        ser = CallLogCreateSerializer(data=request.data)
        if not ser.is_valid():
            return fail(errors=[{"code": "validation_error", "message": "Invalid payload", "details": ser.errors}], status=400)
        
        try:
            data = log_call(build_ctx(request), lead_id, ser.validated_data)
            return ok(data=data, status=201)
        except NotFoundError as e:
            return fail(errors=[{"code": "not_found", "message": e.message}], status=404)
        except PermissionDeniedError as e:
            return fail(errors=[{"code": "forbidden", "message": e.message}], status=403)

class LeadSiteVisitListCreateAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=SiteVisitSerializer(many=True))
    def get(self, request, lead_id):
        qs = SiteVisit.objects.filter(lead_id=lead_id).order_by('-scheduled_at')
        return ok(data=SiteVisitSerializer(qs, many=True).data)

    @extend_schema(request=SiteVisitCreateSerializer)
    def post(self, request, lead_id):
        ser = SiteVisitCreateSerializer(data=request.data)
        if not ser.is_valid():
            return fail(errors=[{"code": "validation_error", "message": "Invalid payload", "details": ser.errors}], status=400)
        
        try:
            data = schedule_site_visit(build_ctx(request), lead_id, ser.validated_data)
            return ok(data=data, status=201)
        except NotFoundError as e:
            return fail(errors=[{"code": "not_found", "message": e.message}], status=404)
        except PermissionDeniedError as e:
            return fail(errors=[{"code": "forbidden", "message": e.message}], status=403)

class LeadSiteVisitDetailAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=SiteVisitUpdateSerializer)
    def patch(self, request, lead_id, visit_id):
        ser = SiteVisitUpdateSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return fail(errors=[{"code": "validation_error", "message": "Invalid payload", "details": ser.errors}], status=400)
        
        try:
            data = update_site_visit(build_ctx(request), lead_id, visit_id, ser.validated_data)
            return ok(data=data)
        except NotFoundError as e:
            return fail(errors=[{"code": "not_found", "message": e.message}], status=404)
        except PermissionDeniedError as e:
            return fail(errors=[{"code": "forbidden", "message": e.message}], status=403)
 
 
 
 # leads/views.py

from drf_spectacular.utils import extend_schema
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from core.api.responses import ok, fail
from core.utils.context import build_ctx
from leads.models import ImportBatch
from leads.services.import_service import process_import_batch
from core.api.exceptions import PermissionDeniedError

class LeadImportAPI(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser] # <--- Vital for handling files

    @extend_schema(
        summary="Bulk Import Leads",
        description="Upload an Excel (.xlsx) or CSV file to create leads in bulk.",
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'file': {
                        'type': 'string',
                        'format': 'binary'
                    }
                }
            }
        },
        responses={
            200: {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "data": {
                        "type": "object",
                        "properties": {
                            "batch_id": {"type": "string"},
                            "status": {"type": "string"},
                            "summary": {"type": "object"}
                        }
                    }
                }
            }
        }
    )
    def post(self, request):
        if 'file' not in request.FILES:
            return fail(errors=[{"code": "missing_file", "message": "No file uploaded"}], status=400)
            
        file_obj = request.FILES['file']
        
        if not (file_obj.name.endswith('.csv') or file_obj.name.endswith('.xlsx')):
             return fail(errors=[{"code": "invalid_format", "message": "Only .csv or .xlsx allowed"}], status=400)

        try:
            batch = ImportBatch.objects.create(
                uploaded_by=request.user,
                file=file_obj,
                status='PENDING'
            )
            
            results = process_import_batch(build_ctx(request), str(batch.id))
            
            return ok(data={
                "batch_id": str(batch.id),
                "status": batch.status,
                "summary": results
            })
            
        except PermissionDeniedError as e:
            return fail(errors=[{"code": e.code, "message": e.message}], status=403)
        except Exception as e:
            return fail(errors=[{"code": "import_error", "message": str(e)}], status=500)       
        




# leads/views.py

from django.conf import settings
from rest_framework.response import Response
from rest_framework import status
from leads.services.webhook_service import handle_facebook_webhook

class FacebookWebhookAPI(APIView):
    permission_classes = [] # Public Endpoint!
    authentication_classes = [] # No Session Auth!

    def get(self, request):
        """
        Facebook Verification Challenge.
        FB sends a GET request to verify we own the server.
        """
        mode = request.query_params.get('hub.mode')
        token = request.query_params.get('hub.verify_token')
        challenge = request.query_params.get('hub.challenge')

        if mode and token:
            if mode == 'subscribe' and token == settings.WEBHOOK_VERIFY_TOKEN:
                # Respond with the challenge to confirm validity
                return Response(int(challenge), status=status.HTTP_200_OK)
            else:
                return Response(status=status.HTTP_403_FORBIDDEN)
        
        return Response(status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        """
        Receive Lead Data.
        """
        # In a real scenario, you verify X-Hub-Signature header here.
        # For this test, we trust the payload structure.
        
        try:
            # We assume a simplified structure for this mock
            # { "object": "page", "entry": [ ... ] }
            data = request.data
            
            # Simple extraction loop to find lead data in the mock payload
            if 'entry' in data:
                for entry in data['entry']:
                    for change in entry.get('changes', []):
                        if change.get('value'):
                            # Process using our service
                            # We create a System Context since there is no user
                            sys_ctx = build_ctx(request) 
                            handle_facebook_webhook(sys_ctx, change['value'])
            
            return Response({"status": "received"}, status=status.HTTP_200_OK)

        except Exception as e:
            # Always return 200 to Facebook/Provider so they don't retry endlessly
            # But log the error internally
            print(f"Webhook Error: {str(e)}")
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_200_OK)