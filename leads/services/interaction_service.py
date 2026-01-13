from django.utils import timezone
from django.db import transaction
from core.api.exceptions import NotFoundError, ValidationError
from core.utils.context import RequestContext
from leads.models import Lead, CallLog, SiteVisit
from leads.utils.security import ensure_can_update_lead
from leads.services.leads_service import add_timeline_event, change_stage
from audit.utils.recorder import record as audit_record

LEAD_ENTITY_TYPE = "leads.Lead"

def log_call(ctx: RequestContext, lead_id: str, payload: dict) -> dict:
    """
    Logs a call, updates Timeline, and potentially auto-moves stage.
    """
    lead = Lead.objects.filter(id=lead_id, is_deleted=False).first()
    if not lead:
        raise NotFoundError(message="Lead not found")
    
    ensure_can_update_lead(ctx, lead)

    with transaction.atomic():
        # 1. Create Log
        call = CallLog.objects.create(
            lead=lead,
            actor=ctx.actor,
            direction=payload.get('direction', 'OUTBOUND'),
            outcome=payload['outcome'],
            duration=payload['duration'],
            note=payload.get('note', ''),
            recording_url=payload.get('recording_url')
        )

        # 2. Update Lead Timestamps
        now = timezone.now()
        # Update last_contacted_at if the field exists on the model
        if hasattr(lead, 'last_contacted_at'):
            lead.last_contacted_at = now
        
        if not lead.first_contact_at:
            lead.first_contact_at = now
            
        update_fields = ['first_contact_at']
        if hasattr(lead, 'last_contacted_at'):
            update_fields.append('last_contacted_at')
        lead.save(update_fields=update_fields) 

        # 3. Create Unified Timeline Event
        add_timeline_event(
            ctx, 
            lead_id=lead.id, 
            event_type="call", 
            title=f"Call {call.get_outcome_display()}",
            body=call.note,
            payload={
                "call_log_id": str(call.id),
                "duration": call.duration,
                "outcome": call.outcome
            }
        )

        # 4. Automation: Auto-move to CONTACTED if answered and currently NEW
        if call.outcome == 'ANSWERED' and lead.stage == 'NEW':
            try:
                change_stage(ctx, lead.id, action='contact', to_stage='CONTACTED')
            except Exception:
                pass 

        # 5. Audit (FIXED: ctx is now a keyword argument)
        audit_record(
            ctx=ctx,  # <--- CHANGED THIS LINE
            action="lead.call_log.created", 
            entity_type=LEAD_ENTITY_TYPE,
            entity_id=lead.id,
            message=f"Call logged: {call.get_outcome_display()}",
            metadata={"call_id": str(call.id)}
        )

        return {"id": str(call.id), "outcome": call.outcome}

def schedule_site_visit(ctx: RequestContext, lead_id: str, payload: dict) -> dict:
    lead = Lead.objects.filter(id=lead_id, is_deleted=False).first()
    if not lead:
        raise NotFoundError(message="Lead not found")
    
    ensure_can_update_lead(ctx, lead)

    with transaction.atomic():
        assigned_id = payload.get('assigned_to_id')
        assigned_user = None
        if assigned_id:
            from django.contrib.auth import get_user_model
            assigned_user = get_user_model().objects.filter(id=assigned_id).first()
        
        visit = SiteVisit.objects.create(
            lead=lead,
            assigned_to=assigned_user or ctx.actor,
            project_name=payload['project_name'],
            location=payload.get('location', 'Site Office'),
            scheduled_at=payload['scheduled_at'],
            status='SCHEDULED'
        )

        # Timeline Event
        add_timeline_event(
            ctx,
            lead_id=lead.id,
            event_type="meeting",
            title=f"Site Visit Scheduled: {visit.project_name}",
            body=f"Location: {visit.location} @ {visit.scheduled_at}",
            payload={"visit_id": str(visit.id)}
        )

        # Audit (FIXED: ctx passed as keyword)
        audit_record(
            ctx=ctx, # <--- CHANGED
            action="lead.site_visit.scheduled", 
            entity_type=LEAD_ENTITY_TYPE,
            entity_id=lead.id,
            message=f"Site visit scheduled for {visit.project_name}",
            metadata={"visit_id": str(visit.id)}
        )

        return {"id": str(visit.id), "status": visit.status}

def update_site_visit(ctx: RequestContext, lead_id: str, visit_id: str, payload: dict) -> dict:
    visit = SiteVisit.objects.filter(id=visit_id, lead_id=lead_id).first()
    if not visit:
        raise NotFoundError(message="Visit not found")
    
    lead = visit.lead
    ensure_can_update_lead(ctx, lead)

    with transaction.atomic():
        old_status = visit.status
        visit.status = payload['status']
        if 'feedback' in payload:
            visit.feedback = payload['feedback']
        
        visit.save()

        # Log change to timeline if status changed
        if old_status != visit.status:
            add_timeline_event(
                ctx,
                lead_id=lead.id,
                event_type="meeting",
                title=f"Site Visit {visit.status}",
                body=visit.feedback,
                payload={"visit_id": str(visit.id), "old_status": old_status}
            )
        
        # Audit (FIXED: ctx passed as keyword)
        audit_record(
            ctx=ctx, # <--- CHANGED
            action="lead.site_visit.updated", 
            entity_type=LEAD_ENTITY_TYPE,
            entity_id=lead.id,
            message=f"Site visit status changed to {visit.status}",
            metadata={"visit_id": str(visit.id)}
        )

        return {"id": str(visit.id), "status": visit.status}