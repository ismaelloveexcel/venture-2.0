"""
event_normalizer.py — Single pipeline entry point for all events (INV-2).

Rules:
- Demo events and real execution events BOTH enter through normalize()
- Post-normalization events are immutable (frozen dataclass) — INV-7
- No is_demo / source fields in the output envelope — INV-7
- No branching after normalization — INV-2
- Zero import-time side effects — INV-1
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from domain_types import (
    VALID_EVENT_TYPES,
    VALID_SEVERITIES,
    SEVERITY_INFO,
    NormalizedEvent,
)


class NormalizationError(ValueError):
    """Raised when an event cannot be normalized."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _make_event_id(session_id: str, sequence: int, event_type: str) -> str:
    """Deterministic event_id from session + sequence + type."""
    raw = f"{session_id}:{sequence}:{event_type}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"evt-{digest[:12]}"


def normalize(
    *,
    session_id: str,
    run_id: str,
    event_type: str,
    severity: str = SEVERITY_INFO,
    sequence: int,
    description: str,
    metadata: dict[str, object] | None = None,
    timestamp: str | None = None,
    event_id: str | None = None,
) -> NormalizedEvent:
    """
    Normalize any event (demo or real) into a NormalizedEvent.

    This is the SINGLE entry point for the event pipeline (INV-2).
    No is_demo or source field exists in the output — post-normalization
    all events are equivalent (INV-7).

    Args:
        session_id: The session this event belongs to.
        run_id: The run_id (from SessionManager).
        event_type: One of VALID_EVENT_TYPES.
        severity: INFO | SOFT | HARD.
        sequence: Monotonic sequence number within the session.
        description: Human-readable description.
        metadata: Optional typed dict of event-specific data.
        timestamp: ISO-8601 UTC string; defaults to now.
        event_id: If provided, used as-is; else deterministically generated.

    Returns:
        NormalizedEvent (frozen, immutable).

    Raises:
        NormalizationError: if event_type or severity is invalid.
    """
    if event_type not in VALID_EVENT_TYPES:
        raise NormalizationError(
            f"Unknown event_type {event_type!r}. Valid: {sorted(VALID_EVENT_TYPES)}"
        )
    if severity not in VALID_SEVERITIES:
        raise NormalizationError(
            f"Unknown severity {severity!r}. Valid: {sorted(VALID_SEVERITIES)}"
        )
    if not session_id:
        raise NormalizationError("session_id must not be empty")
    if not run_id:
        raise NormalizationError("run_id must not be empty")
    if sequence < 1:
        raise NormalizationError(f"sequence must be >= 1, got {sequence}")

    ts = timestamp or _utc_now_iso()
    eid = event_id or _make_event_id(session_id, sequence, event_type)

    return NormalizedEvent(
        event_id=eid,
        session_id=session_id,
        run_id=run_id,
        event_type=event_type,
        severity=severity,
        timestamp=ts,
        sequence=sequence,
        description=description,
        metadata=metadata or {},
    )


def normalize_batch(
    raw_events: list[dict[str, Any]],
    *,
    session_id: str,
    run_id: str,
) -> list[NormalizedEvent]:
    """
    Normalize a list of raw event dicts into NormalizedEvents.

    Each dict must have keys matching normalize() kwargs.
    sequence is auto-assigned if not present (1-based, ascending).
    """
    results: list[NormalizedEvent] = []
    for i, raw in enumerate(raw_events, start=1):
        seq = raw.get("sequence", i)
        results.append(
            normalize(
                session_id=session_id,
                run_id=run_id,
                event_type=raw["event_type"],
                severity=raw.get("severity", SEVERITY_INFO),
                sequence=int(seq),
                description=raw.get("description", ""),
                metadata=raw.get("metadata"),
                timestamp=raw.get("timestamp"),
                event_id=raw.get("event_id"),
            )
        )
    # Sort by sequence to guarantee ordering (INV-2: no branching, linear pipeline)
    results.sort(key=lambda e: e.sequence)
    return results
