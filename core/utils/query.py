from __future__ import annotations

from datetime import datetime
from typing import Optional
from django.utils.dateparse import parse_datetime, parse_date


def parse_int(value: str | None, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        v = int(value) if value is not None else default
    except (TypeError, ValueError):
        v = default
    if min_value is not None:
        v = max(v, min_value)
    if max_value is not None:
        v = min(v, max_value)
    return v


def parse_iso_datetime_or_date(value: str | None) -> Optional[datetime]:
    """
    Accepts:
    - ISO datetime: 2026-01-11T10:30:00Z or 2026-01-11T10:30:00+02:00
    - date only: 2026-01-11 (treated as midnight)
    """
    if not value:
        return None

    dt = parse_datetime(value)
    if dt:
        return dt

    d = parse_date(value)
    if d:
        return datetime(d.year, d.month, d.day)

    return None
