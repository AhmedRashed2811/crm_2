from __future__ import annotations

from rest_framework import serializers
from .models import Lead, LeadTimelineEvent, LeadTask, ScoringRule, ScoreBucket
from core.api.exceptions import PermissionDeniedError
from leads.utils.security import ensure_can_assign, ensure_can_transition, ensure_can_add_timeline


 
class LeadCreateSerializer(serializers.Serializer):
    full_name = serializers.CharField(required=False, allow_blank=True)
    primary_phone = serializers.CharField(required=False, allow_blank=True)
    primary_email = serializers.EmailField(required=False, allow_blank=True)

    source = serializers.CharField(required=False, allow_blank=True)
    medium = serializers.CharField(required=False, allow_blank=True)
    campaign = serializers.CharField(required=False, allow_blank=True)

    marketing_opt_in = serializers.BooleanField(required=False)
    do_not_contact = serializers.BooleanField(required=False)

    score_bucket = serializers.CharField(required=False, allow_blank=True)
    
    # v1: allow passing qualification payload
    qualification = serializers.JSONField(required=False)
    
    

    def validate(self, attrs):
        phone = (attrs.get("primary_phone") or "").strip()
        email = (attrs.get("primary_email") or "").strip()

        if not phone and not email:
            raise serializers.ValidationError("Either primary_phone or primary_email is required.")
        return attrs


class LeadListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = [
            "id",
            "full_name",
            "primary_phone",
            "primary_email",
            "source",
            "medium",
            "campaign",
            "stage",
            "score_bucket",
            "created_at",
            "updated_at",
        ]


class LeadDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = "__all__"




class LeadAssignCommandSerializer(serializers.Serializer):
    owner_id = serializers.IntegerField(required=True)  # keep integer for default Django user
    lock = serializers.BooleanField(required=False, default=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="")

    override = serializers.BooleanField(required=False, default=False)
    override_reason = serializers.CharField(required=False, allow_blank=True, default="")



class LeadChangeStageCommandSerializer(serializers.Serializer):
    to_stage = serializers.CharField(required=True)      # NEW/CONTACTED/QUALIFYING/...
    action = serializers.CharField(required=True)        # contact/start_qualifying/qualify/...
    payload = serializers.JSONField(required=False)      # may include reason_code, project_interest, etc.

    def validate_to_stage(self, v):
        return v.strip().upper()

class LeadAddTimelineEventCommandSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["note", "call", "whatsapp", "email", "sms", "meeting", "system"])
    title = serializers.CharField(required=False, allow_blank=True, default="")
    body = serializers.CharField(required=False, allow_blank=True, default="")
    payload = serializers.JSONField(required=False)



from .models import ReasonCode

class ReasonCodeListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReasonCode
        fields = ["id", "type", "code", "label", "is_active"]



from .models import LeadTimelineEvent, LeadTask
from workflow.models import WorkflowEvent, WorkflowInstance


class LeadTimelineEventSerializer(serializers.ModelSerializer):
    actor_id = serializers.SerializerMethodField()

    class Meta:
        model = LeadTimelineEvent
        fields = ["id", "created_at", "type", "title", "body", "payload", "actor_id"]

    def get_actor_id(self, obj):
        return str(obj.actor_id) if obj.actor_id else None


class LeadTaskSerializer(serializers.ModelSerializer):
    assigned_to_id = serializers.SerializerMethodField()

    class Meta:
        model = LeadTask
        fields = ["id", "created_at", "updated_at", "title", "status", "due_at", "completed_at", "assigned_to_id"]

    def get_assigned_to_id(self, obj):
        return str(obj.assigned_to_id) if obj.assigned_to_id else None


class LeadTaskCreateCommandSerializer(serializers.Serializer):
    title = serializers.CharField(required=True, max_length=160)
    due_at = serializers.DateTimeField(required=False, allow_null=True)
    assigned_to_id = serializers.IntegerField(required=False, allow_null=True)  # Optional: assign immediately
    

class LeadTaskMarkDoneCommandSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")
    
     

class WorkflowEventSerializer(serializers.ModelSerializer):
    actor_id = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowEvent
        fields = ["id", "created_at", "action", "from_state", "to_state", "payload", "actor_id", "request_id"]

    def get_actor_id(self, obj):
        return str(obj.actor_id) if obj.actor_id else None

class LeadMergeCommandSerializer(serializers.Serializer):
    secondary_lead_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        required=True,
    )
    reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_secondary_lead_ids(self, ids):
        unique_ids = list(dict.fromkeys(ids))
        return unique_ids
    
    
    
class ScoringRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScoringRule
        fields = [
            'id', 'name', 'category', 'keyword', 
            'match_type', 'points', 'is_active'
        ]

class ScoreBucketSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScoreBucket
        fields = ['id', 'name', 'min_score', 'priority', 'color']