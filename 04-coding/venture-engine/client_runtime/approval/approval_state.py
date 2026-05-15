"""Approval lifecycle state tokens."""

from __future__ import annotations

APPROVAL_STATES: tuple[str, ...] = (
    "generated",
    "pending_approval",
    "approved",
    "rejected",
    "sent",
)


def normalize_approval_state(value: str) -> str:
    state = (value or "").strip().lower()
    if state not in APPROVAL_STATES:
        raise ValueError(f"invalid approval state: {value!r}")
    return state
