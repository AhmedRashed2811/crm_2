import random
from django.db import transaction
from django.utils import timezone
from leads.models import Lead, RoutingRule, SalesTeam, TeamMember
from core.utils.context import RequestContext

# DELETE THIS LINE FROM THE TOP:
# from leads.services.leads_service import assign_lead  <-- CAUSES CIRCULAR IMPORT

def route_lead(ctx: RequestContext, lead: Lead):
    """
    Main Entry Point: Finds the right rule -> Finds the right team -> Finds the right user.
    """
    # 1. Find matching Rule
    # We fetch all active rules ordered by priority (0 first)
    rules = RoutingRule.objects.filter(is_active=True).select_related("target_team")
    print(f"rules = {rules}")
    matched_rule = None
    for rule in rules:
        if rule.matches(lead):
            matched_rule = rule
            break
        
    print(f"matched_rule = {matched_rule}")
    
    if not matched_rule:
        return

    # 2. Apply SLA from the rule (SRS requirement)
    if matched_rule.sla_minutes:
        
        print(f"matched_rule.sla_minutes= {matched_rule.sla_minutes}")
        lead.first_response_due_at = timezone.now() + timezone.timedelta(minutes=matched_rule.sla_minutes)
        lead.save(update_fields=["first_response_due_at"])

    # 3. Distribute to Team
    team = matched_rule.target_team
    
    print(f"team = {team}")
    
    target_user = _pick_user_from_team(team)
    
    print(f"target_user = {target_user}")
    
    

    if target_user:
        # ✅ FIX: Import inside the function to break the circle
        from leads.services.leads_service import assign_lead
        
        assign_lead(
            ctx=ctx,
            lead_id=lead.id,
            owner_id=target_user.id,
            lock=True, # SRS: "Lead lock to owner"
            reason=f"Routed via Rule: {matched_rule.name} (Team: {team.name})"
        )

def _pick_user_from_team(team: SalesTeam):
    """
    The 'Routing Engine' Logic (Round Robin / Weighted).
    Only picks 'Available' members.
    """
    # Filter for available members only
    members = team.members.filter(is_available=True, user__is_active=True)
    
    print(f"members = {members}")
    if not members.exists():
        return None

    print(f"team.distribution_method = {team.distribution_method}")
    if team.distribution_method == "ROUND_ROBIN":
        # Strategy: Pick the member who waited the longest (oldest last_assigned_at)
        # Null last_assigned_at means they never got a lead, so they go first.
        candidate = members.order_by("last_assigned_at").first()
        print(f"candidate = {candidate}")
        
        if candidate:
            # Update their timestamp so they go to the back of the line
            candidate.last_assigned_at = timezone.now()
            candidate.save(update_fields=["last_assigned_at"])
            return candidate.user

    elif team.distribution_method == "WEIGHTED":
        # Strategy: Weighted Random selection
        total_weight = sum(m.weight for m in members)
        print(f"total_weight = {total_weight}")
        if total_weight == 0:
            print(f"members.first().user = {members.first().user}")
            return members.first().user # Fallback
            
        pick = random.randint(1, total_weight)
        print(f"pick = {pick}")
        current = 0
        for m in members:
            current += m.weight
            if current >= pick:
                print(f"current = {current}")
                print(f"m.user = {m.user}")
                return m.user

    elif team.distribution_method == "BROADCAST":
        return None

    return None