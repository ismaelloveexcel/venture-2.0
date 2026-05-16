"""Tests for the deterministic telemetry replay/timeline reconstruction layer.

Coverage:
- deterministic replay (identical input → identical output)
- ordering stability
- span reconstruction (single and multi-timestamp)
- governance escalation reconstruction
- retry/failure sequencing
- execution summary correctness
- group_by_category / group_by_subtype utilities
- append-only replay behavior
- backward compatibility (empty events, unknown subtypes in normalized form)
- timeline entry summary text
- all output structures JSON-serializable
- span_id structure (sha256 hex)
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from telemetry_normalizer import NormalizedEvent, normalize_phase1_telemetry
from telemetry_replay import (
    ExecutionTimeline,
    GovernanceEscalationSummary,
    ReconstructedSpan,
    RetryFailureSummary,
    ExecutionSummary,
    TimelineEntry,
    group_by_category,
    group_by_subtype,
    replay_timeline,
)

# ---------------------------------------------------------------------------
# Shared fixtures / builders
# ---------------------------------------------------------------------------

_TS = "2026-05-16T10:00:00Z"
_TS2 = "2026-05-16T11:00:00Z"


def _make_event(
    subtype: str,
    *,
    position: int = 0,
    timestamp: str = _TS,
    severity: str = "",
    payload: dict[str, Any] | None = None,
) -> NormalizedEvent:
    cat_map = {
        "queue_operations": "queue",
        "state_transitions": "state",
        "governance_blocks": "governance",
        "retries_failures": "health",
        "operator_interventions": "operator",
    }
    cat = cat_map.get(subtype, "unknown")
    p = payload or {}
    key_parts = {
        "category": cat,
        "payload": p,
        "position": position,
        "source": "phase1_structured",
        "subtype": subtype,
        "timestamp": timestamp,
    }
    canonical = json.dumps(key_parts, sort_keys=True, separators=(",", ":"), default=str)
    eid = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return NormalizedEvent(
        event_id=eid,
        timestamp=timestamp,
        category=cat,
        subtype=subtype,
        severity=severity,
        source="phase1_structured",
        payload=p,
    )


def _full_events() -> list[NormalizedEvent]:
    """A standard 5-event set covering all Phase 1 subtypes."""
    return [
        _make_event("queue_operations", position=0, payload={"jobs_total_delta": 3}),
        _make_event("state_transitions", position=1, payload={"lifecycle_events_delta": 5}),
        _make_event(
            "governance_blocks",
            position=2,
            severity="HARD",
            payload={"block_logs_delta": 2, "severity_delta": {"hard": 1, "soft": 0, "info": 1}},
        ),
        _make_event(
            "retries_failures",
            position=3,
            payload={"jobs_retry_sum_delta": 1, "failed_status_delta": 0, "abandoned_status_delta": 0},
        ),
        _make_event(
            "operator_interventions",
            position=4,
            payload={"operator_pause_blocks_delta": 0, "operator_lifecycle_events_delta": 2},
        ),
    ]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_replay_deterministic_identical_input():
    events = _full_events()
    t1 = replay_timeline(events)
    t2 = replay_timeline(events)
    assert [e.event_id for e in t1.entries] == [e.event_id for e in t2.entries]
    assert [s.span_id for s in t1.spans] == [s.span_id for s in t2.spans]
    assert t1.summary.event_count == t2.summary.event_count


def test_replay_deterministic_across_independent_event_lists():
    """Two independently constructed identical event lists produce the same timeline."""
    t1 = replay_timeline(_full_events())
    t2 = replay_timeline(_full_events())
    assert [e.event_id for e in t1.entries] == [e.event_id for e in t2.entries]
    assert t1.summary.as_dict() == t2.summary.as_dict()


def test_replay_different_events_produce_different_span_ids():
    events_a = [_make_event("state_transitions", payload={"lifecycle_events_delta": 1})]
    events_b = [_make_event("state_transitions", payload={"lifecycle_events_delta": 9})]
    t_a = replay_timeline(events_a)
    t_b = replay_timeline(events_b)
    assert t_a.spans[0].span_id != t_b.spans[0].span_id


# ---------------------------------------------------------------------------
# Empty / edge inputs
# ---------------------------------------------------------------------------


def test_replay_empty_list_returns_empty_timeline():
    t = replay_timeline([])
    assert t.entries == []
    assert t.spans == []
    assert t.groups_by_category == {}
    assert t.groups_by_subtype == {}
    assert t.summary.event_count == 0


def test_replay_single_event():
    ev = _make_event("queue_operations", payload={"jobs_total_delta": 1})
    t = replay_timeline([ev])
    assert len(t.entries) == 1
    assert len(t.spans) == 1
    assert t.summary.event_count == 1


# ---------------------------------------------------------------------------
# Ordering stability
# ---------------------------------------------------------------------------


def test_timeline_entry_positions_match_source_order():
    events = _full_events()
    t = replay_timeline(events)
    for i, entry in enumerate(t.entries):
        assert entry.position == i
        assert entry.event_id == events[i].event_id


def test_ordering_stable_across_calls():
    events = _full_events()
    ids_a = [e.event_id for e in replay_timeline(events).entries]
    ids_b = [e.event_id for e in replay_timeline(events).entries]
    assert ids_a == ids_b


def test_subtype_order_preserved_in_entries():
    events = _full_events()
    t = replay_timeline(events)
    expected = [ev.subtype for ev in events]
    actual = [entry.subtype for entry in t.entries]
    assert actual == expected


# ---------------------------------------------------------------------------
# Span reconstruction
# ---------------------------------------------------------------------------


def test_single_timestamp_produces_one_span():
    t = replay_timeline(_full_events())
    assert len(t.spans) == 1


def test_span_contains_all_event_ids():
    events = _full_events()
    t = replay_timeline(events)
    assert set(t.spans[0].event_ids) == {ev.event_id for ev in events}


def test_span_event_ids_in_source_order():
    events = _full_events()
    t = replay_timeline(events)
    assert t.spans[0].event_ids == [ev.event_id for ev in events]


def test_span_start_timestamp_equals_event_timestamp():
    events = _full_events()
    t = replay_timeline(events)
    assert t.spans[0].start_timestamp == _TS


def test_span_end_timestamp_equals_start_for_single_ts():
    """Without distinct end-event timestamps, end_timestamp == start_timestamp."""
    t = replay_timeline(_full_events())
    assert t.spans[0].end_timestamp == t.spans[0].start_timestamp


def test_multiple_timestamps_produce_multiple_spans():
    events = [
        _make_event("queue_operations", timestamp=_TS, payload={"jobs_total_delta": 1}),
        _make_event("state_transitions", timestamp=_TS2, payload={"lifecycle_events_delta": 2}),
    ]
    t = replay_timeline(events)
    assert len(t.spans) == 2
    assert t.spans[0].start_timestamp == _TS
    assert t.spans[1].start_timestamp == _TS2


def test_multi_span_each_has_correct_events():
    ev1 = _make_event("queue_operations", timestamp=_TS, payload={"jobs_total_delta": 1})
    ev2 = _make_event("state_transitions", timestamp=_TS2, payload={"lifecycle_events_delta": 2})
    t = replay_timeline([ev1, ev2])
    assert t.spans[0].event_ids == [ev1.event_id]
    assert t.spans[1].event_ids == [ev2.event_id]
    # Span ordering must follow first-seen timestamp order
    assert t.spans[0].start_timestamp == _TS
    assert t.spans[1].start_timestamp == _TS2


def test_span_category_set_sorted():
    events = _full_events()
    t = replay_timeline(events)
    cats = t.spans[0].category_set
    assert cats == sorted(cats)


def test_span_id_is_64_char_hex():
    t = replay_timeline(_full_events())
    for span in t.spans:
        assert len(span.span_id) == 64
        int(span.span_id, 16)  # valid hex


def test_span_id_deterministic_from_sorted_event_ids():
    """Manually compute span_id and compare."""
    events = _full_events()
    ids = [ev.event_id for ev in events]
    expected = hashlib.sha256(
        json.dumps(sorted(ids), separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    t = replay_timeline(events)
    assert t.spans[0].span_id == expected


def test_empty_timestamp_events_grouped_into_one_span():
    """Events with empty timestamps are grouped together into a single span."""
    events = [
        _make_event("queue_operations", timestamp="", payload={"jobs_total_delta": 1}),
        _make_event("state_transitions", timestamp="", payload={"lifecycle_events_delta": 1}),
    ]
    t = replay_timeline(events)
    assert len(t.spans) == 1


# ---------------------------------------------------------------------------
# Governance escalation
# ---------------------------------------------------------------------------


def test_governance_hard_delta_captured():
    ev = _make_event(
        "governance_blocks",
        severity="HARD",
        payload={"block_logs_delta": 3, "severity_delta": {"hard": 2, "soft": 1, "info": 0}},
    )
    t = replay_timeline([ev])
    gov = t.summary.governance
    assert gov.hard_delta == 2
    assert gov.soft_delta == 1
    assert gov.info_delta == 0
    assert gov.total_block_delta == 3
    assert ev.event_id in gov.hard_event_ids


def test_governance_soft_only_not_in_hard_event_ids():
    ev = _make_event(
        "governance_blocks",
        severity="SOFT",
        payload={"block_logs_delta": 1, "severity_delta": {"hard": 0, "soft": 1, "info": 0}},
    )
    t = replay_timeline([ev])
    gov = t.summary.governance
    assert gov.soft_delta == 1
    assert gov.hard_delta == 0
    assert gov.hard_event_ids == []


def test_governance_zero_blocks_no_hard_ids():
    ev = _make_event(
        "governance_blocks",
        payload={"block_logs_delta": 0, "severity_delta": {"hard": 0, "soft": 0, "info": 0}},
    )
    t = replay_timeline([ev])
    gov = t.summary.governance
    assert gov.total_block_delta == 0
    assert gov.hard_event_ids == []


def test_governance_multiple_events_accumulate():
    ev1 = _make_event(
        "governance_blocks",
        position=0,
        severity="HARD",
        payload={"block_logs_delta": 2, "severity_delta": {"hard": 1, "soft": 0, "info": 0}},
    )
    ev2 = _make_event(
        "governance_blocks",
        position=1,
        severity="SOFT",
        payload={"block_logs_delta": 1, "severity_delta": {"hard": 0, "soft": 1, "info": 0}},
    )
    t = replay_timeline([ev1, ev2])
    gov = t.summary.governance
    assert gov.total_block_delta == 3
    assert gov.hard_delta == 1
    assert gov.soft_delta == 1
    assert len(gov.hard_event_ids) == 1
    assert ev1.event_id in gov.hard_event_ids


def test_no_governance_events_gives_zero_summary():
    ev = _make_event("queue_operations", payload={"jobs_total_delta": 1})
    t = replay_timeline([ev])
    gov = t.summary.governance
    assert gov.total_block_delta == 0
    assert gov.hard_delta == 0
    assert gov.hard_event_ids == []


# ---------------------------------------------------------------------------
# Retry / failure sequencing
# ---------------------------------------------------------------------------


def test_retry_delta_captured():
    ev = _make_event(
        "retries_failures",
        payload={"jobs_retry_sum_delta": 3, "failed_status_delta": 1, "abandoned_status_delta": 0},
    )
    t = replay_timeline([ev])
    ret = t.summary.retries
    assert ret.total_retry_delta == 3
    assert ret.total_failed_delta == 1
    assert ret.total_abandoned_delta == 0
    assert ev.event_id in ret.retry_event_ids
    assert ev.event_id in ret.failure_event_ids


def test_retry_zero_values_empty_id_lists():
    ev = _make_event(
        "retries_failures",
        payload={"jobs_retry_sum_delta": 0, "failed_status_delta": 0, "abandoned_status_delta": 0},
    )
    t = replay_timeline([ev])
    ret = t.summary.retries
    assert ret.total_retry_delta == 0
    assert ret.retry_event_ids == []
    assert ret.failure_event_ids == []


def test_retry_abandoned_in_failure_ids():
    ev = _make_event(
        "retries_failures",
        payload={"jobs_retry_sum_delta": 0, "failed_status_delta": 0, "abandoned_status_delta": 2},
    )
    t = replay_timeline([ev])
    ret = t.summary.retries
    assert ret.total_abandoned_delta == 2
    assert ev.event_id in ret.failure_event_ids
    assert ret.retry_event_ids == []


def test_retry_multiple_events_accumulate():
    ev1 = _make_event(
        "retries_failures",
        position=0,
        payload={"jobs_retry_sum_delta": 1, "failed_status_delta": 0, "abandoned_status_delta": 0},
    )
    ev2 = _make_event(
        "retries_failures",
        position=1,
        payload={"jobs_retry_sum_delta": 2, "failed_status_delta": 1, "abandoned_status_delta": 0},
    )
    t = replay_timeline([ev1, ev2])
    ret = t.summary.retries
    assert ret.total_retry_delta == 3
    assert ret.total_failed_delta == 1


def test_no_retry_events_gives_zero_summary():
    t = replay_timeline([_make_event("queue_operations", payload={"jobs_total_delta": 1})])
    ret = t.summary.retries
    assert ret.total_retry_delta == 0
    assert ret.retry_event_ids == []


# ---------------------------------------------------------------------------
# Execution summary
# ---------------------------------------------------------------------------


def test_summary_event_count():
    events = _full_events()
    t = replay_timeline(events)
    assert t.summary.event_count == 5


def test_summary_categories_sorted():
    t = replay_timeline(_full_events())
    cats = t.summary.categories_observed
    assert cats == sorted(cats)


def test_summary_queue_delta():
    ev = _make_event("queue_operations", payload={"jobs_total_delta": 7})
    t = replay_timeline([ev])
    assert t.summary.queue_delta == 7


def test_summary_queue_delta_accumulated():
    ev1 = _make_event("queue_operations", position=0, payload={"jobs_total_delta": 3})
    ev2 = _make_event("queue_operations", position=1, payload={"jobs_total_delta": 2})
    t = replay_timeline([ev1, ev2])
    assert t.summary.queue_delta == 5


def test_summary_state_transitions_delta():
    ev = _make_event("state_transitions", payload={"lifecycle_events_delta": 9})
    t = replay_timeline([ev])
    assert t.summary.state_transitions_delta == 9


def test_summary_has_operator_interventions_true():
    ev = _make_event(
        "operator_interventions",
        payload={"operator_pause_blocks_delta": 1, "operator_lifecycle_events_delta": 0},
    )
    t = replay_timeline([ev])
    assert t.summary.has_operator_interventions is True


def test_summary_has_operator_interventions_true_via_lifecycle_delta():
    ev = _make_event(
        "operator_interventions",
        payload={"operator_pause_blocks_delta": 0, "operator_lifecycle_events_delta": 3},
    )
    t = replay_timeline([ev])
    assert t.summary.has_operator_interventions is True


def test_summary_has_operator_interventions_false_when_all_zero_deltas():
    """operator_interventions event with all-zero deltas must NOT set the flag.

    venture_pipeline always emits an operator_interventions event even when no
    actual operator action occurred; the flag should only be True for non-zero
    deltas to avoid false-positive summaries on normal runs.
    """
    ev = _make_event(
        "operator_interventions",
        payload={"operator_pause_blocks_delta": 0, "operator_lifecycle_events_delta": 0},
    )
    t = replay_timeline([ev])
    assert t.summary.has_operator_interventions is False


def test_summary_has_operator_interventions_false_when_absent():
    t = replay_timeline([_make_event("queue_operations", payload={"jobs_total_delta": 1})])
    assert t.summary.has_operator_interventions is False


def test_summary_categories_all_phase1_types():
    t = replay_timeline(_full_events())
    expected = sorted({"queue", "state", "governance", "health", "operator"})
    assert t.summary.categories_observed == expected


# ---------------------------------------------------------------------------
# Grouping utilities
# ---------------------------------------------------------------------------


def test_group_by_category_correct_keys():
    events = _full_events()
    groups = group_by_category(events)
    assert set(groups.keys()) == {"queue", "state", "governance", "health", "operator"}


def test_group_by_category_each_event_in_correct_group():
    events = _full_events()
    groups = group_by_category(events)
    for ev in events:
        assert ev in groups[ev.category]


def test_group_by_category_preserves_source_order():
    events = _full_events()
    groups = group_by_category(events)
    for cat, cat_events in groups.items():
        source_ids = [ev.event_id for ev in events if ev.category == cat]
        assert [ev.event_id for ev in cat_events] == source_ids


def test_group_by_subtype_correct_keys():
    events = _full_events()
    groups = group_by_subtype(events)
    expected_subtypes = {
        "queue_operations", "state_transitions", "governance_blocks",
        "retries_failures", "operator_interventions",
    }
    assert set(groups.keys()) == expected_subtypes


def test_group_by_subtype_each_event_in_correct_group():
    events = _full_events()
    groups = group_by_subtype(events)
    for ev in events:
        assert ev in groups[ev.subtype]


def test_group_by_category_returns_new_dict_each_call():
    events = _full_events()
    g1 = group_by_category(events)
    g2 = group_by_category(events)
    assert g1 is not g2


def test_group_by_subtype_returns_new_dict_each_call():
    events = _full_events()
    g1 = group_by_subtype(events)
    g2 = group_by_subtype(events)
    assert g1 is not g2


def test_groups_in_timeline_match_standalone_group_functions():
    """ExecutionTimeline groups_by_category event_id lists match group_by_category output."""
    events = _full_events()
    t = replay_timeline(events)
    standalone = group_by_category(events)
    for cat, ev_list in standalone.items():
        assert t.groups_by_category[cat] == [ev.event_id for ev in ev_list]


# ---------------------------------------------------------------------------
# Append-only / no shared state
# ---------------------------------------------------------------------------


def test_replay_returns_new_timeline_each_call():
    events = _full_events()
    t1 = replay_timeline(events)
    t2 = replay_timeline(events)
    assert t1 is not t2


def test_mutating_returned_entries_does_not_affect_next_call():
    events = _full_events()
    t1 = replay_timeline(events)
    t1.entries.clear()
    t2 = replay_timeline(events)
    assert len(t2.entries) == 5


def test_mutating_returned_spans_does_not_affect_next_call():
    events = _full_events()
    t1 = replay_timeline(events)
    t1.spans.clear()
    t2 = replay_timeline(events)
    assert len(t2.spans) == 1


def test_accumulate_across_calls_append_only():
    """Callers may accumulate timelines across multiple calls safely."""
    events = _full_events()
    entries: list[TimelineEntry] = []
    entries.extend(replay_timeline(events).entries)
    entries.extend(replay_timeline(events).entries)
    assert len(entries) == 10
    # Each batch is deterministic
    first = [e.event_id for e in entries[:5]]
    second = [e.event_id for e in entries[5:]]
    assert first == second


# ---------------------------------------------------------------------------
# Timeline entry summary text
# ---------------------------------------------------------------------------


def test_summary_text_queue_operations_positive_delta():
    ev = _make_event("queue_operations", payload={"jobs_total_delta": 3})
    t = replay_timeline([ev])
    assert t.entries[0].summary == "Queue delta: +3 job(s)"


def test_summary_text_queue_operations_negative_delta():
    ev = _make_event("queue_operations", payload={"jobs_total_delta": -2})
    t = replay_timeline([ev])
    assert t.entries[0].summary == "Queue delta: -2 job(s)"


def test_summary_text_queue_operations_no_delta():
    ev = _make_event("queue_operations", payload={})
    t = replay_timeline([ev])
    assert "no delta" in t.entries[0].summary


def test_summary_text_state_transitions():
    ev = _make_event("state_transitions", payload={"lifecycle_events_delta": 7})
    t = replay_timeline([ev])
    assert t.entries[0].summary == "State transitions: 7 lifecycle event(s)"


def test_summary_text_governance_blocks_with_hard_severity():
    ev = _make_event(
        "governance_blocks",
        severity="HARD",
        payload={"block_logs_delta": 2},
    )
    t = replay_timeline([ev])
    assert "(HARD)" in t.entries[0].summary
    assert "+2" in t.entries[0].summary


def test_summary_text_governance_blocks_no_severity():
    ev = _make_event("governance_blocks", payload={"block_logs_delta": 1})
    t = replay_timeline([ev])
    assert "HARD" not in t.entries[0].summary
    assert "+1" in t.entries[0].summary


def test_summary_text_retries_failures():
    ev = _make_event(
        "retries_failures",
        payload={"jobs_retry_sum_delta": 2, "failed_status_delta": 1, "abandoned_status_delta": 0},
    )
    t = replay_timeline([ev])
    assert "2 retry(ies)" in t.entries[0].summary
    assert "1 failure(s)" in t.entries[0].summary


def test_summary_text_operator_interventions():
    ev = _make_event(
        "operator_interventions",
        payload={"operator_pause_blocks_delta": 1, "operator_lifecycle_events_delta": 3},
    )
    t = replay_timeline([ev])
    assert "1 pause(s)" in t.entries[0].summary
    assert "3 lifecycle event(s)" in t.entries[0].summary


def test_summary_text_unknown_subtype_fallback():
    """Events with an unknown subtype get a generic summary (backward compat)."""
    ev = NormalizedEvent(
        event_id="a" * 64,
        timestamp=_TS,
        category="unknown",
        subtype="future_event_type",
        severity="",
        source="phase1_structured",
        payload={},
    )
    t = replay_timeline([ev])
    assert "future_event_type" in t.entries[0].summary


# ---------------------------------------------------------------------------
# JSON serialization (all as_dict must be serializable)
# ---------------------------------------------------------------------------


def test_execution_timeline_as_dict_json_serializable():
    t = replay_timeline(_full_events())
    serialized = json.dumps(t.as_dict())
    recovered = json.loads(serialized)
    assert recovered["summary"]["event_count"] == 5


def test_reconstructed_span_as_dict_json_serializable():
    t = replay_timeline(_full_events())
    for span in t.spans:
        json.dumps(span.as_dict())


def test_governance_summary_as_dict_json_serializable():
    t = replay_timeline(_full_events())
    json.dumps(t.summary.governance.as_dict())


def test_retry_summary_as_dict_json_serializable():
    t = replay_timeline(_full_events())
    json.dumps(t.summary.retries.as_dict())


def test_timeline_entries_as_dict_json_serializable():
    t = replay_timeline(_full_events())
    for entry in t.entries:
        json.dumps(entry.as_dict())


# ---------------------------------------------------------------------------
# Backward compatibility (normalizer → replay round-trip)
# ---------------------------------------------------------------------------


def test_normalizer_to_replay_full_round_trip():
    """normalize_phase1_telemetry output is directly usable by replay_timeline."""
    raw = {
        "version": 1,
        "window": {
            "pipeline_started_at_utc": _TS,
            "pipeline_finished_at_utc": "2026-05-16T10:01:00Z",
        },
        "events": [
            {"event": "queue_operations", "jobs_total_delta": 5},
            {"event": "governance_blocks", "block_logs_delta": 1,
             "severity_delta": {"hard": 1, "soft": 0, "info": 0}},
        ],
    }
    normalized = normalize_phase1_telemetry(raw)
    t = replay_timeline(normalized)
    assert t.summary.event_count == 2
    assert t.summary.governance.hard_delta == 1
    assert t.summary.queue_delta == 5


def test_empty_normalized_events_produces_empty_timeline():
    normalized = normalize_phase1_telemetry(None)
    t = replay_timeline(normalized)
    assert t.entries == []
    assert t.spans == []


def test_replay_idempotent_with_normalizer_output():
    """Two replay calls on the same normalizer output are identical."""
    raw = {
        "version": 1,
        "events": [{"event": "state_transitions", "lifecycle_events_delta": 4}],
    }
    evs = normalize_phase1_telemetry(raw)
    t1 = replay_timeline(evs)
    t2 = replay_timeline(evs)
    assert t1.summary.as_dict() == t2.summary.as_dict()


def test_non_integer_payload_values_do_not_raise():
    """NormalizedEvent constructed with non-integer delta values must not raise.

    Phase 1 Pydantic-validated payloads always carry int|None deltas.  This
    test covers the defensive _as_int path for manually-constructed events.
    """
    ev = NormalizedEvent(
        event_id="a" * 64,
        timestamp=_TS,
        category="queue",
        subtype="queue_operations",
        severity="",
        source="phase1_structured",
        payload={"jobs_total_delta": "not-an-int"},  # unexpected string value
    )
    t = replay_timeline([ev])
    # _as_int should return 0 for the string value; no ValueError raised
    assert t.summary.queue_delta == 0


def test_none_payload_values_do_not_raise():
    """None delta values in payload are handled as zero by _as_int."""
    ev = NormalizedEvent(
        event_id="b" * 64,
        timestamp=_TS,
        category="health",
        subtype="retries_failures",
        severity="",
        source="phase1_structured",
        payload={"jobs_retry_sum_delta": None, "failed_status_delta": None},
    )
    t = replay_timeline([ev])
    assert t.summary.retries.total_retry_delta == 0
    assert t.summary.retries.total_failed_delta == 0
