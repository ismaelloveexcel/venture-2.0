"""
Canonical outbound / prospect-send state tokens (import-only library).

Phase A: constants + validation helper for boundaries that must reject unknown states.
"""

from __future__ import annotations

CANONICAL_SEND_STATES: frozenset[str] = frozenset(
    {
        "READY",
        "SENT",
        "REPLIED",
        "SUPPRESSED",
        "REVIEW_REQUIRED",
        "FAILED",
        "PAUSED",
    }
)

# SQLite outbound_events.status — lowercase historical values.
OUTBOUND_EVENT_STATUSES: frozenset[str] = frozenset({"sent", "dry_run"})


class SendStateValidationError(ValueError):
    """Raised when a persisted or inbound state string is not in the canonical set."""


def normalize_send_state_token(value: str) -> str:
    return (value or "").strip().upper()


def validate_canonical_send_state(value: str, *, context: str = "") -> str:
    """
    Return normalized state or raise if unknown.

    Use at validation boundaries (e.g. DB writes, report ingest) — not on every log line.
    """
    token = normalize_send_state_token(value)
    if token not in CANONICAL_SEND_STATES:
        hint = f" ({context})" if context else ""
        raise SendStateValidationError(f"unknown send state{hint}: {value!r}")
    return token


def validate_outbound_event_status(value: str, *, context: str = "") -> str:
    """Validate outbound_events.status before write (money-path persistence)."""
    token = (value or "").strip().lower()
    if token not in OUTBOUND_EVENT_STATUSES:
        hint = f" ({context})" if context else ""
        raise SendStateValidationError(f"unknown outbound_events.status{hint}: {value!r}")
    return token
