from __future__ import annotations

import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class AuditEvent(models.Model):
    """
    Immutable append-only audit log.

    Design:
    - No updates. No deletes (DB + app-level discipline).
    - Queryable by entity, actor, action, time, request_id.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)

    # Correlation / source
    request_id = models.CharField(max_length=64, db_index=True)
    source = models.CharField(max_length=32, default="api", db_index=True)
    ip = models.CharField(max_length=64, blank=True, default="")
    user_agent = models.CharField(max_length=256, blank=True, default="")

    # Actor
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
        db_index=True,
    )

    # What happened
    action = models.CharField(max_length=80, db_index=True)  # e.g. lead.created, lead.assigned
    message = models.CharField(max_length=255, blank=True, default="")

    # Target (generic reference)
    entity_type = models.CharField(max_length=80, db_index=True)  # e.g. leads.Lead
    entity_id = models.UUIDField(db_index=True)

    # Details (JSON)
    # Use JSONField (native on modern Django)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    metadata = models.JSONField(null=True, blank=True)  # extra context, reason codes, etc.

    class Meta:
        indexes = [
            models.Index(fields=["entity_type", "entity_id", "created_at"]),
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["actor", "created_at"]),
            models.Index(fields=["request_id"]),
        ]
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        # enforce immutability at application level: block updates
        if self.pk and AuditEvent.objects.filter(pk=self.pk).exists():
            raise RuntimeError("AuditEvent is immutable and cannot be updated.")
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.created_at} {self.action} {self.entity_type}:{self.entity_id}"
