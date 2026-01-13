from __future__ import annotations

from core.api.exceptions import PermissionDeniedError
from core.utils.context import RequestContext
from core.utils.permissions import user_in_groups

# Reuse the roles defined in your pattern
ROLE_ADMIN = ["Admin", "Developer"]
ROLE_MANAGER = ["Manager"]

def ensure_can_access_analytics(ctx: RequestContext):
    """
    Only Admins and Managers can view analytics dashboards.
    """
    if user_in_groups(ctx.actor, ROLE_ADMIN + ROLE_MANAGER):
        return
        
    raise PermissionDeniedError(
        code="analytics.access_forbidden", 
        message="You do not have permission to view analytics."
    )