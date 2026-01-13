from django.utils import timezone
from django.contrib.auth import get_user_model
from leads.models import Lead, LeadTimelineEvent

User = get_user_model()

def check_sla_breaches():
    """
    Finds leads where the 'first_response_due_at' has passed 
    AND the lead is still in 'NEW' stage.
    """
    now = timezone.now()
    
    # 1. Fetch Candidates (SQLite Safe Mode)
    # We fetch all overdue NEW leads, then filter the 'escalated' flag in Python
    # to avoid database errors with JSON fields on SQLite.
    candidates = Lead.objects.filter(
        first_response_due_at__lt=now,
        stage="NEW",
        is_deleted=False
    )

    results = []
    
    for lead in candidates:
        # Check if already escalated
        qual = lead.qualification or {}
        if qual.get("is_escalated") is True:
            continue

        # If not, escalate it
        action_taken = escalate_lead(lead)
        results.append(action_taken)
        
    return results

def escalate_lead(lead: Lead):
    """
    Tags lead as Escalated and logs the event.
    """
    old_owner = lead.owner
    
    # 1. Update Lead Data
    if not lead.qualification:
        lead.qualification = {}
    
    lead.qualification["is_escalated"] = True
    lead.qualification["escalated_at"] = str(timezone.now())
    lead.save(update_fields=["qualification"])

    # 2. Add Timeline Event (Audit)
    LeadTimelineEvent.objects.create(
        lead=lead,
        type="system",
        title="SLA Breach Escalation",
        body=f"Lead was not contacted by due date ({lead.first_response_due_at}). Escalated.",
        payload={
            "original_owner_id": str(old_owner.id) if old_owner else None,
            "days_overdue": (timezone.now() - lead.first_response_due_at).days
        }
    )

    return f"Lead {lead.id} escalated."