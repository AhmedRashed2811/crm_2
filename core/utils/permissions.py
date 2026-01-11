from __future__ import annotations

from typing import Iterable
from django.contrib.auth.models import AbstractBaseUser


def user_in_groups(user: AbstractBaseUser, allowed: Iterable[str]) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name__in=list(allowed)).exists()
