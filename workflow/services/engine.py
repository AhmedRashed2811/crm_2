from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from django.db import transaction

from core.api.exceptions import WorkflowRejectedError, NotFoundError
from core.utils.context import RequestContext
from workflow.models import WorkflowDefinition, WorkflowEvent, WorkflowInstance


@dataclass(frozen=True)
class TransitionResult:
    instance: WorkflowInstance
    event: WorkflowEvent


def get_active_definition(key: str) -> WorkflowDefinition:
    wf = WorkflowDefinition.objects.filter(key=key, status="active").order_by("-version").first()
    if not wf:
        raise NotFoundError(code="workflow.not_found", message=f"No active workflow found for key={key}")
    return wf


def _is_transition_allowed(defn: Dict[str, Any], from_state: str, to_state: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    transitions = defn.get("transitions", [])
    for t in transitions:
        if t.get("from") == from_state and t.get("to") == to_state:
            return True, t
    return False, None


@transaction.atomic
def create_instance(
    *,
    ctx: RequestContext,
    workflow_key: str,
    entity_type: str,
    entity_id: UUID,
    initial_state: str,
    payload: Optional[Dict[str, Any]] = None,
) -> TransitionResult:
    definition = get_active_definition(workflow_key)

    instance = WorkflowInstance.objects.create(
        definition=definition,
        entity_type=entity_type,
        entity_id=entity_id,
        state=initial_state,
    )

    event = WorkflowEvent.objects.create(
        request_id=ctx.request_id,
        source=ctx.source,
        actor=ctx.actor,
        instance=instance,
        action="init",
        from_state="__none__",
        to_state=initial_state,
        payload=payload or {},
    )

    return TransitionResult(instance=instance, event=event)


@transaction.atomic
def transition(
    *,
    ctx: RequestContext,
    instance: WorkflowInstance,
    action: str,
    to_state: str,
    payload: Optional[Dict[str, Any]] = None,
) -> TransitionResult:
    """
    Transition instance.state -> to_state if allowed by definition.
    """
    defn = instance.definition.definition
    from_state = instance.state

    allowed, transition_def = _is_transition_allowed(defn, from_state, to_state)
    if not allowed:
        raise WorkflowRejectedError(
            code="workflow.transition_not_allowed",
            message=f"Transition not allowed: {from_state} -> {to_state}",
            details={"from": from_state, "to": to_state, "action": action},
        )

    # v1: guard requirements (required_fields, required_reason_code, etc.)
    required_fields = transition_def.get("required_fields", [])
    if required_fields:
        
        val = (payload or {})
        missing = [f for f in required_fields if (f not in val) or (val.get(f) in [None, "", [], {}])]

        if missing:
            raise WorkflowRejectedError(
                code="workflow.missing_required_fields",
                message="Missing required fields for transition",
                details={"missing": missing, "from": from_state, "to": to_state},
            )

    # update state
    instance.state = to_state
    instance.save(update_fields=["state", "updated_at"])

    # write immutable event
    event = WorkflowEvent.objects.create(
        request_id=ctx.request_id,
        source=ctx.source,
        actor=ctx.actor,
        instance=instance,
        action=action,
        from_state=from_state,
        to_state=to_state,
        payload=payload or {},
    )

    return TransitionResult(instance=instance, event=event)
