from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class AppError(Exception):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class PermissionDeniedError(AppError):
    pass


class ValidationError(AppError):
    pass


class NotFoundError(AppError):
    pass


class WorkflowRejectedError(AppError):
    """
    Use for workflow guard/transition rejections.
    Typically maps to 422.
    """
    pass
