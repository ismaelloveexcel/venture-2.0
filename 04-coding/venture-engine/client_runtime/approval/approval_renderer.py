"""Deterministic approval snapshot rendering."""

from __future__ import annotations

from typing import Any

from .approval_state import APPROVAL_STATES


def render_approval_snapshot(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {state: 0 for state in APPROVAL_STATES}
    for item in items:
        state = str(item.get("state") or "").strip().lower()
        if state in counts:
            counts[state] += 1
    return {
        "total": len(items),
        "status_counts": counts,
        "next_action": "approve_pending" if counts["pending_approval"] > 0 else "none",
    }
