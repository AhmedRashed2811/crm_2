from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from core.utils.context import RequestContext
from audit.models import AuditEvent


def record(
    *,
    ctx: RequestContext,
    action: str,
    entity_type: str,
    entity_id: UUID,
    message: str = "",
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    """
    Create an immutable audit event.
    Must be called from service layer whenever business state changes.
    """
    return AuditEvent.objects.create(
        request_id=ctx.request_id,
        source=ctx.source,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        actor=ctx.actor,
        action=action,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        metadata=metadata,
    )
