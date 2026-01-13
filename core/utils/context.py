from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from django.contrib.auth.models import AbstractBaseUser


@dataclass(frozen=True)
class RequestContext:
    actor: Optional[AbstractBaseUser]
    request_id: str
    source: str = "api"
    ip: str = ""
    user_agent: str = ""



def build_ctx(request) -> RequestContext:
    """
    Helper to build RequestContext from a standard Django Request.
    """
    return RequestContext(
        actor=request.user if request.user.is_authenticated else None,
        request_id=getattr(request, "request_id", ""), # Assumes ID middleware or empty
        source="api",
        ip=request.META.get("REMOTE_ADDR", ""),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:256],
    )