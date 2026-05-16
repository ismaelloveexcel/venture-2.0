"""
Deterministic telemetry replay and timeline reconstruction layer (Phase 2 continuation).

Derives replayable execution timelines from normalized Phase 1 telemetry events produced
by :mod:`telemetry_normalizer`.

Design constraints:
- Pure / side-effect free: no I/O, no DB, no background workers
- No wall-clock reads
- No UUID/random generation (span_id is sha256-based, derived from event IDs)
- No mutable global state
- Identical inputs always produce identical outputs
- Stable source ordering always preserved
- Fully additive: does NOT modify runtime orchestration flow or emission behaviour
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Sequence

from telemetry_normalizer import NormalizedEvent

# ---------------------------------------------------------------------------
# Output structures
# ---------------------------------------------------------------------------


@dataclass
class TimelineEntry:
    """A single ordered entry in the reconstructed execution timeline.

    ``summary`` is a human-readable, deterministic description derived
    entirely from the event's ``subtype`` and ``payload``.
    """

    position: int
    event_id: str
    timestamp: str
    category: str
    subtype: str
    severity: str
    summary: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "category": self.category,
            "subtype": self.subtype,
            "severity": self.severity,
            "summary": self.summary,
        }


@dataclass
class ReconstructedSpan:
    """A logical execution span grouping a set of temporally adjacent events.

    For Phase 1 telemetry, all events in a single pipeline run share the same
    ``timestamp`` (``pipeline_started_at_utc``).  When multiple distinct
    timestamps appear in the event stream, multiple spans are produced —
    one per unique timestamp, preserving the source ordering of events.

    ``span_id`` is a deterministic sha256 hash of the sorted event_id list so
    that identical event sets always produce the same span identifier.
    """

    span_id: str
    start_timestamp: str
    end_timestamp: str  # == start_timestamp when no end-event data is available
    event_ids: list[str]
    category_set: list[str]  # sorted unique categories present in this span

    def as_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "event_ids": list(self.event_ids),
            "category_set": list(self.category_set),
        }


@dataclass
class GovernanceEscalationSummary:
    """Rollup of governance block deltas by severity.

    ``hard_event_ids`` lists the ``event_id`` of every governance_blocks event
    that contributed at least one HARD-severity block delta, enabling callers
    to locate those events in the timeline.
    """

    total_block_delta: int
    hard_delta: int
    soft_delta: int
    info_delta: int
    hard_event_ids: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_block_delta": self.total_block_delta,
            "hard_delta": self.hard_delta,
            "soft_delta": self.soft_delta,
            "info_delta": self.info_delta,
            "hard_event_ids": list(self.hard_event_ids),
        }


@dataclass
class RetryFailureSummary:
    """Retry and failure sequence visibility.

    ``retry_event_ids`` and ``failure_event_ids`` list the ``event_id`` values
    of events that contributed non-zero retry, failure, or abandoned deltas
    respectively.
    """

    total_retry_delta: int
    total_failed_delta: int
    total_abandoned_delta: int
    retry_event_ids: list[str]
    failure_event_ids: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_retry_delta": self.total_retry_delta,
            "total_failed_delta": self.total_failed_delta,
            "total_abandoned_delta": self.total_abandoned_delta,
            "retry_event_ids": list(self.retry_event_ids),
            "failure_event_ids": list(self.failure_event_ids),
        }


@dataclass
class ExecutionSummary:
    """High-level execution summary derived purely from the event stream."""

    event_count: int
    categories_observed: list[str]  # sorted unique categories
    queue_delta: int  # net jobs_total_delta across all queue_operations events
    state_transitions_delta: int  # net lifecycle_events_delta
    has_operator_interventions: bool
    governance: GovernanceEscalationSummary
    retries: RetryFailureSummary

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_count": self.event_count,
            "categories_observed": list(self.categories_observed),
            "queue_delta": self.queue_delta,
            "state_transitions_delta": self.state_transitions_delta,
            "has_operator_interventions": self.has_operator_interventions,
            "governance": self.governance.as_dict(),
            "retries": self.retries.as_dict(),
        }


@dataclass
class ExecutionTimeline:
    """Top-level deterministic replay result.

    ``entries``            — ordered timeline entries, one per source event.
    ``spans``              — reconstructed spans grouped by timestamp bucket.
    ``groups_by_category`` — mapping of category slug → ordered event_id list.
    ``groups_by_subtype``  — mapping of subtype slug → ordered event_id list.
    ``summary``            — high-level aggregated execution summary.
    """

    entries: list[TimelineEntry]
    spans: list[ReconstructedSpan]
    groups_by_category: dict[str, list[str]]
    groups_by_subtype: dict[str, list[str]]
    summary: ExecutionSummary

    def as_dict(self) -> dict[str, Any]:
        return {
            "entries": [e.as_dict() for e in self.entries],
            "spans": [s.as_dict() for s in self.spans],
            "groups_by_category": {k: list(v) for k, v in self.groups_by_category.items()},
            "groups_by_subtype": {k: list(v) for k, v in self.groups_by_subtype.items()},
            "summary": self.summary.as_dict(),
        }


# ---------------------------------------------------------------------------
# Internal helpers — all pure functions
# ---------------------------------------------------------------------------


def _as_int(value: Any) -> int:
    """Safely coerce a payload value to int, returning 0 for None or non-numeric types.

    Phase 1 normalized events carry Pydantic-validated ``int | None`` delta
    fields, so in normal operation ``value`` is always ``int`` or ``None``.
    This helper guards against unexpected ``str`` or other types that could
    arise if callers construct :class:`~telemetry_normalizer.NormalizedEvent`
    objects manually with arbitrary payloads.
    """
    if isinstance(value, int):
        return value
    return 0


def _span_id(event_ids: list[str]) -> str:
    """Deterministic sha256 span identifier derived from sorted event IDs."""
    key = json.dumps(sorted(event_ids), separators=(",", ":"))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _derive_summary(subtype: str, severity: str, payload: dict[str, Any]) -> str:
    """Derive a human-readable, deterministic summary string from event fields."""
    if subtype == "queue_operations":
        raw = payload.get("jobs_total_delta")
        if raw is None:
            return "Queue operations: no delta recorded"
        delta = _as_int(raw)
        sign = "+" if delta >= 0 else ""
        return f"Queue delta: {sign}{delta} job(s)"

    if subtype == "state_transitions":
        raw = payload.get("lifecycle_events_delta")
        if raw is None:
            return "State transitions: no delta recorded"
        return f"State transitions: {_as_int(raw)} lifecycle event(s)"

    if subtype == "governance_blocks":
        raw = payload.get("block_logs_delta")
        if raw is None:
            delta_str = "no delta recorded"
        else:
            delta = _as_int(raw)
            sign = "+" if delta >= 0 else ""
            delta_str = f"{sign}{delta}"
        sev = f" ({severity})" if severity else ""
        return f"Governance blocks: {delta_str}{sev}"

    if subtype == "retries_failures":
        retries = _as_int(payload.get("jobs_retry_sum_delta"))
        failed = _as_int(payload.get("failed_status_delta"))
        abandoned = _as_int(payload.get("abandoned_status_delta"))
        return f"Retries/failures: {retries} retry(ies), {failed} failure(s), {abandoned} abandoned"

    if subtype == "operator_interventions":
        pauses = _as_int(payload.get("operator_pause_blocks_delta"))
        lc = _as_int(payload.get("operator_lifecycle_events_delta"))
        return f"Operator interventions: {pauses} pause(s), {lc} lifecycle event(s)"

    return f"{subtype}: event recorded"


def _build_timeline_entries(events: Sequence[NormalizedEvent]) -> list[TimelineEntry]:
    return [
        TimelineEntry(
            position=pos,
            event_id=ev.event_id,
            timestamp=ev.timestamp,
            category=ev.category,
            subtype=ev.subtype,
            severity=ev.severity,
            summary=_derive_summary(ev.subtype, ev.severity, ev.payload),
        )
        for pos, ev in enumerate(events)
    ]


def _build_spans(events: Sequence[NormalizedEvent]) -> list[ReconstructedSpan]:
    """Group events by timestamp bucket into ordered spans.

    Events with the same timestamp are collapsed into a single span.  The
    order of spans reflects the first-seen order of each new timestamp value,
    preserving source ordering.
    """
    # ordered dict of timestamp → list[NormalizedEvent]
    buckets: dict[str, list[NormalizedEvent]] = {}
    for ev in events:
        ts = ev.timestamp or ""
        if ts not in buckets:
            buckets[ts] = []
        buckets[ts].append(ev)

    spans: list[ReconstructedSpan] = []
    for ts, bucket_events in buckets.items():
        ids = [ev.event_id for ev in bucket_events]
        categories = sorted({ev.category for ev in bucket_events})
        spans.append(
            ReconstructedSpan(
                span_id=_span_id(ids),
                start_timestamp=ts,
                end_timestamp=ts,  # Phase 1 events share a single timestamp per run
                event_ids=ids,
                category_set=categories,
            )
        )
    return spans


def _build_groups(events: Sequence[NormalizedEvent]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return (groups_by_category, groups_by_subtype) as ordered dicts of event_id lists."""
    by_cat: dict[str, list[str]] = {}
    by_sub: dict[str, list[str]] = {}
    for ev in events:
        if ev.category not in by_cat:
            by_cat[ev.category] = []
        by_cat[ev.category].append(ev.event_id)
        if ev.subtype not in by_sub:
            by_sub[ev.subtype] = []
        by_sub[ev.subtype].append(ev.event_id)
    return by_cat, by_sub


def _build_governance_summary(events: Sequence[NormalizedEvent]) -> GovernanceEscalationSummary:
    total = hard = soft = info = 0
    hard_ids: list[str] = []
    for ev in events:
        if ev.subtype != "governance_blocks":
            continue
        payload = ev.payload
        total += _as_int(payload.get("block_logs_delta"))
        sev_d = payload.get("severity_delta") or {}
        h = _as_int(sev_d.get("hard"))
        s = _as_int(sev_d.get("soft"))
        i = _as_int(sev_d.get("info"))
        hard += h
        soft += s
        info += i
        if h > 0:
            hard_ids.append(ev.event_id)
    return GovernanceEscalationSummary(
        total_block_delta=total,
        hard_delta=hard,
        soft_delta=soft,
        info_delta=info,
        hard_event_ids=hard_ids,
    )


def _build_retry_summary(events: Sequence[NormalizedEvent]) -> RetryFailureSummary:
    total_retry = total_failed = total_abandoned = 0
    retry_ids: list[str] = []
    failure_ids: list[str] = []
    for ev in events:
        if ev.subtype != "retries_failures":
            continue
        payload = ev.payload
        retries = _as_int(payload.get("jobs_retry_sum_delta"))
        failed = _as_int(payload.get("failed_status_delta"))
        abandoned = _as_int(payload.get("abandoned_status_delta"))
        total_retry += retries
        total_failed += failed
        total_abandoned += abandoned
        if retries > 0:
            retry_ids.append(ev.event_id)
        if failed > 0 or abandoned > 0:
            failure_ids.append(ev.event_id)
    return RetryFailureSummary(
        total_retry_delta=total_retry,
        total_failed_delta=total_failed,
        total_abandoned_delta=total_abandoned,
        retry_event_ids=retry_ids,
        failure_event_ids=failure_ids,
    )


def _build_summary(events: Sequence[NormalizedEvent]) -> ExecutionSummary:
    categories = sorted({ev.category for ev in events})
    queue_delta = sum(
        _as_int(ev.payload.get("jobs_total_delta"))
        for ev in events
        if ev.subtype == "queue_operations"
    )
    state_delta = sum(
        _as_int(ev.payload.get("lifecycle_events_delta"))
        for ev in events
        if ev.subtype == "state_transitions"
    )
    has_operator = any(
        (_as_int(ev.payload.get("operator_pause_blocks_delta")) > 0
         or _as_int(ev.payload.get("operator_lifecycle_events_delta")) > 0)
        for ev in events
        if ev.subtype == "operator_interventions"
    )
    return ExecutionSummary(
        event_count=len(events),
        categories_observed=categories,
        queue_delta=queue_delta,
        state_transitions_delta=state_delta,
        has_operator_interventions=has_operator,
        governance=_build_governance_summary(events),
        retries=_build_retry_summary(events),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def replay_timeline(events: Sequence[NormalizedEvent]) -> ExecutionTimeline:
    """Reconstruct a deterministic execution timeline from normalized telemetry events.

    Accepts any sequence of :class:`~telemetry_normalizer.NormalizedEvent` objects
    (typically the output of :func:`~telemetry_normalizer.normalize_phase1_telemetry`).

    Returns a fully-populated :class:`ExecutionTimeline` on every call.  All
    returned objects are independent of the input sequence — callers may safely
    mutate the returned structures without affecting subsequent calls.

    Guarantees:

    * **Deterministic** — identical input sequences produce identical timelines.
    * **Stable ordering** — timeline entries appear in source-event order.
    * **No side effects** — no I/O, no DB writes, no wall-clock reads.
    * **Additive** — does not alter runtime orchestration or telemetry emission.
    """
    # Snapshot into a concrete list so we iterate exactly once in a fixed order.
    ev_list = list(events)

    entries = _build_timeline_entries(ev_list)
    spans = _build_spans(ev_list)
    by_cat, by_sub = _build_groups(ev_list)
    summary = _build_summary(ev_list)

    return ExecutionTimeline(
        entries=entries,
        spans=spans,
        groups_by_category=by_cat,
        groups_by_subtype=by_sub,
        summary=summary,
    )


def group_by_category(events: Sequence[NormalizedEvent]) -> dict[str, list[NormalizedEvent]]:
    """Return a new dict mapping category slug → ordered list of events.

    Source ordering is preserved within each group.  Returns independent
    lists; mutating the result does not affect subsequent calls.
    """
    result: dict[str, list[NormalizedEvent]] = {}
    for ev in events:
        if ev.category not in result:
            result[ev.category] = []
        result[ev.category].append(ev)
    return result


def group_by_subtype(events: Sequence[NormalizedEvent]) -> dict[str, list[NormalizedEvent]]:
    """Return a new dict mapping subtype slug → ordered list of events.

    Source ordering is preserved within each group.  Returns independent
    lists; mutating the result does not affect subsequent calls.
    """
    result: dict[str, list[NormalizedEvent]] = {}
    for ev in events:
        if ev.subtype not in result:
            result[ev.subtype] = []
        result[ev.subtype].append(ev)
    return result
