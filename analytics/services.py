from django.db.models import Count, Sum, Avg, F, Q
from django.utils import timezone
from datetime import timedelta
from typing import Dict, Any

from core.utils.context import RequestContext
from leads.models import Lead, CallLog, SiteVisit
from django.contrib.auth import get_user_model
from analytics.utils.security import ensure_can_access_analytics

User = get_user_model()

def get_agent_performance(ctx: RequestContext, date_from=None, date_to=None) -> Dict[str, Any]:
    ensure_can_access_analytics(ctx)
    
    # Date Filtering defaults to "Last 30 Days" if not provided
    if not date_from:
        date_from = timezone.now() - timedelta(days=30)
    if not date_to:
        date_to = timezone.now()

    # 1. Calls Aggregation
    calls_data = (
        CallLog.objects.filter(created_at__range=(date_from, date_to))
        .values('actor') # Group by Agent
        .annotate(
            total_calls=Count('id'),
            total_duration=Sum('duration'),
            answered_calls=Count('id', filter=Q(outcome='ANSWERED'))
        )
    )

    # 2. Site Visits Aggregation
    visits_data = (
        SiteVisit.objects.filter(scheduled_at__range=(date_from, date_to))
        .values('assigned_to') # Group by Agent
        .annotate(
            scheduled_visits=Count('id'),
            completed_visits=Count('id', filter=Q(status='COMPLETED'))
        )
    )

    # 3. Merge Data by Agent
    # We create a dictionary keyed by User ID to merge the two datasets
    agent_stats = {}

    def get_agent_entry(user_id):
        if user_id not in agent_stats:
            user = User.objects.filter(id=user_id).first()
            agent_stats[user_id] = {
                "agent_id": str(user_id),
                "agent_name": user.get_full_name() if user else "Unknown",
                "calls": {"total": 0, "answered": 0, "duration_minutes": 0},
                "visits": {"scheduled": 0, "completed": 0}
            }
        return agent_stats[user_id]

    for c in calls_data:
        if c['actor']:
            entry = get_agent_entry(c['actor'])
            entry['calls']['total'] = c['total_calls']
            entry['calls']['answered'] = c['answered_calls']
            entry['calls']['duration_minutes'] = round((c['total_duration'] or 0) / 60, 1)

    for v in visits_data:
        if v['assigned_to']:
            entry = get_agent_entry(v['assigned_to'])
            entry['visits']['scheduled'] = v['scheduled_visits']
            entry['visits']['completed'] = v['completed_visits']

    return {
        "period": {"from": date_from, "to": date_to},
        "agents": list(agent_stats.values())
    }

def get_pipeline_stats(ctx: RequestContext) -> Dict[str, Any]:
    ensure_can_access_analytics(ctx)

    # 1. Funnel: Count by Stage
    # Example: [{'stage': 'NEW', 'count': 50}, {'stage': 'CONTACTED', 'count': 20}]
    funnel = list(Lead.objects.filter(is_deleted=False).values('stage').annotate(count=Count('id')).order_by('-count'))

    # 2. Stagnation: Leads in NEW for > 24 hours
    threshold = timezone.now() - timedelta(hours=24)
    stagnant_count = Lead.objects.filter(
        stage='NEW', 
        created_at__lt=threshold,
        is_deleted=False
    ).count()

    # 3. Total Active Leads
    total_active = Lead.objects.filter(is_deleted=False).count()

    return {
        "total_leads": total_active,
        "stagnant_leads": stagnant_count,
        "funnel_breakdown": funnel
    }

def get_response_metrics(ctx: RequestContext, date_from=None, date_to=None) -> Dict[str, Any]:
    ensure_can_access_analytics(ctx)
    
    if not date_from: date_from = timezone.now() - timedelta(days=30)
    if not date_to: date_to = timezone.now()

    # 1. Average Response Time
    # Calculate difference between created_at and first_contact_at
    qs = Lead.objects.filter(
        created_at__range=(date_from, date_to),
        first_contact_at__isnull=False
    ).annotate(
        response_time=F('first_contact_at') - F('created_at')
    ).aggregate(
        avg_response=Avg('response_time')
    )

    avg_seconds = qs['avg_response'].total_seconds() if qs['avg_response'] else 0

    return {
        "avg_response_time_minutes": round(avg_seconds / 60, 1),
        "period": {"from": date_from, "to": date_to}
    }
    
    
# analytics/services.py

# ... existing imports ...
from leads.models import ReasonCode

def get_lost_analysis(ctx: RequestContext, date_from=None, date_to=None) -> Dict[str, Any]:
    ensure_can_access_analytics(ctx)
    
    if not date_from: date_from = timezone.now() - timedelta(days=90) # Default 90 days for trends
    if not date_to: date_to = timezone.now()

    # 1. Filter Lost Leads in Date Range
    qs = Lead.objects.filter(
        stage__in=["LOST", "DO_NOT_PURSUE"],
        updated_at__range=(date_from, date_to),
        is_deleted=False
    )
    
    total_lost = qs.count()

    # 2. Group by Reason Label
    # Result: [{'lost_reason__label': 'Price High', 'count': 15}, ...]
    breakdown = (
        qs.values('lost_reason__label')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # 3. Format Data (Calculate Percentages)
    data = []
    for item in breakdown:
        label = item['lost_reason__label'] or "Unknown / No Reason"
        count = item['count']
        percentage = round((count / total_lost) * 100, 1) if total_lost > 0 else 0
        
        data.append({
            "reason": label,
            "count": count,
            "percentage": percentage
        })

    return {
        "period": {"from": date_from, "to": date_to},
        "total_lost": total_lost,
        "breakdown": data
    }
    
    
# analytics/services.py

# ... existing imports ...
from django.db.models import Avg, F, Max
from django.utils import timezone
from datetime import timedelta

def get_daily_leaderboard(ctx: RequestContext, date=None) -> Dict[str, Any]:
    """
    Returns a ranked list of agents by activity for a specific day.
    """
    ensure_can_access_analytics(ctx)
    
    target_date = date or timezone.now().date()
    
    # 1. Rank by Calls
    # Note: We filter by the specific day
    call_leaders = (
        CallLog.objects.filter(created_at__date=target_date)
        .values('actor__id', 'actor__first_name', 'actor__last_name')
        .annotate(score=Count('id'))
        .order_by('-score')
    )[:5] # Top 5

    # 2. Rank by Visits Completed
    visit_leaders = (
        SiteVisit.objects.filter(
            status='COMPLETED',
            scheduled_at__date=target_date
        )
        .values('assigned_to__id', 'assigned_to__first_name', 'assigned_to__last_name')
        .annotate(score=Count('id'))
        .order_by('-score')
    )[:5]

    def format_leader(entry, key_id='actor__id', key_first='actor__first_name', key_last='actor__last_name'):
        # Handle cases where name might be empty
        name = f"{entry.get(key_first, '')} {entry.get(key_last, '')}".strip()
        return {
            "agent_name": name or "Unknown Agent",
            "count": entry['score'],
            "agent_id": str(entry[key_id]) if entry[key_id] else None
        }

    return {
        "date": target_date,
        "most_calls": [format_leader(x) for x in call_leaders],
        "most_visits": [format_leader(x, 'assigned_to__id', 'assigned_to__first_name', 'assigned_to__last_name') for x in visit_leaders]
    }

def get_stage_aging_analysis(ctx: RequestContext) -> Dict[str, Any]:
    """
    Bottleneck Analysis: Calculates the average age of leads in each stage.
    "How long have current leads been stuck in this stage?"
    """
    ensure_can_access_analytics(ctx)
    
    # We calculate 'age' as: Now - Updated_At (Last time it moved/changed)
    # OR Now - Created_At (Total age)
    # Let's use Total Age (Created_At) to see how old the leads in this bucket are.
    
    stats = (
        Lead.objects.filter(is_deleted=False)
        .values('stage')
        .annotate(
            avg_age=Avg(timezone.now() - F('created_at')),
            max_age=Max(timezone.now() - F('created_at')),
            count=Count('id')
        )
        .order_by('-avg_age')
    )
    
    data = []
    for stat in stats:
        avg_seconds = stat['avg_age'].total_seconds() if stat['avg_age'] else 0
        max_seconds = stat['max_age'].total_seconds() if stat['max_age'] else 0
        
        data.append({
            "stage": stat['stage'],
            "lead_count": stat['count'],
            "avg_age_days": round(avg_seconds / 86400, 1), # Convert seconds to days
            "max_age_days": round(max_seconds / 86400, 1),
            "status": "CRITICAL" if (avg_seconds / 86400) > 7 else "NORMAL" # Simple threshold logic
        })
        
    return {
        "analysis_date": timezone.now(),
        "stages": data
    }