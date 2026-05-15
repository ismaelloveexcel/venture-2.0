"""Deterministic operator workflow state snapshot."""

from __future__ import annotations

from typing import Any


def build_workflow_state(action_queue: dict[str, Any]) -> dict[str, Any]:
    queue = list(action_queue.get("queue") or [])
    next_action = str(action_queue.get("next_action") or "None")
    highest_priority = str(action_queue.get("highest_priority") or "LOW")
    if not queue:
        state = "IDLE"
    elif highest_priority == "HIGH":
        state = "ACTION_REQUIRED"
    elif highest_priority == "MEDIUM":
        state = "REVIEW_REQUIRED"
    else:
        state = "MONITOR"
    return {
        "state": state,
        "queue_size": len(queue),
        "highest_priority": highest_priority,
        "next_action": next_action,
    }
