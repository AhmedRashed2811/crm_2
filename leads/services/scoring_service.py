from typing import Dict, Any
from django.db import transaction
from leads.models import Lead, ScoringRule, ScoreBucket

def calculate_lead_score(lead: Lead) -> int:
    """
    Dynamic Scoring Engine:
    Fetches active rules from DB and applies them.
    Logic: Sum of (Max Score per Category).
    """
    total_score = 0
    
    # 1. Prepare Data for Matching
    # Normalize inputs to lowercase for comparison
    lead_data = {
        'source': str(lead.source or "").lower(),
        'budget': str((lead.qualification or {}).get("budget", "")).lower(),
        'title': str((lead.qualification or {}).get("job_title", "")).lower(),
        'country': str((lead.qualification or {}).get("country", "")).lower(),
    }

    # 2. Fetch all Active Rules
    # Optimization: In high scale, cache this query
    rules = ScoringRule.objects.filter(is_active=True)

    # 3. Group Rules by Category to apply "Max per Category" logic
    # This prevents "Manager" (5pts) and "Director" (15pts) adding up to 20.
    # We want the single highest match per category.
    category_scores = {}

    for rule in rules:
        cat = rule.category
        if cat not in category_scores:
            category_scores[cat] = []

        # Check Match
        data_val = lead_data.get(cat, "")
        rule_val = rule.keyword.lower()
        matched = False

        if rule.match_type == 'exact':
            if data_val == rule_val:
                matched = True
        elif rule.match_type == 'contains':
            if rule_val in data_val:
                matched = True
        
        if matched:
            category_scores[cat].append(rule.points)

    # 4. Calculate Final Score
    for cat, scores in category_scores.items():
        if scores:
            best_score = max(scores)
            total_score += best_score

    return total_score

def get_bucket_from_score(score: int) -> str:
    """
    Dynamic Bucket Assignment.
    Fetches buckets from DB (ordered by min_score desc).
    """
    buckets = ScoreBucket.objects.all().order_by('-min_score')
    
    for bucket in buckets:
        if score >= bucket.min_score:
            return bucket.name
            
    return "COLD"

def get_next_best_action(lead: Lead) -> str:
    bucket = lead.score_bucket or "COLD"
    stage = lead.stage or "NEW"

    if bucket == "HOT":
        if stage == "NEW": return "CALL_IMMEDIATELY"
        elif stage == "CONTACTED": return "SCHEDULE_SITE_VISIT"
    elif bucket == "WARM":
        return "SEND_BROCHURE"
        
    return "EMAIL_NURTURE_SEQUENCE"

@transaction.atomic
def run_scoring_engine(lead: Lead):
    """
    Main Entry Point
    """
    raw_score = calculate_lead_score(lead)
    new_bucket = get_bucket_from_score(raw_score)
    next_action = get_next_best_action(lead)

    # Update Lead
    lead.score_bucket = new_bucket
    if not lead.qualification:
        lead.qualification = {}
    
    lead.qualification["scoring_details"] = {
        "raw_score": raw_score,
        "next_best_action": next_action,
        "last_scored_at": "NOW" # Use timezone.now() in production
    }
    
    lead.save(update_fields=["score_bucket", "qualification"])
    
    return {
        "score": raw_score,
        "bucket": new_bucket,
        "next_action": next_action
    }