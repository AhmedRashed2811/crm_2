from __future__ import annotations
import uuid

def new_request_id() -> str:
    return uuid.uuid4().hex
