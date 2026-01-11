from __future__ import annotations

from core.api.exceptions import PermissionDeniedError
from core.utils.context import RequestContext
from core.utils.permissions import user_in_groups
from leads.models import Lead


ROLE_ADMIN = ["Admin", "Developer"]
ROLE_MANAGER = ["Manager"]
ROLE_TEAM = ["TeamMember"]
ROLE_CONTROLLER = ["Controller"]

# Simple policy (v1):
# - Admin/Developer: full access
# - Manager: can assign/override/transition/timeline
# - TeamMember: can timeline + transition leads they own
# - Controller: read-only (for v1)


def ensure_can_read_lead(ctx: RequestContext, lead: Lead):
    if user_in_groups(ctx.actor, ROLE_ADMIN + ROLE_MANAGER + ROLE_TEAM + ROLE_CONTROLLER):
        return
    raise PermissionDeniedError(code="lead.read.forbidden", message="Not allowed to read lead")


def ensure_can_assign(ctx: RequestContext):
    if user_in_groups(ctx.actor, ROLE_ADMIN + ROLE_MANAGER):
        return
    raise PermissionDeniedError(code="lead.assign.forbidden", message="Not allowed to assign leads")


def ensure_can_transition(ctx: RequestContext, lead: Lead):
    if user_in_groups(ctx.actor, ROLE_ADMIN + ROLE_MANAGER):
        return
    # TeamMember can transition only owned leads
    if user_in_groups(ctx.actor, ROLE_TEAM) and lead.owner_id == getattr(ctx.actor, "id", None):
        return
    raise PermissionDeniedError(code="lead.transition.forbidden", message="Not allowed to change lead stage")


def ensure_can_add_timeline(ctx: RequestContext, lead: Lead):
    if user_in_groups(ctx.actor, ROLE_ADMIN + ROLE_MANAGER):
        return
    if user_in_groups(ctx.actor, ROLE_TEAM) and lead.owner_id == getattr(ctx.actor, "id", None):
        return
    raise PermissionDeniedError(code="lead.timeline.forbidden", message="Not allowed to add timeline events")


def ensure_can_merge(ctx: RequestContext):
    if user_in_groups(ctx.actor, ROLE_ADMIN + ROLE_MANAGER):
        return
    raise PermissionDeniedError(code="lead.merge.forbidden", message="Not allowed to merge leads")
