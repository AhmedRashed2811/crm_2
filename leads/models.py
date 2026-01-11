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
