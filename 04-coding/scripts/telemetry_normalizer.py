"""
Deterministic telemetry normalization layer (Phase 2 foundation).

Converts raw Phase 1 telemetry payloads into stable canonical event records.

Design constraints:
- Pure / side-effect free: no I/O, no DB, no background workers
- No wall-clock mutation during normalization
- No runtime UUID generation (event_id is sha256-based)
- Identical inputs always produce identical outputs
- Append-only semantics: each call returns a new independent list
- Does NOT modify runtime execution flow
- Does NOT expand beyond Phase 1 event categories
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from run_report_schema import (
    Phase1GovernanceBlocksEventModel,
    Phase1StructuredTelemetryModel,
)

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical event record
# ---------------------------------------------------------------------------

_SOURCE = "phase1_structured"

_CATEGORY_MAP: dict[str, str] = {
    "queue_operations": "queue",
    "state_transitions": "state",
    "governance_blocks": "governance",
    "retries_failures": "health",
    "operator_interventions": "operator",
}


@dataclass
class NormalizedEvent:
    """Canonical normalized telemetry event.

    Treat as immutable after construction — fields are intentionally not
    protected by ``frozen=True`` so that a plain ``dict`` payload remains
    JSON-serialisable without extra conversion.
    """

    event_id: str
    timestamp: str
    category: str
    subtype: str
    severity: str  # "HARD" | "SOFT" | "INFO" | ""
    source: str
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return a plain dict representation."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "category": self.category,
            "subtype": self.subtype,
            "severity": self.severity,
            "source": self.source,
            "payload": dict(self.payload),
        }


# ---------------------------------------------------------------------------
# Internal helpers — all pure functions
# ---------------------------------------------------------------------------


def _deterministic_event_id(
    category: str,
    subtype: str,
    position: int,
    payload: dict[str, Any],
) -> str:
    """Return a deterministic sha256-hex event_id from stable, sorted inputs.

    The sha256 is computed over a canonical JSON representation so that:
    - identical ``(category, subtype, position, payload)`` tuples always map to
      the same id;
    - different tuples (including different positions) map to different ids.
    """
    key_parts: dict[str, Any] = {
        "category": category,
        "position": position,
        "source": _SOURCE,
        "subtype": subtype,
        "payload": payload,
    }
    canonical = json.dumps(key_parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _extract_severity(event: Any) -> str:
    """Return the dominant severity string for a governance_blocks event."""
    if not isinstance(event, Phase1GovernanceBlocksEventModel):
        return ""
    delta = event.severity_delta
    if delta is None:
        return ""
    if delta.hard > 0:
        return "HARD"
    if delta.soft > 0:
        return "SOFT"
    if delta.info > 0:
        return "INFO"
    return ""


def _normalize_payload(event: Any) -> dict[str, Any]:
    """Extract a minimal normalized payload dict from a Phase1 event model.

    Strips the ``event`` discriminator key (already captured in ``subtype``)
    and removes ``None`` values to keep payloads compact.
    """
    raw: dict[str, Any] = event.model_dump()
    raw.pop("event", None)
    return {k: v for k, v in raw.items() if v is not None}


def _normalize_structured(
    model: Phase1StructuredTelemetryModel,
) -> list[NormalizedEvent]:
    """Produce canonical NormalizedEvent records from a validated model.

    Ordering: events appear in their original Phase 1 list order (stable).
    """
    timestamp: str = ""
    if model.window is not None:
        timestamp = model.window.pipeline_started_at_utc or ""

    events: list[NormalizedEvent] = []
    for position, raw_event in enumerate(model.events):
        subtype: str = raw_event.event
        category: str = _CATEGORY_MAP.get(subtype, "unknown")
        severity: str = _extract_severity(raw_event)
        payload: dict[str, Any] = _normalize_payload(raw_event)
        event_id: str = _deterministic_event_id(category, subtype, position, payload)
        events.append(
            NormalizedEvent(
                event_id=event_id,
                timestamp=timestamp,
                category=category,
                subtype=subtype,
                severity=severity,
                source=_SOURCE,
                payload=payload,
            )
        )
    return events


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_phase1_telemetry(
    data: Phase1StructuredTelemetryModel | dict[str, Any] | None,
) -> list[NormalizedEvent]:
    """Convert Phase 1 telemetry into a list of canonical :class:`NormalizedEvent` records.

    Accepts:

    * :class:`~run_report_schema.Phase1StructuredTelemetryModel` — already validated model.
    * ``dict`` — either a raw ``phase1_structured`` sub-dict *or* a full pipeline
      telemetry payload that contains a ``"phase1_structured"`` key; auto-validated.
    * ``None`` or any other type — returns an empty list (malformed input).

    Returns a **new list** on every call; callers may append to their own accumulator
    without risking shared-state mutations (append-only semantics).

    Guarantees:

    * **Deterministic** — identical inputs produce identical output lists.
    * **Ordering** — events appear in Phase 1 source order (stable).
    * **No side effects** — no I/O, no DB writes, no wall-clock reads.
    """
    if data is None:
        return []

    if isinstance(data, Phase1StructuredTelemetryModel):
        return _normalize_structured(data)

    if not isinstance(data, dict):
        return []

    # Support both the full pipeline telemetry envelope and the bare
    # phase1_structured sub-dict.
    inner: Any = data
    if "phase1_structured" in data:
        candidate = data["phase1_structured"]
        if isinstance(candidate, dict):
            inner = candidate
        elif isinstance(candidate, Phase1StructuredTelemetryModel):
            return _normalize_structured(candidate)
        else:
            # Malformed inner value — cannot normalise
            return []

    try:
        model = Phase1StructuredTelemetryModel.model_validate(inner)
    except Exception as exc:  # noqa: BLE001
        _logger.debug(
            "telemetry_normalizer: phase1_structured validation failed (%s); "
            "returning empty list — may indicate schema evolution or malformed input",
            exc,
        )
        return []

    return _normalize_structured(model)
