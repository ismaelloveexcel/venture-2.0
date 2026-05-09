"""
Deterministic, replayable outreach state reduction from ordered lifecycle events.

All outreach state changes should be derived from the lifecycle event stream so
behavior is observable and reproducible (re-run replay after logic updates).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from outreach_state_machine import next_state_from_signal, SIDE_STATES

# Bump when replay / validation rules change; stored per opportunity to detect drift.
STATE_ENGINE_VERSION = "1.2.0"


class LifecycleEventType:
    PROSPECT_LOADED = "prospect_loaded"
    EMAIL_ENRICHED = "email_enriched"
    MESSAGE_DRAFTED = "message_drafted"
    CTA_SELECTED = "cta_selected"
    OUTREACH_SENT = "outreach_sent"
    FOLLOWUP_SENT = "followup_sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    REPLIED = "replied"
    BOUNCED = "bounced"
    COMPLAINED = "complained"
    UNSUBSCRIBED = "unsubscribed"
    BLOCKED = "blocked"
    QUALIFIED = "qualified"
    DISQUALIFIED = "disqualified"
    NURTURE = "nurture"
    CLOSED_WON = "closed_won"
    NO_RESPONSE_DECAY = "no_response_decay"


@dataclass(frozen=True)
class LifecycleSnapshot:
    """Fold checkpoint: replay only events with id > after_event_id."""

    after_event_id: int
    outreach_state: str
    opened_count: int
    evidence_score: float


def _parse_payload(raw: str) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else {}
    except json.JSONDecodeError:
        return {}


def _replay_step(state: str, opened_count: int, event_type: str, payload_raw: str) -> Tuple[str, int]:
    payload = _parse_payload(payload_raw)
    et = (event_type or "").strip()

    if state in SIDE_STATES and et not in {LifecycleEventType.DISQUALIFIED, LifecycleEventType.NURTURE}:
        if et not in {LifecycleEventType.NURTURE, LifecycleEventType.DISQUALIFIED}:
            return state, opened_count

    if et in {LifecycleEventType.BOUNCED, LifecycleEventType.COMPLAINED, LifecycleEventType.UNSUBSCRIBED}:
        return next_state_from_signal(state, "disqualified"), opened_count
    if et == LifecycleEventType.DISQUALIFIED:
        return next_state_from_signal(state, "disqualified"), opened_count
    if et == LifecycleEventType.NURTURE:
        return next_state_from_signal(state, "nurture"), opened_count
    if et == LifecycleEventType.CLOSED_WON:
        return next_state_from_signal(state, "closed_won"), opened_count
    if et == LifecycleEventType.QUALIFIED:
        return next_state_from_signal(state, "qualified_pain_budget_timeline"), opened_count
    if et == LifecycleEventType.REPLIED:
        return next_state_from_signal(state, "reply_received"), opened_count
    if et == LifecycleEventType.CLICKED:
        return next_state_from_signal(state, "high_intent"), opened_count
    if et == LifecycleEventType.OPENED:
        opened_count += 1
        if opened_count >= 2 and state == "WARM":
            return next_state_from_signal(state, "high_intent"), opened_count
        return state, opened_count
    if et == LifecycleEventType.NO_RESPONSE_DECAY:
        return next_state_from_signal(state, "no_response_decay"), opened_count

    return state, opened_count


def replay_outreach_state_fold(
    events: List[Tuple[str, str]],
    initial_state: str = "COLD",
    initial_opened: int = 0,
) -> Tuple[str, int]:
    """Fold (event_type, payload_json) pairs into terminal state and open count."""
    state, opened = initial_state, initial_opened
    for event_type, payload_raw in events:
        state, opened = _replay_step(state, opened, event_type, payload_raw)
    return state, opened


def replay_outreach_state(events: List[Tuple[str, str]]) -> str:
    state, _ = replay_outreach_state_fold(events)
    return state


def replay_outreach_state_from_rows(
    rows: List[Tuple[int, str, str]],
    snapshot: Optional[LifecycleSnapshot] = None,
) -> Tuple[str, int]:
    """
    rows: (id, event_type, payload_json) ascending id.
    When snapshot is set, starts from snapshot fields and only applies tail rows.
    """
    if not snapshot:
        tail = [(t, p) for _, t, p in rows]
        return replay_outreach_state_fold(tail)
    tail = [(t, p) for eid, t, p in rows if eid > snapshot.after_event_id]
    return replay_outreach_state_fold(
        tail,
        initial_state=snapshot.outreach_state,
        initial_opened=snapshot.opened_count,
    )


def extract_evidence_score(events: List[Tuple[str, str]]) -> float:
    """Latest explicit evidence_confidence from message_drafted (or 0)."""
    last = 0.0
    for event_type, payload_raw in events:
        if (event_type or "").strip() != LifecycleEventType.MESSAGE_DRAFTED:
            continue
        payload = _parse_payload(payload_raw)
        try:
            last = float(payload.get("evidence_confidence", 0.0))
        except (TypeError, ValueError):
            continue
    return last


def extract_evidence_score_from_rows(
    rows: List[Tuple[int, str, str]],
    snapshot: Optional[LifecycleSnapshot] = None,
) -> float:
    last = snapshot.evidence_score if snapshot else 0.0
    cutoff = snapshot.after_event_id if snapshot else 0
    for eid, event_type, payload_raw in rows:
        if eid <= cutoff:
            continue
        if (event_type or "").strip() != LifecycleEventType.MESSAGE_DRAFTED:
            continue
        payload = _parse_payload(payload_raw)
        try:
            last = float(payload.get("evidence_confidence", 0.0))
        except (TypeError, ValueError):
            continue
    return last


def last_block_reason(events: List[Tuple[str, str]]) -> str:
    """Most recent blocked event reason, if any."""
    reason = ""
    for event_type, payload_raw in events:
        if (event_type or "").strip() != LifecycleEventType.BLOCKED:
            continue
        payload = _parse_payload(payload_raw)
        reason = str(payload.get("reason", "") or payload.get("status_reason", "") or "")
    return reason
