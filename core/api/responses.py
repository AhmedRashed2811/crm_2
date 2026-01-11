from __future__ import annotations

from typing import Any, Dict, List, Optional
from rest_framework.response import Response


def ok(data: Any = None, meta: Optional[Dict[str, Any]] = None, status: int = 200) -> Response:
    return Response(
        {"success": True, "data": data, "errors": [], "meta": meta or {}},
        status=status,
    )


def fail(errors: List[Dict[str, Any]], meta: Optional[Dict[str, Any]] = None, status: int = 400) -> Response:
    return Response(
        {"success": False, "data": None, "errors": errors, "meta": meta or {}},
        status=status,
    )
