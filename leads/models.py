from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import BaseUUIDModel


class ReasonCode(BaseUUIDModel):
    """
    Reason codes for terminal states like LOST / DO_NOT_PURSUE.
    Soft-deletable (deactivate without breaking history).
    """
    TYPE_CHOICES = [
        ("LOST", "Lost"),
        ("DO_NOT_PURSUE", "Do Not Pursue"),
    ]

    code = models.CharField(max_length=50, unique=True)  # e.g. "NO_BUDGET"
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, db_index=True)
    label = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True, db_index=True)

    def __str__(self) -> str:
        return f"{self.type}:{self.code}"


class Lead(BaseUUIDModel):
    """
    Core lead record (Module 1 system of record).
    """
    # Basic identity
    full_name = models.CharField(max_length=160, blank=True, default="")
    primary_phone = models.CharField(max_length=40, blank=True, default="", db_index=True)
    primary_email = models.EmailField(blank=True, default="", db_index=True)

    # Attribution
    source = models.CharField(max_length=80, blank=True, default="", db_index=True)   # e.g. meta_ads, walk_in
    medium = models.CharField(max_length=80, blank=True, default="", db_index=True)   # e.g. cpc, referral
    campaign = models.CharField(max_length=120, blank=True, default="")
    content = models.CharField(max_length=120, blank=True, default="")
    term = models.CharField(max_length=120, blank=True, default="")
    utm = models.JSONField(null=True, blank=True)  # store extra UTMs

    # Consent / DNC
    marketing_opt_in = models.BooleanField(default=True, db_index=True)
    do_not_contact = models.BooleanField(default=False, db_index=True)

    # Ownership / assignment
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_leads",
        db_index=True,
    )
    locked = models.BooleanField(default=False, db_index=True)  # prevent cherry-picking
    locked_at = models.DateTimeField(null=True, blank=True)

    # Lifecycle summary (current workflow state is stored in workflow instance; we mirror for fast filtering)
    stage = models.CharField(max_length=40, default="NEW", db_index=True)  # mirror of workflow state

    # Qualification summary (v1)
    score_bucket = models.CharField(max_length=20, blank=True, default="", db_index=True)  # HOT/WARM/COLD
    qualification = models.JSONField(null=True, blank=True)  # budget, timeframe, interest, etc.

    # SLA fields (v1 minimal)
    first_response_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    first_contact_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # External references (integrations)
    external_refs = models.JSONField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.full_name or 'Lead'} ({self.primary_phone or self.primary_email})"


class LeadIdentityPoint(BaseUUIDModel):
    """
    Normalized identity points for dedup: phone/email/national_id/etc.
    """
    TYPE_CHOICES = [
        ("phone", "Phone"),
        ("email", "Email"),
        ("national_id", "National ID"),
        ("other", "Other"),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="identity_points")
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, db_index=True)
    value = models.CharField(max_length=160, db_index=True)

    is_primary = models.BooleanField(default=False, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["type", "value"]),
        ]


    def __str__(self) -> str:
        return f"{self.type}:{self.value}"


class LeadTimelineEvent(BaseUUIDModel):
    """
    Append-only timeline events (notes/calls/whatsapp/email/system events).
    Do NOT edit; corrections are new events.
    """
    TYPE_CHOICES = [
        ("note", "Note"),
        ("call", "Call"),
        ("whatsapp", "WhatsApp"),
        ("email", "Email"),
        ("sms", "SMS"),
        ("meeting", "Meeting"),
        ("system", "System"),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="timeline")

    type = models.CharField(max_length=20, choices=TYPE_CHOICES, db_index=True)
    title = models.CharField(max_length=160, blank=True, default="")
    body = models.TextField(blank=True, default="")
    payload = models.JSONField(null=True, blank=True)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lead_timeline_events",
    )

    class Meta:
        ordering = ["-created_at"]




class LeadTask(BaseUUIDModel):
    """
    Follow-up tasks for next actions (SLA-02 later).
    """
    STATUS_CHOICES = [
        ("open", "Open"),
        ("done", "Done"),
        ("canceled", "Canceled"),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=160)
    due_at = models.DateTimeField(null=True, blank=True, db_index=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open", db_index=True)

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lead_tasks",
        db_index=True,
    )

    completed_at = models.DateTimeField(null=True, blank=True)

    def mark_done(self):
        if self.status != "done":
            self.status = "done"
            self.completed_at = timezone.now()
            self.save(update_fields=["status", "completed_at", "updated_at"])
            
            
# leads/models.py

from django.db import models
from django.conf import settings
from core.models import BaseUUIDModel

class SalesTeam(BaseUUIDModel):
    """
    Represents a pool of agents (e.g., 'Alpha Team', 'VIP Handlers').
    SRS: Supports Routing Engine targets.
    """
    DISTRIBUTION_METHOD_CHOICES = [
        ("ROUND_ROBIN", "Round Robin"),
        ("WEIGHTED", "Weighted Random"),
        ("BROADCAST", "Broadcast / Cherry Pick"), # Everyone sees it, first to claim wins
    ]

    name = models.CharField(max_length=120)
    distribution_method = models.CharField(
        max_length=20, 
        choices=DISTRIBUTION_METHOD_CHOICES, 
        default="ROUND_ROBIN"
    )
    
    # SRS: "Team Coverage" - We can add working hours here later
    
    def __str__(self):
        return f"{self.name} ({self.get_distribution_method_display()})"


class TeamMember(BaseUUIDModel):
    """
    Links a User to a Team with routing properties.
    SRS: Supports 'Weighted distribution' & 'Performance-based routing'.
    """
    team = models.ForeignKey(SalesTeam, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    # For Weighted Distribution (e.g., Senior gets 100, Junior gets 50)
    weight = models.PositiveIntegerField(default=100)
    
    # For Round Robin: Tracks when they last got a lead
    last_assigned_at = models.DateTimeField(null=True, blank=True)
    
    # For Availability (Vacation/Shift)
    is_available = models.BooleanField(default=True)

    class Meta:
        unique_together = ("team", "user")
        ordering = ["last_assigned_at"] # Crucial for Round Robin (oldest timestamp = next in line)

class RoutingRule(BaseUUIDModel):
    """
    The Decision Logic.
    SRS: "Apply routing rules by project, language, availability, or priority."
    """
    name = models.CharField(max_length=120)
    priority = models.PositiveIntegerField(default=0, db_index=True)  # Priority 0 runs first
    is_active = models.BooleanField(default=True)

    # --- CRITERIA (The "IF" part) ---
    # We use JSON for flexibility or specific fields. Let's use strict fields for performance.
    
    # SRS: "Project/phase interest"
    project_scope = models.CharField(max_length=120, blank=True, null=True, help_text="Matches Lead.interest")
    
    # SRS: "Nationality / Language"
    language = models.CharField(max_length=10, blank=True, null=True, help_text="e.g. 'en', 'ar'")
    
    # SRS: "Preferred Channel"
    source = models.CharField(max_length=80, blank=True, null=True, help_text="e.g. 'whatsapp', 'walk_in'")
    
    # SRS: "VIP leads"
    score_bucket = models.CharField(max_length=20, blank=True, null=True, help_text="e.g. 'HOT', 'VIP'")

    # --- TARGET (The "THEN" part) ---
    target_team = models.ForeignKey(SalesTeam, on_delete=models.CASCADE)
    
    # SRS: SLA Enforcement
    sla_minutes = models.PositiveIntegerField(
        default=60, 
        help_text="Expected response time in minutes for leads matching this rule."
    )

    class Meta:
        ordering = ["priority"]

    def matches(self, lead) -> bool:
        """
        Check if lead matches criteria. None/Empty fields act as Wildcards.
        """
        # 1. Source Check
        if self.source and self.source != lead.source:
            return False
        
        # 2. Score Check
        if self.score_bucket and self.score_bucket != lead.score_bucket:
            return False
            
        # 3. Language Check (STRICT FIX)
        # If rule specifies a language, the lead MUST match it. Missing = Mismatch.
        if self.language:
            lead_lang = (lead.qualification or {}).get("language")
            if lead_lang != self.language:
                return False

        # 4. Project Scope Check (ADDED MISSING LOGIC)
        # If rule specifies a project, the lead MUST have that interest.
        if self.project_scope:
            lead_interest = (lead.qualification or {}).get("interest")
            if lead_interest != self.project_scope:
                return False
                
        return True
    
    
    

# ==========================================
# 3. DYNAMIC SCORING MODELS (NEW)
# ==========================================

class ScoringRule(BaseUUIDModel):
    """
    Dynamic Rules for Lead Scoring.
    """
    CATEGORY_CHOICES = (
        ('budget', 'Budget'),
        ('title', 'Job Title'),
        ('source', 'Source'),
        ('country', 'Country'),
    )
    
    MATCH_TYPE_CHOICES = (
        ('exact', 'Exact Match'),       
        ('contains', 'Contains'),       
    )

    name = models.CharField(max_length=255, help_text="Internal name for this rule")
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, db_index=True)
    keyword = models.CharField(max_length=255, help_text="Value to match (e.g., 'CEO', '10M+')")
    match_type = models.CharField(max_length=20, choices=MATCH_TYPE_CHOICES, default='contains')
    points = models.IntegerField(default=0, help_text="Points to add (can be negative)")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.category.upper()}: {self.keyword} ({self.points} pts)"


class ScoreBucket(BaseUUIDModel):
    """
    Thresholds for classification.
    """
    name = models.CharField(max_length=50, unique=True) # HOT, WARM, COLD
    min_score = models.IntegerField(unique=True, help_text="Minimum score required")
    priority = models.IntegerField(default=0, help_text="High priority buckets checked first")
    color = models.CharField(max_length=20, default="#FFFFFF", help_text="Hex code for UI")

    class Meta:
        ordering = ['-min_score']

    def __str__(self):
        return f"{self.name} (>{self.min_score})"