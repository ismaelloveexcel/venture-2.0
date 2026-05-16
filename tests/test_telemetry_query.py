"""Tests for the deterministic telemetry query engine (Phase 3 foundation)."""

from __future__ import annotations

import json

from telemetry_normalizer import NormalizedEvent, normalize_phase1_telemetry
from telemetry_query import (
    AggregateSummary,
    FailureQueryResult,
    GovernanceQueryResult,
    OperatorActivitySummary,
    SpanQueryView,
    TimelineQueryView,
    aggregate_events,
    filter_events,
    group_events,
    query_failures,
    query_governance,
    query_operator_activity,
    slice_spans,
    slice_timeline,
)
from telemetry_replay import replay_timeline

_TS1 = "2026-05-16T10:00:00Z"
_TS2 = "2026-05-16T11:00:00Z"
_TS3 = "2026-05-16T12:00:00Z"


def _phase1_raw() -> dict[str, object]:
    return {
        "version": 1,
        "window": {
            "pipeline_started_at_utc": _TS1,
            "pipeline_finished_at_utc": "2026-05-16T10:01:00Z",
        },
        "events": [
            {"event": "queue_operations", "jobs_total_delta": 3},
            {"event": "state_transitions", "lifecycle_events_delta": 5},
            {
                "event": "governance_blocks",
                "block_logs_delta": 2,
                "severity_delta": {"hard": 1, "soft": 0, "info": 1},
            },
            {
                "event": "retries_failures",
                "jobs_retry_sum_delta": 2,
                "failed_status_delta": 1,
                "abandoned_status_delta": 0,
            },
            {
                "event": "operator_interventions",
                "operator_pause_blocks_delta": 1,
                "operator_lifecycle_events_delta": 2,
            },
        ],
    }


def _query_events() -> list[NormalizedEvent]:
    base = normalize_phase1_telemetry(_phase1_raw())
    governance_soft = NormalizedEvent(
        event_id="b" * 64,
        timestamp=_TS2,
        category="governance",
        subtype="governance_blocks",
        severity="SOFT",
        source="phase1_structured",
        payload={"block_logs_delta": 1, "severity_delta": {"hard": 0, "soft": 1, "info": 0}},
    )
    retries_abandoned = NormalizedEvent(
        event_id="c" * 64,
        timestamp=_TS2,
        category="health",
        subtype="retries_failures",
        severity="",
        source="phase1_structured",
        payload={"jobs_retry_sum_delta": 0, "failed_status_delta": 0, "abandoned_status_delta": 2},
    )
    queue_late = NormalizedEvent(
        event_id="d" * 64,
        timestamp=_TS3,
        category="queue",
        subtype="queue_operations",
        severity="",
        source="phase1_structured",
        payload={"jobs_total_delta": -1},
    )
    return [*base, governance_soft, retries_abandoned, queue_late]


def test_filter_events_by_category_preserves_order():
    events = _query_events()
    filtered = filter_events(events, categories="governance")
    assert [event.event_id for event in filtered] == [events[2].event_id, events[5].event_id]


def test_filter_events_by_subtype_and_severity():
    events = _query_events()
    filtered = filter_events(events, subtypes="governance_blocks", severities="SOFT")
    assert [event.event_id for event in filtered] == [events[5].event_id]


def test_filter_events_by_timestamp_range_inclusive():
    events = _query_events()
    filtered = filter_events(events, start_timestamp=_TS2, end_timestamp=_TS3)
    assert [event.event_id for event in filtered] == [events[5].event_id, events[6].event_id, events[7].event_id]


def test_filter_events_combines_selectors_with_and_semantics():
    events = _query_events()
    filtered = filter_events(events, categories="health", start_timestamp=_TS2, end_timestamp=_TS2)
    assert [event.event_id for event in filtered] == [events[6].event_id]


def test_filter_events_selector_order_does_not_change_output():
    events = _query_events()
    first = filter_events(events, categories=["governance", "health"])
    second = filter_events(events, categories=["health", "governance"])
    assert [event.event_id for event in first] == [event.event_id for event in second]


def test_filter_events_invalid_selector_type_returns_empty():
    events = _query_events()
    assert filter_events(events, categories=123) == []  # type: ignore[arg-type]


def test_filter_events_invalid_timestamp_range_returns_empty():
    events = _query_events()
    assert filter_events(events, start_timestamp=_TS3, end_timestamp=_TS1) == []


def test_filter_events_non_canonical_timestamp_range_returns_empty():
    events = _query_events()
    assert filter_events(events, start_timestamp="2026-05-16 11:00:00Z", end_timestamp=_TS3) == []
    assert filter_events(events, start_timestamp=_TS2, end_timestamp="2026-05-16T12:00:00+00:00") == []


def test_filter_events_excludes_non_canonical_event_timestamps_when_range_used():
    malformed = NormalizedEvent(
        event_id="f" * 64,
        timestamp="2026-05-16T11:00:00+00:00",
        category="health",
        subtype="retries_failures",
        severity="",
        source="phase1_structured",
        payload={"jobs_retry_sum_delta": 1},
    )
    filtered = filter_events([*_query_events(), malformed], start_timestamp=_TS1, end_timestamp=_TS3)
    assert all(event.event_id != malformed.event_id for event in filtered)


def test_filter_events_empty_input_returns_empty():
    assert filter_events([]) == []
    assert filter_events(None) == []


def test_group_events_by_category_and_order():
    events = _query_events()
    grouped = group_events(events, by="category")
    assert list(grouped.keys()) == ["governance", "health", "operator", "queue", "state"]
    assert [event.event_id for event in grouped["queue"]] == [events[0].event_id, events[7].event_id]


def test_group_events_by_severity_supports_empty_key():
    grouped = group_events(_query_events(), by="severity")
    assert list(grouped.keys()) == ["", "HARD", "SOFT"]


def test_group_events_invalid_key_returns_empty():
    assert group_events(_query_events(), by="not-real") == {}  # type: ignore[arg-type]


def test_group_events_unhashable_key_returns_empty():
    assert group_events(_query_events(), by=["category"]) == {}  # type: ignore[arg-type]


def test_aggregate_events_counts_correctly():
    summary = aggregate_events(_query_events())
    assert summary.total_events == 8
    assert summary.counts_by_category == {
        "governance": 2,
        "health": 2,
        "operator": 1,
        "queue": 2,
        "state": 1,
    }
    assert summary.counts_by_subtype["governance_blocks"] == 2
    assert summary.counts_by_severity[""] == 6
    assert summary.counts_by_timestamp == {_TS1: 5, _TS2: 2, _TS3: 1}


def test_aggregate_events_sorts_grouped_count_keys():
    summary = aggregate_events(_query_events())
    assert list(summary.counts_by_category.keys()) == ["governance", "health", "operator", "queue", "state"]
    assert list(summary.counts_by_timestamp.keys()) == [_TS1, _TS2, _TS3]


def test_aggregate_events_coerces_malformed_group_values():
    malformed = NormalizedEvent(
        event_id="g" * 64,
        timestamp=_TS1,
        category="queue",
        subtype="queue_operations",
        severity="",
        source="phase1_structured",
        payload={},
    )
    # Post-construction mutation is intentional to simulate malformed runtime objects
    # that bypass static typing but may still reach query helpers.
    malformed.category = ["bad"]  # type: ignore[assignment]
    malformed.subtype = {"x": 1}  # type: ignore[assignment]
    malformed.severity = ("tuple",)  # type: ignore[assignment]
    malformed.timestamp = {"ts": _TS1}  # type: ignore[assignment]
    summary = aggregate_events([malformed])
    assert summary.total_events == 1
    assert summary.counts_by_category == {"": 1}
    assert summary.counts_by_subtype == {"": 1}
    assert summary.counts_by_severity == {"": 1}
    assert summary.counts_by_timestamp == {"": 1}


def test_aggregate_events_empty_input_returns_zero_summary():
    summary = aggregate_events(None)
    assert summary == AggregateSummary(
        total_events=0,
        counts_by_category={},
        counts_by_subtype={},
        counts_by_severity={},
        counts_by_timestamp={},
    )


def test_query_governance_extracts_escalations():
    result = query_governance(_query_events())
    assert result.event_count == 2
    assert result.total_block_delta == 3
    assert result.hard_delta == 1
    assert result.soft_delta == 1
    assert result.info_delta == 1
    assert result.hard_event_ids == [_query_events()[2].event_id]
    assert result.soft_event_ids == [_query_events()[5].event_id]
    assert result.info_event_ids == [_query_events()[2].event_id]


def test_query_governance_supports_severity_filter():
    result = query_governance(_query_events(), severities="SOFT")
    assert result.event_count == 1
    assert [event.severity for event in result.events] == ["SOFT"]


def test_query_governance_malformed_range_returns_empty_result():
    result = query_governance(_query_events(), start_timestamp=_TS3, end_timestamp=_TS1)
    assert result == GovernanceQueryResult(event_count=0, events=[])


def test_query_governance_malformed_payload_values_do_not_raise():
    malformed = NormalizedEvent(
        event_id="h" * 64,
        timestamp=_TS2,
        category="governance",
        subtype="governance_blocks",
        severity="HARD",
        source="phase1_structured",
        payload={"block_logs_delta": "x", "severity_delta": ["bad"]},
    )
    result = query_governance([malformed])
    assert result.total_block_delta == 0
    assert result.hard_delta == 0
    assert result.soft_delta == 0
    assert result.info_delta == 0


def test_query_failures_extracts_retries_and_failures():
    result = query_failures(_query_events())
    assert result.event_count == 2
    assert result.total_retry_delta == 2
    assert result.total_failed_delta == 1
    assert result.total_abandoned_delta == 2
    assert result.retry_event_ids == [_query_events()[3].event_id]
    assert result.failure_event_ids == [_query_events()[3].event_id, _query_events()[6].event_id]


def test_query_failures_empty_input_returns_zero_summary():
    assert query_failures(None) == FailureQueryResult(event_count=0, events=[])


def test_query_failures_malformed_payload_values_do_not_raise():
    malformed = NormalizedEvent(
        event_id="i" * 64,
        timestamp=_TS2,
        category="health",
        subtype="retries_failures",
        severity="",
        source="phase1_structured",
        payload={"jobs_retry_sum_delta": "2", "failed_status_delta": {}, "abandoned_status_delta": None},
    )
    result = query_failures([malformed])
    assert result.total_retry_delta == 0
    assert result.total_failed_delta == 0
    assert result.total_abandoned_delta == 0


def test_query_operator_activity_extracts_totals():
    result = query_operator_activity(_query_events())
    assert result.event_count == 1
    assert result.total_pause_delta == 1
    assert result.total_lifecycle_delta == 2
    assert result.has_activity is True


def test_query_operator_activity_zero_deltas_not_flagged_as_activity():
    event = NormalizedEvent(
        event_id="e" * 64,
        timestamp=_TS2,
        category="operator",
        subtype="operator_interventions",
        severity="",
        source="phase1_structured",
        payload={"operator_pause_blocks_delta": 0, "operator_lifecycle_events_delta": 0},
    )
    result = query_operator_activity([event])
    assert result == OperatorActivitySummary(
        event_count=1,
        events=[event],
        event_ids=[event.event_id],
        total_pause_delta=0,
        total_lifecycle_delta=0,
        has_activity=False,
    )


def test_slice_timeline_supports_replay_output():
    timeline = replay_timeline(_query_events())
    view = slice_timeline(timeline, start=1, stop=6, categories=["state", "governance", "health"])
    assert [entry.event_id for entry in view.entries] == [
        timeline.entries[1].event_id,
        timeline.entries[2].event_id,
        timeline.entries[3].event_id,
        timeline.entries[5].event_id,
    ]
    assert view.start_position == 1
    assert view.end_position == 6


def test_slice_timeline_supports_raw_entries_and_timestamp_filter():
    timeline = replay_timeline(_query_events())
    view = slice_timeline(timeline.entries, start_timestamp=_TS2, end_timestamp=_TS3)
    assert [entry.event_id for entry in view.entries] == [timeline.entries[5].event_id, timeline.entries[6].event_id, timeline.entries[7].event_id]


def test_slice_timeline_invalid_indices_return_empty_view():
    timeline = replay_timeline(_query_events())
    view = slice_timeline(timeline, start=4, stop=2)
    assert view == TimelineQueryView(total_entries=0, entries=[], event_ids=[], start_position=4, end_position=2)


def test_slice_timeline_negative_indices_return_empty_view():
    timeline = replay_timeline(_query_events())
    view = slice_timeline(timeline, start=-1, stop=3)
    assert view == TimelineQueryView(total_entries=0, entries=[], event_ids=[], start_position=-1, end_position=3)


def test_slice_timeline_out_of_range_indices_are_stable():
    timeline = replay_timeline(_query_events())
    view = slice_timeline(timeline, start=999, stop=1000)
    assert view == TimelineQueryView(total_entries=0, entries=[], event_ids=[], start_position=999, end_position=1000)


def test_slice_timeline_none_boundaries_return_full_filtered_window():
    timeline = replay_timeline(_query_events())
    view = slice_timeline(timeline, start=None, stop=None, categories=["governance", "health"])
    assert [entry.event_id for entry in view.entries] == [
        timeline.entries[2].event_id,
        timeline.entries[3].event_id,
        timeline.entries[5].event_id,
        timeline.entries[6].event_id,
    ]


def test_slice_timeline_non_canonical_timestamp_range_returns_empty():
    timeline = replay_timeline(_query_events())
    view = slice_timeline(timeline, start_timestamp="2026-05-16T11:00:00+00:00", end_timestamp=_TS3)
    assert view == TimelineQueryView(total_entries=0, entries=[], event_ids=[], start_position=None, end_position=None)


def test_slice_spans_supports_replay_output():
    timeline = replay_timeline(_query_events())
    view = slice_spans(timeline, categories="governance")
    assert view.total_spans == 2
    assert view.span_ids == [timeline.spans[0].span_id, timeline.spans[1].span_id]


def test_slice_spans_supports_raw_span_list_and_index_slice():
    timeline = replay_timeline(_query_events())
    view = slice_spans(timeline.spans, start=1, stop=2)
    assert view.total_spans == 1
    assert view.span_ids == [timeline.spans[1].span_id]


def test_slice_spans_invalid_timestamp_range_returns_empty():
    timeline = replay_timeline(_query_events())
    view = slice_spans(timeline, start_timestamp=_TS3, end_timestamp=_TS1)
    assert view == SpanQueryView(total_spans=0, spans=[], span_ids=[], start_position=None, end_position=None)


def test_slice_spans_negative_indices_return_empty():
    timeline = replay_timeline(_query_events())
    view = slice_spans(timeline, start=-1, stop=1)
    assert view == SpanQueryView(total_spans=0, spans=[], span_ids=[], start_position=-1, end_position=1)


def test_slice_spans_none_boundaries_include_full_window():
    timeline = replay_timeline(_query_events())
    view = slice_spans(timeline, start=None, stop=None)
    assert view.span_ids == [timeline.spans[0].span_id, timeline.spans[1].span_id, timeline.spans[2].span_id]


def test_slice_spans_non_canonical_timestamp_range_returns_empty():
    timeline = replay_timeline(_query_events())
    view = slice_spans(timeline, start_timestamp="2026-05-16 11:00:00Z", end_timestamp=_TS3)
    assert view == SpanQueryView(total_spans=0, spans=[], span_ids=[], start_position=None, end_position=None)


def test_query_primitives_are_deterministic_across_calls():
    events = _query_events()
    assert [event.event_id for event in filter_events(events, categories="governance")] == [
        event.event_id for event in filter_events(events, categories="governance")
    ]
    assert aggregate_events(events).as_dict() == aggregate_events(events).as_dict()
    assert query_failures(events).as_dict() == query_failures(events).as_dict()


def test_query_primitives_are_byte_stable_across_calls():
    events = _query_events()
    timeline = replay_timeline(events)
    first = json.dumps(
        {
            "filtered": [event.as_dict() for event in filter_events(events, categories=["health", "governance"])],
            "grouped": {
                key: [event.as_dict() for event in value]
                for key, value in group_events(events, by="category").items()
            },
            "aggregate": aggregate_events(events).as_dict(),
            "governance": query_governance(events).as_dict(),
            "failures": query_failures(events).as_dict(),
            "operator": query_operator_activity(events).as_dict(),
            "timeline": slice_timeline(timeline, start=0, stop=6).as_dict(),
            "spans": slice_spans(timeline).as_dict(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    second = json.dumps(
        {
            "filtered": [event.as_dict() for event in filter_events(events, categories=["health", "governance"])],
            "grouped": {
                key: [event.as_dict() for event in value]
                for key, value in group_events(events, by="category").items()
            },
            "aggregate": aggregate_events(events).as_dict(),
            "governance": query_governance(events).as_dict(),
            "failures": query_failures(events).as_dict(),
            "operator": query_operator_activity(events).as_dict(),
            "timeline": slice_timeline(timeline, start=0, stop=6).as_dict(),
            "spans": slice_spans(timeline).as_dict(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    assert first == second


def test_query_results_are_json_serializable():
    events = _query_events()
    timeline = replay_timeline(events)
    payload = {
        "aggregate": aggregate_events(events).as_dict(),
        "governance": query_governance(events).as_dict(),
        "failures": query_failures(events).as_dict(),
        "operator": query_operator_activity(events).as_dict(),
        "timeline": slice_timeline(timeline, start=0, stop=3).as_dict(),
        "spans": slice_spans(timeline).as_dict(),
    }
    json.dumps(payload)


def test_mutating_query_result_does_not_affect_next_call():
    events = _query_events()
    first = filter_events(events, categories="governance")
    first.clear()
    second = filter_events(events, categories="governance")
    assert [event.event_id for event in second] == [events[2].event_id, events[5].event_id]


def test_filter_events_returns_defensive_copies():
    events = _query_events()
    result = filter_events(events, categories="governance")
    result[0].payload["block_logs_delta"] = 999
    assert events[2].payload.get("block_logs_delta") == 2


def test_group_events_returns_isolated_event_instances():
    events = _query_events()
    grouped = group_events(events, by="category")
    grouped["governance"][0].payload["block_logs_delta"] = 777
    assert events[2].payload.get("block_logs_delta") == 2
    second = group_events(events, by="category")
    assert second["governance"][0].payload.get("block_logs_delta") == 2


def test_slice_timeline_returns_isolated_entries():
    timeline = replay_timeline(_query_events())
    view = slice_timeline(timeline, start=0, stop=2)
    view.entries[0].summary = "mutated"
    assert timeline.entries[0].summary != "mutated"
    fresh = slice_timeline(timeline, start=0, stop=2)
    assert fresh.entries[0].summary == timeline.entries[0].summary


def test_slice_spans_returns_isolated_spans():
    timeline = replay_timeline(_query_events())
    view = slice_spans(timeline, start=0, stop=1)
    view.spans[0].event_ids.append("x")
    assert "x" not in timeline.spans[0].event_ids
    fresh = slice_spans(timeline, start=0, stop=1)
    assert "x" not in fresh.spans[0].event_ids


def test_normalized_event_compatibility_with_query_layer():
    normalized = normalize_phase1_telemetry(_phase1_raw())
    assert aggregate_events(normalized).total_events == 5
    assert query_governance(normalized).hard_delta == 1


def test_replay_compatibility_with_query_layer():
    timeline = replay_timeline(normalize_phase1_telemetry(_phase1_raw()))
    assert slice_timeline(timeline, categories="governance").total_entries == 1
    assert slice_spans(timeline).total_spans == 1


def test_append_only_input_semantics_preserved():
    events = _query_events()
    before_ids = [event.event_id for event in events]
    filter_events(events, categories="queue")
    group_events(events, by="category")
    query_failures(events)
    assert [event.event_id for event in events] == before_ids
