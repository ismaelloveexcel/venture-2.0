"""
Strict validation for lifecycle events before append (ordering, dedupe, payloads, time).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from lifecycle_engine import LifecycleEventType

# Stored on every event payload for forward-compatible replay
EVENT_SCHEMA_VERSION = 1

ALL_EVENT_TYPES: Set[str] = {
    LifecycleEventType.PROSPECT_LOADED,
    LifecycleEventType.EMAIL_ENRICHED,
    LifecycleEventType.MESSAGE_DRAFTED,
    LifecycleEventType.CTA_SELECTED,
    LifecycleEventType.OUTREACH_SENT,
    LifecycleEventType.FOLLOWUP_SENT,
    LifecycleEventType.DELIVERED,
    LifecycleEventType.OPENED,
    LifecycleEventType.CLICKED,
    LifecycleEventType.REPLIED,
    LifecycleEventType.BOUNCED,
    LifecycleEventType.COMPLAINED,
    LifecycleEventType.UNSUBSCRIBED,
    LifecycleEventType.BLOCKED,
    LifecycleEventType.QUALIFIED,
    LifecycleEventType.DISQUALIFIED,
    LifecycleEventType.NURTURE,
    LifecycleEventType.CLOSED_WON,
    LifecycleEventType.NO_RESPONSE_DECAY,
}

# At most one of these per opportunity stream (dedupe)
_SINGLETON_EVENTS = {
    LifecycleEventType.REPLIED,
    LifecycleEventType.CLOSED_WON,
    LifecycleEventType.QUALIFIED,
}

_SEND_MARKERS = {LifecycleEventType.OUTREACH_SENT, LifecycleEventType.FOLLOWUP_SENT}


class LifecycleEventValidationError(Exception):
    def __init__(self, reasons: List[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons))


def normalize_lifecycle_payload(payload: Optional[Dict[str, Any]], schema_version: int = EVENT_SCHEMA_VERSION) -> Dict[str, Any]:
    base = dict(payload or {})
    base.setdefault("_schema_version", schema_version)
    return base


def _parse_ts(iso: str) -> datetime:
    s = (iso or "").strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def validate_event_timestamp(created_at_iso: str, now: Optional[datetime] = None) -> None:
    reasons: List[str] = []
    now = now or datetime.now()
    try:
        ts = _parse_ts(created_at_iso)
    except ValueError:
        raise LifecycleEventValidationError(["invalid_timestamp_iso"])
    skew_future = timedelta(minutes=5)
    if ts > now + skew_future:
        reasons.append("timestamp_in_future")
    if ts < now - timedelta(days=400):
        reasons.append("timestamp_too_far_in_past")
    if reasons:
        raise LifecycleEventValidationError(reasons)


def validate_payload_fields(event_type: str, payload: Dict[str, Any]) -> None:
    reasons: List[str] = []
    if event_type == LifecycleEventType.BLOCKED:
        if not str(payload.get("reason") or payload.get("detail") or ""):
            reasons.append("blocked_event_requires_reason_or_detail")
    ver = payload.get("_schema_version", EVENT_SCHEMA_VERSION)
    try:
        v = int(ver)
    except (TypeError, ValueError):
        reasons.append("invalid_schema_version")
    else:
        if v < 1:
            reasons.append("unsupported_schema_version")
    if reasons:
        raise LifecycleEventValidationError(reasons)


def validate_lifecycle_event(
    event_type: str,
    payload: Dict[str, Any],
    *,
    current_outreach_state: str,
    prior_event_types: List[str],
    created_at_iso: str,
    now: Optional[datetime] = None,
    engagement_requires_send: bool = True,
) -> None:
    """
    Raises LifecycleEventValidationError if the event must not be appended.
    """
    reasons: List[str] = []
    et = (event_type or "").strip()
    if et not in ALL_EVENT_TYPES:
        raise LifecycleEventValidationError([f"unknown_event_type:{et}"])

    validate_event_timestamp(created_at_iso, now=now)
    validate_payload_fields(et, payload)

    counts = {}
    for t in prior_event_types:
        counts[t] = counts.get(t, 0) + 1

    if et in _SINGLETON_EVENTS and counts.get(et, 0) >= 1:
        reasons.append(f"duplicate_singleton_event:{et}")

    if et == LifecycleEventType.REPLIED:
        if not any(m in counts for m in _SEND_MARKERS):
            reasons.append("replied_requires_prior_outreach_or_followup_sent")
        if current_outreach_state == "DISQUALIFIED":
            reasons.append("replied_not_allowed_in_disqualified")
        if current_outreach_state == "NURTURE":
            reasons.append("replied_not_allowed_in_nurture")

    if et in {LifecycleEventType.OPENED, LifecycleEventType.CLICKED, LifecycleEventType.DELIVERED}:
        if engagement_requires_send and not any(m in counts for m in _SEND_MARKERS):
            reasons.append(f"{et}_expects_prior_send_marker")

    if et == LifecycleEventType.QUALIFIED:
        if current_outreach_state not in {"WARM", "ENGAGED"}:
            reasons.append("qualified_only_from_warm_or_engaged")

    if et == LifecycleEventType.CLOSED_WON:
        if current_outreach_state not in {"QUALIFIED", "ENGAGED"}:
            reasons.append("closed_won_only_from_qualified_or_engaged")

    if reasons:
        raise LifecycleEventValidationError(reasons)
