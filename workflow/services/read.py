from __future__ import annotations

from typing import Any, Dict, List
from workflow.models import WorkflowInstance


def allowed_next_states(instance: WorkflowInstance) -> List[str]:
    defn: Dict[str, Any] = instance.definition.definition
    current = instance.state
    transitions = defn.get("transitions", [])
    next_states = [t.get("to") for t in transitions if t.get("from") == current and t.get("to")]
    # remove duplicates, keep order
    seen = set()
    out = []
    for s in next_states:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out
