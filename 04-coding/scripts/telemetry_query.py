"""
Deterministic telemetry query primitives (Phase 3 foundation).

Pure in-memory query helpers over normalized telemetry events and replay outputs.

Design constraints:
- Pure / side-effect free: no I/O, no DB, no background workers
- No caching layer or mutable global state
- Stable source ordering always preserved
- Identical inputs and queries produce identical outputs
- Fully additive: does NOT alter existing telemetry contracts or runtime flow
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from telemetry_normalizer import NormalizedEvent
from telemetry_replay import ExecutionTimeline, ReconstructedSpan, TimelineEntry

GroupField = Literal["category", "subtype", "severity", "timestamp"]
_INVALID = object()


@dataclass
class AggregateSummary:
    total_events: int
    counts_by_category: dict[str, int] = field(default_factory=dict)
    counts_by_subtype: dict[str, int] = field(default_factory=dict)
    counts_by_severity: dict[str, int] = field(default_factory=dict)
    counts_by_timestamp: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_events": self.total_events,
            "counts_by_category": dict(self.counts_by_category),
            "counts_by_subtype": dict(self.counts_by_subtype),
            "counts_by_severity": dict(self.counts_by_severity),
            "counts_by_timestamp": dict(self.counts_by_timestamp),
        }


@dataclass
class GovernanceQueryResult:
    event_count: int
    events: list[NormalizedEvent] = field(default_factory=list)
    total_block_delta: int = 0
    hard_delta: int = 0
    soft_delta: int = 0
    info_delta: int = 0
    hard_event_ids: list[str] = field(default_factory=list)
    soft_event_ids: list[str] = field(default_factory=list)
    info_event_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_count": self.event_count,
            "events": [event.as_dict() for event in self.events],
            "total_block_delta": self.total_block_delta,
            "hard_delta": self.hard_delta,
            "soft_delta": self.soft_delta,
            "info_delta": self.info_delta,
            "hard_event_ids": list(self.hard_event_ids),
            "soft_event_ids": list(self.soft_event_ids),
            "info_event_ids": list(self.info_event_ids),
        }


@dataclass
class FailureQueryResult:
    event_count: int
    events: list[NormalizedEvent] = field(default_factory=list)
    total_retry_delta: int = 0
    total_failed_delta: int = 0
    total_abandoned_delta: int = 0
    retry_event_ids: list[str] = field(default_factory=list)
    failure_event_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_count": self.event_count,
            "events": [event.as_dict() for event in self.events],
            "total_retry_delta": self.total_retry_delta,
            "total_failed_delta": self.total_failed_delta,
            "total_abandoned_delta": self.total_abandoned_delta,
            "retry_event_ids": list(self.retry_event_ids),
            "failure_event_ids": list(self.failure_event_ids),
        }


@dataclass
class OperatorActivitySummary:
    event_count: int
    events: list[NormalizedEvent] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    total_pause_delta: int = 0
    total_lifecycle_delta: int = 0
    has_activity: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_count": self.event_count,
            "events": [event.as_dict() for event in self.events],
            "event_ids": list(self.event_ids),
            "total_pause_delta": self.total_pause_delta,
            "total_lifecycle_delta": self.total_lifecycle_delta,
            "has_activity": self.has_activity,
        }


@dataclass
class TimelineQueryView:
    total_entries: int
    entries: list[TimelineEntry] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    start_position: int | None = None
    end_position: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_entries": self.total_entries,
            "entries": [entry.as_dict() for entry in self.entries],
            "event_ids": list(self.event_ids),
            "start_position": self.start_position,
            "end_position": self.end_position,
        }


@dataclass
class SpanQueryView:
    total_spans: int
    spans: list[ReconstructedSpan] = field(default_factory=list)
    span_ids: list[str] = field(default_factory=list)
    start_position: int | None = None
    end_position: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_spans": self.total_spans,
            "spans": [span.as_dict() for span in self.spans],
            "span_ids": list(self.span_ids),
            "start_position": self.start_position,
            "end_position": self.end_position,
        }


def _as_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    return 0


def _coerce_list(values: Iterable[Any] | Any | None) -> list[Any]:
    if values is None or isinstance(values, (str, bytes)):
        return []
    try:
        return list(values)
    except TypeError:
        return []


def _coerce_events(events: Iterable[NormalizedEvent] | None) -> list[NormalizedEvent]:
    if events is None or isinstance(events, (str, bytes)):
        return []
    try:
        return list(events)
    except TypeError:
        return []


def _normalize_selector(values: str | Iterable[str] | None) -> set[str] | None | object:
    if values is None:
        return None
    if isinstance(values, str):
        return {values}
    if isinstance(values, (bytes, bytearray)):
        return _INVALID
    try:
        normalized = list(values)
    except TypeError:
        return _INVALID
    if any(not isinstance(value, str) for value in normalized):
        return _INVALID
    return set(normalized)


def _timestamp_in_range(timestamp: str, start_timestamp: str | None, end_timestamp: str | None) -> bool:
    if start_timestamp is not None and timestamp < start_timestamp:
        return False
    if end_timestamp is not None and timestamp > end_timestamp:
        return False
    return True


def _is_valid_timestamp_range(start_timestamp: str | None, end_timestamp: str | None) -> bool:
    if start_timestamp is not None and not isinstance(start_timestamp, str):
        return False
    if end_timestamp is not None and not isinstance(end_timestamp, str):
        return False
    if start_timestamp is not None and end_timestamp is not None and start_timestamp > end_timestamp:
        return False
    return True


def _normalize_index(value: int | None) -> int | None | object:
    if value is None:
        return None
    if not isinstance(value, int) or value < 0:
        return _INVALID
    return value


def _empty_timeline_view(start: int | None = None, stop: int | None = None) -> TimelineQueryView:
    return TimelineQueryView(total_entries=0, entries=[], event_ids=[], start_position=start, end_position=stop)


def _empty_span_view(start: int | None = None, stop: int | None = None) -> SpanQueryView:
    return SpanQueryView(total_spans=0, spans=[], span_ids=[], start_position=start, end_position=stop)


def _empty_aggregate() -> AggregateSummary:
    return AggregateSummary(
        total_events=0,
        counts_by_category={},
        counts_by_subtype={},
        counts_by_severity={},
        counts_by_timestamp={},
    )


def _count_values(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def filter_events(
    events: Iterable[NormalizedEvent] | None,
    *,
    categories: str | Iterable[str] | None = None,
    subtypes: str | Iterable[str] | None = None,
    severities: str | Iterable[str] | None = None,
    start_timestamp: str | None = None,
    end_timestamp: str | None = None,
) -> list[NormalizedEvent]:
    """Return a new ordered event list filtered by exact-match selectors and timestamp range."""
    if not _is_valid_timestamp_range(start_timestamp, end_timestamp):
        return []

    category_selector = _normalize_selector(categories)
    subtype_selector = _normalize_selector(subtypes)
    severity_selector = _normalize_selector(severities)
    if _INVALID in (category_selector, subtype_selector, severity_selector):
        return []

    result: list[NormalizedEvent] = []
    for event in _coerce_events(events):
        if category_selector is not None and event.category not in category_selector:
            continue
        if subtype_selector is not None and event.subtype not in subtype_selector:
            continue
        if severity_selector is not None and event.severity not in severity_selector:
            continue
        if not _timestamp_in_range(event.timestamp, start_timestamp, end_timestamp):
            continue
        result.append(event)
    return result


def group_events(
    events: Iterable[NormalizedEvent] | None,
    *,
    by: GroupField = "category",
) -> dict[str, list[NormalizedEvent]]:
    """Return ordered groups keyed by a supported event field."""
    if by not in {"category", "subtype", "severity", "timestamp"}:
        return {}

    result: dict[str, list[NormalizedEvent]] = {}
    for event in _coerce_events(events):
        key = getattr(event, by)
        if key not in result:
            result[key] = []
        result[key].append(event)
    return result


def aggregate_events(events: Iterable[NormalizedEvent] | None) -> AggregateSummary:
    """Return deterministic aggregate counts over an event stream."""
    event_list = _coerce_events(events)
    if not event_list:
        return _empty_aggregate()
    return AggregateSummary(
        total_events=len(event_list),
        counts_by_category=_count_values([event.category for event in event_list]),
        counts_by_subtype=_count_values([event.subtype for event in event_list]),
        counts_by_severity=_count_values([event.severity for event in event_list]),
        counts_by_timestamp=_count_values([event.timestamp for event in event_list]),
    )


def query_governance(
    events: Iterable[NormalizedEvent] | None,
    *,
    severities: str | Iterable[str] | None = None,
    start_timestamp: str | None = None,
    end_timestamp: str | None = None,
) -> GovernanceQueryResult:
    """Return deterministic governance escalation extraction from an event stream."""
    governance_events = filter_events(
        events,
        categories="governance",
        severities=severities,
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
    )
    total_block_delta = hard_delta = soft_delta = info_delta = 0
    hard_event_ids: list[str] = []
    soft_event_ids: list[str] = []
    info_event_ids: list[str] = []

    for event in governance_events:
        severity_delta = event.payload.get("severity_delta") or {}
        hard = _as_int(severity_delta.get("hard"))
        soft = _as_int(severity_delta.get("soft"))
        info = _as_int(severity_delta.get("info"))
        total_block_delta += _as_int(event.payload.get("block_logs_delta"))
        hard_delta += hard
        soft_delta += soft
        info_delta += info
        if hard > 0:
            hard_event_ids.append(event.event_id)
        if soft > 0:
            soft_event_ids.append(event.event_id)
        if info > 0:
            info_event_ids.append(event.event_id)

    return GovernanceQueryResult(
        event_count=len(governance_events),
        events=governance_events,
        total_block_delta=total_block_delta,
        hard_delta=hard_delta,
        soft_delta=soft_delta,
        info_delta=info_delta,
        hard_event_ids=hard_event_ids,
        soft_event_ids=soft_event_ids,
        info_event_ids=info_event_ids,
    )


def query_failures(
    events: Iterable[NormalizedEvent] | None,
    *,
    start_timestamp: str | None = None,
    end_timestamp: str | None = None,
) -> FailureQueryResult:
    """Return deterministic retry/failure extraction from an event stream."""
    failure_events = filter_events(
        events,
        subtypes="retries_failures",
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
    )
    retry_event_ids: list[str] = []
    failure_event_ids: list[str] = []
    total_retry_delta = total_failed_delta = total_abandoned_delta = 0

    for event in failure_events:
        retries = _as_int(event.payload.get("jobs_retry_sum_delta"))
        failed = _as_int(event.payload.get("failed_status_delta"))
        abandoned = _as_int(event.payload.get("abandoned_status_delta"))
        total_retry_delta += retries
        total_failed_delta += failed
        total_abandoned_delta += abandoned
        if retries > 0:
            retry_event_ids.append(event.event_id)
        if failed > 0 or abandoned > 0:
            failure_event_ids.append(event.event_id)

    return FailureQueryResult(
        event_count=len(failure_events),
        events=failure_events,
        total_retry_delta=total_retry_delta,
        total_failed_delta=total_failed_delta,
        total_abandoned_delta=total_abandoned_delta,
        retry_event_ids=retry_event_ids,
        failure_event_ids=failure_event_ids,
    )


def query_operator_activity(
    events: Iterable[NormalizedEvent] | None,
    *,
    start_timestamp: str | None = None,
    end_timestamp: str | None = None,
) -> OperatorActivitySummary:
    """Return deterministic operator intervention extraction from an event stream."""
    operator_events = filter_events(
        events,
        subtypes="operator_interventions",
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
    )
    total_pause_delta = 0
    total_lifecycle_delta = 0
    for event in operator_events:
        total_pause_delta += _as_int(event.payload.get("operator_pause_blocks_delta"))
        total_lifecycle_delta += _as_int(event.payload.get("operator_lifecycle_events_delta"))
    return OperatorActivitySummary(
        event_count=len(operator_events),
        events=operator_events,
        event_ids=[event.event_id for event in operator_events],
        total_pause_delta=total_pause_delta,
        total_lifecycle_delta=total_lifecycle_delta,
        has_activity=(total_pause_delta > 0 or total_lifecycle_delta > 0),
    )


def slice_timeline(
    timeline: ExecutionTimeline | Iterable[TimelineEntry] | None,
    *,
    start: int | None = None,
    stop: int | None = None,
    categories: str | Iterable[str] | None = None,
    subtypes: str | Iterable[str] | None = None,
    severities: str | Iterable[str] | None = None,
    start_timestamp: str | None = None,
    end_timestamp: str | None = None,
) -> TimelineQueryView:
    """Return a deterministic filtered/sliced timeline view."""
    normalized_start = _normalize_index(start)
    normalized_stop = _normalize_index(stop)
    if _INVALID in (normalized_start, normalized_stop):
        return _empty_timeline_view(start, stop)
    if (
        normalized_start is not None
        and normalized_stop is not None
        and normalized_start > normalized_stop
    ):
        return _empty_timeline_view(start, stop)
    if not _is_valid_timestamp_range(start_timestamp, end_timestamp):
        return _empty_timeline_view(start, stop)

    category_selector = _normalize_selector(categories)
    subtype_selector = _normalize_selector(subtypes)
    severity_selector = _normalize_selector(severities)
    if _INVALID in (category_selector, subtype_selector, severity_selector):
        return _empty_timeline_view(start, stop)

    entries = list(timeline.entries) if isinstance(timeline, ExecutionTimeline) else _coerce_list(timeline)
    sliced_entries = entries[slice(normalized_start, normalized_stop)]
    result: list[TimelineEntry] = []
    for entry in sliced_entries:
        if category_selector is not None and entry.category not in category_selector:
            continue
        if subtype_selector is not None and entry.subtype not in subtype_selector:
            continue
        if severity_selector is not None and entry.severity not in severity_selector:
            continue
        if not _timestamp_in_range(entry.timestamp, start_timestamp, end_timestamp):
            continue
        result.append(entry)
    return TimelineQueryView(
        total_entries=len(result),
        entries=result,
        event_ids=[entry.event_id for entry in result],
        start_position=normalized_start,
        end_position=normalized_stop,
    )


def slice_spans(
    spans: ExecutionTimeline | Iterable[ReconstructedSpan] | None,
    *,
    start: int | None = None,
    stop: int | None = None,
    categories: str | Iterable[str] | None = None,
    start_timestamp: str | None = None,
    end_timestamp: str | None = None,
) -> SpanQueryView:
    """Return a deterministic filtered/sliced span view."""
    normalized_start = _normalize_index(start)
    normalized_stop = _normalize_index(stop)
    if _INVALID in (normalized_start, normalized_stop):
        return _empty_span_view(start, stop)
    if (
        normalized_start is not None
        and normalized_stop is not None
        and normalized_start > normalized_stop
    ):
        return _empty_span_view(start, stop)
    if not _is_valid_timestamp_range(start_timestamp, end_timestamp):
        return _empty_span_view(start, stop)

    category_selector = _normalize_selector(categories)
    if category_selector is _INVALID:
        return _empty_span_view(start, stop)

    span_list = list(spans.spans) if isinstance(spans, ExecutionTimeline) else _coerce_list(spans)
    sliced_spans = span_list[slice(normalized_start, normalized_stop)]
    result: list[ReconstructedSpan] = []
    for span in sliced_spans:
        if category_selector is not None and not any(category in category_selector for category in span.category_set):
            continue
        if not _timestamp_in_range(span.start_timestamp, start_timestamp, end_timestamp):
            continue
        result.append(span)
    return SpanQueryView(
        total_spans=len(result),
        spans=result,
        span_ids=[span.span_id for span in result],
        start_position=normalized_start,
        end_position=normalized_stop,
    )
