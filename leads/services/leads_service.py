from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from django.db import transaction
from django.utils import timezone

from audit.utils.recorder import record as audit_record
from core.utils.context import RequestContext
from leads.models import Lead, LeadIdentityPoint, ReasonCode
from workflow.models import WorkflowInstance
from workflow.services.engine import create_instance

from core.api.exceptions import ValidationError


from django.contrib.auth import get_user_model
from core.api.exceptions import NotFoundError, ValidationError, WorkflowRejectedError
from workflow.services.engine import transition
from leads.models import LeadTimelineEvent


from core.api.exceptions import PermissionDeniedError
from leads.utils.security import ensure_can_assign, ensure_can_transition, ensure_can_add_timeline
from leads.utils.security import ensure_can_merge

from leads.models import Lead, LeadIdentityPoint, LeadTimelineEvent, LeadTask
from leads.services.routing_service import route_lead
from leads.services.scoring_service import run_scoring_engine 


LEAD_ENTITY_TYPE = "leads.Lead"
LEAD_WORKFLOW_KEY = "lead_lifecycle"
 

def _lead_to_dict(lead: Lead) -> Dict[str, Any]:
    return {
        "id": str(lead.id),
        "full_name": lead.full_name,
        "primary_phone": lead.primary_phone,
        "primary_email": lead.primary_email,
        "source": lead.source,
        "medium": lead.medium,
        "campaign": lead.campaign,
        "stage": lead.stage,
        "score_bucket": lead.score_bucket,
        "qualification": lead.qualification,
        "marketing_opt_in": lead.marketing_opt_in,
        "do_not_contact": lead.do_not_contact,
        "owner_id": str(lead.owner_id) if lead.owner_id else None,
        "created_at": lead.created_at.isoformat(),
        "updated_at": lead.updated_at.isoformat(),
    }


@transaction.atomic
def create_lead(
    ctx: RequestContext,
    payload: Dict[str, Any],
    *,
    allow_duplicates: bool = False,
) -> Dict[str, Any]:

    # --- 1. Validation & Identity Checks (Existing Code) ---
    phone = (payload.get("primary_phone") or "").strip()
    email = (payload.get("primary_email") or "").strip()

    if phone and not allow_duplicates:
        existing = LeadIdentityPoint.objects.filter(
            type="phone", value=phone, is_deleted=False
        ).select_related("lead").first()
        if existing and not existing.lead.is_deleted:
             raise ValidationError(
                code="lead.duplicate_identity",
                message="A lead with this phone already exists.",
                details={"type": "phone", "value": phone, "existing_lead_id": str(existing.lead_id)},
            )

    if email:
        existing = LeadIdentityPoint.objects.filter(type="email", value=email, is_deleted=False).select_related("lead").first()
        if existing and not existing.lead.is_deleted:
            raise ValidationError(
                code="lead.duplicate_identity",
                message="A lead with this email already exists.",
                details={"type": "email", "value": email, "existing_lead_id": str(existing.lead_id)},
            )

    # --- 2. Create Lead Object ---
    lead = Lead.objects.create(
        full_name=(payload.get("full_name") or "").strip(),
        primary_phone=phone,
        primary_email=email,
        source=(payload.get("source") or "").strip(),
        medium=(payload.get("medium") or "").strip(),
        campaign=(payload.get("campaign") or "").strip(),
        marketing_opt_in=payload.get("marketing_opt_in", True),
        do_not_contact=payload.get("do_not_contact", False),
        
        # ✅ Ensure these fields are saved so Routing can use them
        score_bucket=payload.get("score_bucket", "COLD"), 
        qualification=payload.get("qualification", {}),
        
        stage="NEW",
        first_response_due_at=timezone.now() + timezone.timedelta(minutes=30), # Default fallback
    )

    # --- 3. Create Identity Points ---
    if lead.primary_phone:
        LeadIdentityPoint.objects.create(lead=lead, type="phone", value=lead.primary_phone, is_primary=True)
    if lead.primary_email:
        LeadIdentityPoint.objects.create(lead=lead, type="email", value=lead.primary_email, is_primary=True)

    # --- 4. ⚡ EXECUTE ROUTING ENGINE (The Missing Piece) ---
    # Only route if no owner was manually assigned during creation
    if not lead.owner_id:
        route_lead(ctx, lead) 
        
        lead.refresh_from_db()
        # Note: route_lead calls .save() internally if it finds a match

    # This ensures every new lead starts with a Score and Next Best Action
    run_scoring_engine(lead)
    
    # --- 5. Workflow & Audit (The Rest of the Function) ---
    # Ensure this part is NOT deleted
    instance = _get_or_create_workflow_instance(ctx, lead)
    
    audit_record(
        ctx=ctx,
        action="lead.created",
        entity_type=LEAD_ENTITY_TYPE,
        entity_id=lead.id,
        message="Lead created",
        before=None,
        after=_lead_to_dict(lead),
        metadata=payload
    )

    return _lead_to_dict(lead)

User = get_user_model()


def _get_lead_or_raise(lead_id) -> Lead:
    lead = Lead.objects.filter(id=lead_id, is_deleted=False).first()
    if not lead:
        raise NotFoundError(code="lead.not_found", message="Lead not found", details={"lead_id": str(lead_id)})
    return lead


def _get_or_create_workflow_instance(ctx: RequestContext, lead: Lead):
    instance = WorkflowInstance.objects.filter(entity_type=LEAD_ENTITY_TYPE, entity_id=lead.id).first()
    if instance:
        return instance

    # self-heal: create workflow instance using current lead.stage as initial state
    result = create_instance(
        ctx=ctx,
        workflow_key=LEAD_WORKFLOW_KEY,
        entity_type=LEAD_ENTITY_TYPE,
        entity_id=lead.id,
        initial_state=(lead.stage or "NEW"),
        payload={"note": "Auto-created workflow instance for existing lead"},
    )

    # audit the recovery
    audit_record(
        ctx=ctx,
        action="workflow.instance_auto_created",
        entity_type=LEAD_ENTITY_TYPE,
        entity_id=lead.id,
        message="Workflow instance auto-created for lead",
        before=_lead_to_dict(lead),
        after=_lead_to_dict(lead),
        metadata={"workflow_instance_id": str(result.instance.id), "workflow_event_id": str(result.event.id)},
    )

    return result.instance



@transaction.atomic
def assign_lead(
    ctx: RequestContext,
    lead_id,
    owner_id,
    lock: bool = True,
    reason: str = "",
    override: bool = False,
    override_reason: str = "",
) -> Dict[str, Any]:
    
    ensure_can_assign(ctx)

    lead = _get_lead_or_raise(lead_id)

    # locked-lead rule
    if lead.locked and not override:
        raise ValidationError(
            code="lead.assign.locked",
            message="Lead is locked. Override is required to reassign.",
            details={"lead_id": str(lead.id)},
        )

    if lead.locked and override and not (override_reason or "").strip():
        raise ValidationError(
            code="lead.assign.override_reason_required",
            message="override_reason is required when overriding a locked lead.",
            details={"lead_id": str(lead.id)},
        )

    owner = User.objects.filter(id=owner_id, is_active=True).first()
    if not owner:
        raise ValidationError(
            code="lead.assign.invalid_owner",
            message="Owner user not found or inactive",
            details={"owner_id": str(owner_id)},
        )

    before = _lead_to_dict(lead)

    lead.owner = owner

    # locking behavior
    if lock and not lead.locked:
        lead.locked = True
        lead.locked_at = timezone.now()

    lead.save(update_fields=["owner", "locked", "locked_at", "updated_at"])

    after = _lead_to_dict(lead)

    audit_record(
        ctx=ctx,
        action="lead.assigned",
        entity_type=LEAD_ENTITY_TYPE,
        entity_id=lead.id,
        message="Lead assigned",
        before=before,
        after=after,
        metadata={
            "owner_id": str(owner_id),
            "lock": lock,
            "reason": reason,
            "override": override,
            "override_reason": override_reason,
        },
    )

    return after



@transaction.atomic
def change_stage(ctx: RequestContext, lead_id, action: str, to_stage: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    lead = _get_lead_or_raise(lead_id)
    ensure_can_transition(ctx, lead)
    instance = _get_or_create_workflow_instance(ctx, lead)

 
    before = _lead_to_dict(lead)
    
    payload = _validate_reason_code_for_terminal(to_stage, payload or {})

    # Workflow transition (guards enforced inside engine.transition)
    result = transition(
                ctx=ctx,
                instance=instance,
                action=action.strip(),
                to_state=to_stage.strip().upper(),
                payload=payload,
            )

    # Mirror stage for fast filtering
    lead.stage = result.instance.state

    # Business effects based on stage
    if lead.stage == "CONTACTED" and not lead.first_contact_at:
        lead.first_contact_at = timezone.now()

    lead.save(update_fields=["stage", "first_contact_at", "updated_at"])

    after = _lead_to_dict(lead)

    audit_record(
        ctx=ctx,
        action="lead.stage_changed",
        entity_type=LEAD_ENTITY_TYPE,
        entity_id=lead.id,
        message=f"Lead stage changed to {lead.stage}",
        before=before,
        after=after,
        metadata={
            "workflow_instance_id": str(result.instance.id),
            "workflow_event_id": str(result.event.id),
            "from": result.event.from_state,
            "to": result.event.to_state,
            "action": action,
            "payload": payload or {},
        },
    )

    return after


@transaction.atomic
def add_timeline_event(
    ctx: RequestContext,
    lead_id,
    event_type: str,
    title: str = "",
    body: str = "",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    lead = _get_lead_or_raise(lead_id)
    ensure_can_add_timeline(ctx, lead)
    before = _lead_to_dict(lead)

    ev = LeadTimelineEvent.objects.create(
        lead=lead,
        type=event_type,
        title=title or "",
        body=body or "",
        payload=payload or {},
        actor=ctx.actor,
    )

    audit_record(
        ctx=ctx,
        action="lead.timeline_added",
        entity_type=LEAD_ENTITY_TYPE,
        entity_id=lead.id,
        message="Timeline event added",
        before=before,
        after=before,  # lead fields unchanged; timeline is separate
        metadata={
            "timeline_event_id": str(ev.id),
            "type": ev.type,
            "title": ev.title,
        },
    )

    return {
        "timeline_event": {
            "id": str(ev.id),
            "created_at": ev.created_at.isoformat(),
            "type": ev.type,
            "title": ev.title,
            "body": ev.body,
            "payload": ev.payload,
            "actor_id": str(ev.actor_id) if ev.actor_id else None,
        }
    }


def get_lead(lead_id) -> Lead:
    return Lead.objects.get(id=lead_id)


def get_workflow_instance_for_lead(lead: Lead) -> Optional[WorkflowInstance]:
    return WorkflowInstance.objects.filter(entity_type=LEAD_ENTITY_TYPE, entity_id=lead.id).first()


def _validate_reason_code_for_terminal(to_stage: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    If to_stage is LOST or DO_NOT_PURSUE, ensure payload.reason_code exists in ReasonCode table and is active.
    Adds reason_label to payload for convenience.
    """
    stage = (to_stage or "").strip().upper()
    if stage not in ["LOST", "DO_NOT_PURSUE"]:
        return payload

    reason_code = (payload or {}).get("reason_code")
    if not reason_code or str(reason_code).strip() == "":
        raise ValidationError(
            code="lead.reason_code.required",
            message="reason_code is required for terminal stage",
            details={"to_stage": stage},
        )

    rc = ReasonCode.objects.filter(code=reason_code, type=stage, is_active=True, is_deleted=False).first()
    if not rc:
        raise ValidationError(
            code="lead.reason_code.invalid",
            message="Invalid or inactive reason_code",
            details={"to_stage": stage, "reason_code": reason_code},
        )

    new_payload = dict(payload or {})
    new_payload["reason_label"] = rc.label
    return new_payload


@transaction.atomic
def merge_leads(ctx: RequestContext, primary_lead_id, secondary_lead_ids, reason: str = "") -> Dict[str, Any]:
    ensure_can_merge(ctx)

    primary = _get_lead_or_raise(primary_lead_id)

    # prevent self-merge
    secondary_lead_ids = [sid for sid in secondary_lead_ids if str(sid) != str(primary.id)]
    if not secondary_lead_ids:
        raise ValidationError(
            code="lead.merge.no_secondaries",
            message="No valid secondary leads provided",
            details={"primary_lead_id": str(primary.id)},
        )

    secondaries = list(Lead.objects.filter(id__in=secondary_lead_ids, is_deleted=False))
    if len(secondaries) != len(secondary_lead_ids):
        existing_ids = {str(x.id) for x in secondaries}
        missing = [str(x) for x in secondary_lead_ids if str(x) not in existing_ids]
        raise ValidationError(
            code="lead.merge.secondary_not_found",
            message="One or more secondary leads not found",
            details={"missing_secondary_ids": missing},
        )

    before_primary = _lead_to_dict(primary)
    merged_ids = [str(s.id) for s in secondaries]

    # ---- Field merge rule (v1) ----
    # Primary wins; fill blanks from secondary in order.
    for s in secondaries:
        if not primary.full_name and s.full_name:
            primary.full_name = s.full_name

        if not primary.primary_phone and s.primary_phone:
            primary.primary_phone = s.primary_phone

        if not primary.primary_email and s.primary_email:
            primary.primary_email = s.primary_email

        if not primary.source and s.source:
            primary.source = s.source

        if not primary.campaign and s.campaign:
            primary.campaign = s.campaign

        # qualification: if primary empty, take secondary
        if (primary.qualification is None) and (s.qualification is not None):
            primary.qualification = s.qualification

        # respect DNC/consent (more restrictive wins)
        primary.do_not_contact = bool(primary.do_not_contact or s.do_not_contact)
        primary.marketing_opt_in = bool(primary.marketing_opt_in and s.marketing_opt_in)

    primary.save(update_fields=[
        "full_name", "primary_phone", "primary_email",
        "source", "campaign",
        "qualification", "do_not_contact", "marketing_opt_in",
        "updated_at",
    ])

    # ---- Move identity points (skip duplicates to avoid unique constraint issues) ----
    existing_points = set(
        LeadIdentityPoint.objects.filter(lead=primary, is_deleted=False).values_list("type", "value")
    )

    for s in secondaries:
        points = LeadIdentityPoint.objects.filter(lead=s, is_deleted=False)
        for p in points:
            key = (p.type, p.value)
            if key in existing_points:
                # if already exists on primary, just soft-delete the secondary identity point
                p.soft_delete()
                continue
            p.lead = primary
            p.is_primary = False
            p.save(update_fields=["lead", "is_primary", "updated_at"])
            existing_points.add(key)

    # ---- Move tasks ----
    LeadTask.objects.filter(lead__in=secondaries, is_deleted=False).update(lead=primary)

    # ---- Move timeline events ----
    LeadTimelineEvent.objects.filter(lead__in=secondaries, is_deleted=False).update(lead=primary)

    # ---- Soft delete secondary leads ----
    for s in secondaries:
        s.soft_delete()

    after_primary = _lead_to_dict(primary)

    # ---- System timeline event on primary ----
    LeadTimelineEvent.objects.create(
        lead=primary,
        type="system",
        title="Leads merged",
        body=f"Merged leads into this lead: {', '.join(merged_ids)}",
        payload={"merged_lead_ids": merged_ids, "reason": reason},
        actor=ctx.actor,
    )

    # ---- Audit event ----
    audit_record(
        ctx=ctx,
        action="lead.merged",
        entity_type=LEAD_ENTITY_TYPE,
        entity_id=primary.id,
        message="Leads merged",
        before=before_primary,
        after=after_primary,
        metadata={"primary_lead_id": str(primary.id), "merged_lead_ids": merged_ids, "reason": reason},
    )

    return {
        "primary": after_primary,
        "merged_lead_ids": merged_ids,
    }


# leads/services/leads_service.py

from leads.models import LeadTask
# Ensure LeadTask is imported at the top

@transaction.atomic
def create_task(
    ctx: RequestContext,
    lead_id,
    title: str,
    due_at: Optional[datetime] = None,
    assigned_to_id: Optional[int] = None,
) -> Dict[str, Any]:
    # 1. Get Lead
    lead = _get_lead_or_raise(lead_id)
    
    # 2. Validate User (if assigned)
    assigned_user = None
    if assigned_to_id:
        assigned_user = User.objects.filter(id=assigned_to_id, is_active=True).first()
        if not assigned_user:
            raise ValidationError(
                code="task.assign.invalid_user",
                message="Assigned user not found or inactive",
                details={"assigned_to_id": assigned_to_id}
            )
    else:
        # Default assignment: The creator (actor) implies ownership, or leave null.
        # Strategy: If no one specified, assign to the actor.
        assigned_user = ctx.actor

    # 3. Create
    task = LeadTask.objects.create(
        lead=lead,
        title=title,
        due_at=due_at,
        assigned_to=assigned_user,
        status="open",
    )

    # 4. Audit
    audit_record(
        ctx=ctx,
        action="lead.task_created",
        entity_type=LEAD_ENTITY_TYPE,
        entity_id=lead.id,
        message=f"Task created: {title}",
        before=None,
        after={
            "task_id": str(task.id),
            "title": task.title,
            "status": task.status,
            "assigned_to_id": str(task.assigned_to_id) if task.assigned_to_id else None
        },
        metadata={"due_at": str(due_at) if due_at else None}
    )

    return {
        "id": str(task.id),
        "title": task.title,
        "status": task.status,
        "created_at": task.created_at.isoformat(),
        "assigned_to_id": str(task.assigned_to_id) if task.assigned_to_id else None,
    }

@transaction.atomic
def mark_task_done(ctx: RequestContext, task_id, note: str = "") -> Dict[str, Any]:
    # 1. Find Task
    task = LeadTask.objects.filter(id=task_id).select_related("lead").first()
    if not task:
        raise NotFoundError(code="task.not_found", message="Task not found", details={"task_id": str(task_id)})

    if task.status == "done":
        return {"id": str(task.id), "status": "done", "completed_at": str(task.completed_at)}

    # 2. Execute Logic
    task.mark_done()

    # 3. Audit
    audit_record(
        ctx=ctx,
        action="lead.task_completed",
        entity_type=LEAD_ENTITY_TYPE,
        entity_id=task.lead_id,
        message=f"Task completed: {task.title}",
        before={"status": "open"},
        after={"status": "done", "completed_at": str(task.completed_at)},
        metadata={"task_id": str(task.id), "note": note}
    )

    return {
        "id": str(task.id),
        "status": task.status,
        "completed_at": task.completed_at.isoformat()
    }