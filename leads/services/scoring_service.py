from typing import Dict, Any
from django.db import transaction
from leads.models import Lead, ScoringRule, ScoreBucket, LeadTimelineEvent

def calculate_lead_score(lead: Lead) -> int:
    """
    Dynamic Scoring Engine v2:
    - Static Rules: Sum of (Max Score per Category).
    - Behavioral Rules: Sum of (Points * Occurrence).
    """
    total_score = 0
    
    # --- 1. PREPARE STATIC DATA ---
    lead_data = {
        'source': str(lead.source or "").lower(),
        'budget': str((lead.qualification or {}).get("budget", "")).lower(),
        'title': str((lead.qualification or {}).get("job_title", "")).lower(),
        'country': str((lead.qualification or {}).get("country", "")).lower(),
    }

    # --- 2. PREPARE BEHAVIORAL DATA ---
    # Fetch last 100 events to analyze behavior (optimization limit)
    recent_events = LeadTimelineEvent.objects.filter(lead=lead).order_by('-created_at')[:100]
    # We will match against 'title' or 'type' of the event
    event_signatures = [
        f"{e.type} {e.title}".lower() for e in recent_events
    ]

    # --- 3. FETCH RULES ---
    rules = ScoringRule.objects.filter(is_active=True)

    # --- 4. APPLY LOGIC ---
    static_category_scores = {}
    behavioral_score = 0

    for rule in rules:
        cat = rule.category
        rule_key = rule.keyword.lower()
        points = rule.points

        if cat == 'activity':
            # BEHAVIORAL LOGIC (Cumulative)
            # Check how many times this rule matches the events
            match_count = 0
            for ev_sig in event_signatures:
                if rule.match_type == 'exact' and rule_key == ev_sig:
                    match_count += 1
                elif rule.match_type == 'contains' and rule_key in ev_sig:
                    match_count += 1
            
            if match_count > 0:
                behavioral_score += (points * match_count)

        else:
            # STATIC LOGIC (Max per Category)
            data_val = lead_data.get(cat, "")
            matched = False

            if rule.match_type == 'exact' and data_val == rule_key:
                matched = True
            elif rule.match_type == 'contains' and rule_key in data_val:
                matched = True
            
            if matched:
                if cat not in static_category_scores:
                    static_category_scores[cat] = []
                static_category_scores[cat].append(points)

    # --- 5. SUMMARIZE ---
    
    # A. Add Static Scores (Max per category)
    for scores in static_category_scores.values():
        total_score += max(scores)
        
    # B. Add Behavioral Score
    total_score += behavioral_score

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