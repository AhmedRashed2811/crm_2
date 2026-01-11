from __future__ import annotations

from django.db.models import QuerySet
from core.utils.context import RequestContext
from core.utils.permissions import user_in_groups
from leads.models import Lead

ROLE_ADMIN = ["Admin", "Developer"]
ROLE_MANAGER = ["Manager"]
ROLE_TEAM = ["TeamMember"]
ROLE_CONTROLLER = ["Controller"]


def apply_lead_list_scope(ctx: RequestContext, qs: QuerySet[Lead]) -> QuerySet[Lead]:
    # Admin/Developer/Manager/Controller: can see all (v1)
    if user_in_groups(ctx.actor, ROLE_ADMIN + ROLE_MANAGER + ROLE_CONTROLLER):
        return qs

    # TeamMember: only owned leads
    if user_in_groups(ctx.actor, ROLE_TEAM):
        return qs.filter(owner_id=getattr(ctx.actor, "id", None))

    # Default: nothing
    return qs.none()
