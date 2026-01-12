# leads/services/sla_service.py

from django.utils import timezone
from leads.models import Lead
from core.utils.context import RequestContext

def check_sla_breaches(ctx: RequestContext):
    """
    SRS: 'Escalation to team lead when breached'
    SRS: 'Auto-reassign on inactivity'
    """
    now = timezone.now()
    
    # 1. Find breached leads (Due date passed, still "NEW", not contacted)
    # Assuming "NEW" means not contacted.
    breached_leads = Lead.objects.filter(
        first_response_due_at__lt=now,
        first_contact_at__isnull=True,
        stage="NEW",
        is_deleted=False
    )

    for lead in breached_leads:
        # LOGIC: Reassign or Notify?
        
        # Example: Auto-reassign logic
        # If it was assigned to a user, remove them (return to pool) or escalate to Supervisor
        
        old_owner = lead.owner
        
        # Audit the breach
        # Send Notification (Mock)
        print(f"SLA BREACH: Lead {lead.id} assigned to {old_owner} failed to respond.")
        
        # Logic: Unlock the lead so others can take it?
        if lead.locked:
            lead.locked = False
            lead.locked_at = None
            lead.save(update_fields=["locked", "locked_at"])