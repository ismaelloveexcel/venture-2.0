"""
Prospect send lifecycle state machine (Phase B) — audit/replay layer.

States: READY → SENT → REPLIED | SUPPRESSED | FAILED
Immutable transitions only (caller never mutates past state in-place).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Literal

STATE_ENGINE_VERSION = "phase_b_1"

ProspectState = Literal["READY", "SENT", "REPLIED", "SUPPRESSED", "FAILED"]
TransitionEvent = Literal["SEND", "REPLY", "SUPPRESS", "FAIL"]

_ALLOWED: dict[str, frozenset[str]] = {
    "READY": frozenset({"SENT"}),
    "SENT": frozenset({"REPLIED", "SUPPRESSED", "FAILED"}),
}


def transition(current: ProspectState, event: TransitionEvent) -> ProspectState:
    """Apply one transition; raises ValueError on illegal paths."""
    nxt = _peek_next(current, event)
    if nxt is None:
        raise ValueError(f"invalid transition: {current!r} + {event!r}")
    return nxt  # type: ignore[return-value]


def _peek_next(current: ProspectState, event: TransitionEvent) -> str | None:
    if current == "READY" and event == "SEND":
        return "SENT"
    if current == "SENT" and event == "REPLY":
        return "REPLIED"
    if current == "SENT" and event == "SUPPRESS":
        return "SUPPRESSED"
    if current == "SENT" and event == "FAIL":
        return "FAILED"
    return None


def validate_path(states: Iterable[ProspectState]) -> None:
    """Replay audit: each step must be legal from the previous node."""
    prev: ProspectState | None = None
    for s in states:
        if prev is None:
            if s != "READY":
                raise ValueError(f"replay must start at READY, got {s!r}")
        else:
            if s not in _ALLOWED.get(prev, frozenset()):
                raise ValueError(f"illegal replay step {prev!r} -> {s!r}")
        prev = s


@dataclass(frozen=True)
class ReplayRow:
    """Normalized row from snapshots + suppression audit."""

    ts: str
    source: str
    payload: dict[str, Any]


def replay_from_artifacts(
    *,
    snapshots: list[dict[str, Any]],
    suppression_rows: list[dict[str, Any]],
) -> tuple[list[ReplayRow], str]:
    """
    Merge funnel_health_snapshots (run_report payload_json / schema rows) with
    suppression_history rows for chronological audit narrative.
    """
    rows: list[ReplayRow] = []
    for snap in snapshots:
        ts = str(snap.get("send_timestamp") or snap.get("run_at") or "")
        rows.append(ReplayRow(ts=ts, source="funnel_health_snapshot", payload=dict(snap)))
    for sup in suppression_rows:
        ts = str(sup.get("created_at") or "")
        rows.append(ReplayRow(ts=ts, source="suppression_history", payload=dict(sup)))
    rows.sort(key=lambda r: r.ts)
    digest = json.dumps([asdict(r) for r in rows], default=str, sort_keys=True)
    return rows, digest


def detect_drift(*, expected_version: str, observed_version: str) -> bool:
    """True when stored version does not match engine (audit flag)."""
    return (observed_version or "").strip() != (expected_version or "").strip()
