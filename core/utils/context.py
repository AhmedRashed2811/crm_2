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
