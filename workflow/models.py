from __future__ import annotations

import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class WorkflowDefinition(models.Model):
    """
    Versioned workflow definition (ex: Lead Lifecycle v1).
    We store states/transitions as JSON for v1 speed.
    """
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("retired", "Retired"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    key = models.CharField(max_length=80, db_index=True)  # e.g. lead_lifecycle
    version = models.PositiveIntegerField(default=1, db_index=True)
    name = models.CharField(max_length=120)

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="draft", db_index=True)

    # JSON structure example:
    # { "states": ["NEW","CONTACTED"], "transitions":[{"from":"NEW","to":"CONTACTED","code":"contact"}]}
    definition = models.JSONField()

    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)

    class Meta:
        unique_together = ("key", "version")
        indexes = [
            models.Index(fields=["key", "status"]),
            models.Index(fields=["key", "version"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.key} v{self.version} ({self.status})"


class WorkflowInstance(models.Model):
    """
    Binds a workflow definition to a business entity (Lead).
    Keeps the current state.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    definition = models.ForeignKey(WorkflowDefinition, on_delete=models.PROTECT, related_name="instances")

    entity_type = models.CharField(max_length=80, db_index=True)  # e.g. leads.Lead
    entity_id = models.UUIDField(db_index=True)

    state = models.CharField(max_length=80, db_index=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    updated_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["definition", "state"]),
        ]

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.entity_type}:{self.entity_id} -> {self.state}"


class WorkflowEvent(models.Model):
    """
    Immutable append-only event log for workflow transitions.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)

    # correlation
    request_id = models.CharField(max_length=64, db_index=True)
    source = models.CharField(max_length=32, default="api", db_index=True)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workflow_events",
        db_index=True,
    )

    instance = models.ForeignKey(WorkflowInstance, on_delete=models.CASCADE, related_name="events")

    action = models.CharField(max_length=80, db_index=True)  # e.g. "contacted", "qualified"
    from_state = models.CharField(max_length=80, db_index=True)
    to_state = models.CharField(max_length=80, db_index=True)

    payload = models.JSONField(null=True, blank=True)  # reason codes, notes, etc.

    class Meta:
        indexes = [
            models.Index(fields=["instance", "created_at"]),
            models.Index(fields=["to_state", "created_at"]),
            models.Index(fields=["request_id"]),
        ]
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        # immutability enforcement: no updates
        if self.pk and WorkflowEvent.objects.filter(pk=self.pk).exists():
            raise RuntimeError("WorkflowEvent is immutable and cannot be updated.")
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.created_at} {self.from_state}->{self.to_state} ({self.action})"
