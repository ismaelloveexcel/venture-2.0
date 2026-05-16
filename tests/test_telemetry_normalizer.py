"""Tests for the deterministic telemetry normalization layer (Phase 2 foundation).

Coverage:
- deterministic output (identical input → identical output)
- ordering stability
- malformed / None / invalid telemetry handling
- backward compatibility (extra / unknown fields ignored)
- append-only normalization behavior
- event_id uniqueness and sha256 structure
- severity extraction from governance_blocks
- all Phase 1 event categories represented
- full-envelope vs bare-dict acceptance
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from run_report_schema import (
    Phase1GovernanceBlocksEventModel,
    Phase1OperatorInterventionsEventModel,
    Phase1QueueOperationsEventModel,
    Phase1RetriesFailuresEventModel,
    Phase1SeverityDeltaModel,
    Phase1StateTransitionsEventModel,
    Phase1StructuredTelemetryModel,
    Phase1WindowModel,
)
from telemetry_normalizer import (
    NormalizedEvent,
    _SOURCE,
    normalize_phase1_telemetry,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_WINDOW_DICT = {
    "pipeline_started_at_utc": "2026-05-16T10:00:00Z",
    "pipeline_finished_at_utc": "2026-05-16T10:01:00Z",
}

_FULL_EVENTS: list[dict[str, Any]] = [
    {"event": "queue_operations", "jobs_total_delta": 3},
    {"event": "state_transitions", "lifecycle_events_delta": 5},
    {
        "event": "governance_blocks",
        "block_logs_delta": 2,
        "severity_delta": {"hard": 1, "soft": 0, "info": 1},
    },
    {
        "event": "retries_failures",
        "jobs_retry_sum_delta": 1,
        "failed_status_delta": 0,
        "abandoned_status_delta": 0,
    },
    {"event": "operator_interventions", "operator_pause_blocks_delta": 0, "operator_lifecycle_events_delta": 2},
]


def _bare_phase1_dict(**kwargs: Any) -> dict[str, Any]:
    base = {"version": 1, "window": _WINDOW_DICT, "events": _FULL_EVENTS}
    base.update(kwargs)
    return base


def _full_envelope(**kwargs: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "dry_run": False,
        "run_health": {"sent": 1, "blocked": 0},
        "phase1_structured": _bare_phase1_dict(**kwargs),
    }


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_identical_raw_dict_input_produces_identical_output():
    """Identical input dicts → identical event_id list (deterministic)."""
    result_a = normalize_phase1_telemetry(_bare_phase1_dict())
    result_b = normalize_phase1_telemetry(_bare_phase1_dict())
    assert len(result_a) == len(result_b)
    ids_a = [e.event_id for e in result_a]
    ids_b = [e.event_id for e in result_b]
    assert ids_a == ids_b


def test_identical_model_input_produces_identical_output():
    """Identical Pydantic model → identical event_ids."""
    model = Phase1StructuredTelemetryModel.model_validate(_bare_phase1_dict())
    result_a = normalize_phase1_telemetry(model)
    result_b = normalize_phase1_telemetry(model)
    assert [e.event_id for e in result_a] == [e.event_id for e in result_b]


def test_different_payload_produces_different_event_id():
    """Changing a field changes the event_id (no hash collision on trivial deltas)."""
    import copy

    d1 = copy.deepcopy(_bare_phase1_dict())
    d2 = copy.deepcopy(_bare_phase1_dict())
    d2["events"][0]["jobs_total_delta"] = 99
    r1 = normalize_phase1_telemetry(d1)
    r2 = normalize_phase1_telemetry(d2)
    assert r1[0].event_id != r2[0].event_id


def test_position_index_affects_event_id():
    """Events at different positions get different IDs even with identical payloads."""
    same_event = {"event": "state_transitions", "lifecycle_events_delta": 1}
    data = {"version": 1, "events": [same_event, same_event]}
    result = normalize_phase1_telemetry(data)
    assert len(result) == 2
    assert result[0].event_id != result[1].event_id


# ---------------------------------------------------------------------------
# Ordering stability
# ---------------------------------------------------------------------------


def test_event_order_matches_source_order():
    """Normalized events appear in the same order as the source list."""
    result = normalize_phase1_telemetry(_bare_phase1_dict())
    expected_subtypes = [e["event"] for e in _FULL_EVENTS]
    actual_subtypes = [e.subtype for e in result]
    assert actual_subtypes == expected_subtypes


def test_ordering_stable_across_calls():
    """Two calls on the same data produce identically ordered event_id lists."""
    data = _bare_phase1_dict()
    assert [e.event_id for e in normalize_phase1_telemetry(data)] == [
        e.event_id for e in normalize_phase1_telemetry(data)
    ]


# ---------------------------------------------------------------------------
# Malformed / edge-case input handling
# ---------------------------------------------------------------------------


def test_none_input_returns_empty_list():
    assert normalize_phase1_telemetry(None) == []


def test_string_input_returns_empty_list():
    assert normalize_phase1_telemetry("not a dict") == []  # type: ignore[arg-type]


def test_integer_input_returns_empty_list():
    assert normalize_phase1_telemetry(42) == []  # type: ignore[arg-type]


def test_empty_dict_returns_empty_list():
    assert normalize_phase1_telemetry({}) == []


def test_malformed_event_type_returns_empty_list():
    """Unknown event discriminator makes the Pydantic model reject the list."""
    bad = {"version": 1, "events": [{"event": "totally_unknown_type", "x": 1}]}
    assert normalize_phase1_telemetry(bad) == []


def test_non_dict_phase1_structured_in_envelope_returns_empty():
    """phase1_structured value is not a dict — returns empty list, no crash."""
    envelope = {"schema_version": 1, "phase1_structured": "garbage"}
    assert normalize_phase1_telemetry(envelope) == []


def test_malformed_inner_dict_in_envelope_returns_empty():
    """phase1_structured is a dict but fails validation — returns empty list."""
    envelope = {
        "schema_version": 1,
        "phase1_structured": {"version": 1, "events": [{"event": "bad_type"}]},
    }
    assert normalize_phase1_telemetry(envelope) == []


def test_empty_events_list_returns_empty_list():
    data = {"version": 1, "events": []}
    assert normalize_phase1_telemetry(data) == []


def test_version_2_bare_dict_returns_empty_list():
    """Phase1StructuredTelemetryModel requires version==1; v2 is rejected gracefully."""
    bad = {"version": 2, "events": []}
    assert normalize_phase1_telemetry(bad) == []


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


def test_extra_unknown_keys_in_envelope_ignored():
    """Extra envelope-level keys do not cause errors."""
    envelope = _full_envelope()
    envelope["future_field"] = "some_future_value"
    result = normalize_phase1_telemetry(envelope)
    assert len(result) == len(_FULL_EVENTS)


def test_minimal_event_dict_accepted():
    """Events with only required discriminator field produce valid output."""
    data = {"version": 1, "events": [{"event": "state_transitions"}]}
    result = normalize_phase1_telemetry(data)
    assert len(result) == 1
    assert result[0].subtype == "state_transitions"


def test_window_none_gives_empty_timestamp():
    """No window → timestamp is empty string, not an error."""
    data = {"version": 1, "events": [{"event": "state_transitions", "lifecycle_events_delta": 1}]}
    result = normalize_phase1_telemetry(data)
    assert result[0].timestamp == ""


# ---------------------------------------------------------------------------
# Append-only semantics
# ---------------------------------------------------------------------------


def test_each_call_returns_new_list():
    """Two calls on same data return distinct list objects."""
    data = _bare_phase1_dict()
    r1 = normalize_phase1_telemetry(data)
    r2 = normalize_phase1_telemetry(data)
    assert r1 is not r2


def test_mutating_result_does_not_affect_next_call():
    """Mutating a returned list does not influence the next call (no shared state)."""
    data = _bare_phase1_dict()
    r1 = normalize_phase1_telemetry(data)
    r1.clear()
    r2 = normalize_phase1_telemetry(data)
    assert len(r2) == len(_FULL_EVENTS)


def test_caller_can_accumulate_across_calls():
    """Callers may extend their own accumulator list without side effects."""
    data = _bare_phase1_dict()
    accumulator: list[NormalizedEvent] = []
    accumulator.extend(normalize_phase1_telemetry(data))
    accumulator.extend(normalize_phase1_telemetry(data))
    assert len(accumulator) == len(_FULL_EVENTS) * 2
    # All event_ids in the second batch equal those in the first batch (determinism)
    first_half_ids = [e.event_id for e in accumulator[: len(_FULL_EVENTS)]]
    second_half_ids = [e.event_id for e in accumulator[len(_FULL_EVENTS) :]]
    assert first_half_ids == second_half_ids


# ---------------------------------------------------------------------------
# Canonical field checks
# ---------------------------------------------------------------------------


def test_all_required_fields_present():
    """Every NormalizedEvent has all seven required canonical fields."""
    result = normalize_phase1_telemetry(_bare_phase1_dict())
    required = {"event_id", "timestamp", "category", "subtype", "severity", "source", "payload"}
    for ev in result:
        assert set(ev.as_dict().keys()) == required


def test_source_is_always_phase1_structured():
    result = normalize_phase1_telemetry(_bare_phase1_dict())
    assert all(e.source == _SOURCE for e in result)


def test_timestamp_propagated_from_window():
    result = normalize_phase1_telemetry(_bare_phase1_dict())
    for ev in result:
        assert ev.timestamp == _WINDOW_DICT["pipeline_started_at_utc"]


def test_category_mapping():
    """Each Phase 1 event type maps to its expected category slug."""
    expected = {
        "queue_operations": "queue",
        "state_transitions": "state",
        "governance_blocks": "governance",
        "retries_failures": "health",
        "operator_interventions": "operator",
    }
    result = normalize_phase1_telemetry(_bare_phase1_dict())
    for ev in result:
        assert ev.category == expected[ev.subtype]


def test_payload_excludes_event_discriminator():
    """'event' key is stripped from normalized payload (captured in subtype)."""
    result = normalize_phase1_telemetry(_bare_phase1_dict())
    for ev in result:
        assert "event" not in ev.payload


def test_payload_excludes_none_values():
    """None-valued fields are stripped from the normalized payload."""
    data = {
        "version": 1,
        "events": [{"event": "queue_operations", "jobs_total_delta": None}],
    }
    result = normalize_phase1_telemetry(data)
    assert "jobs_total_delta" not in result[0].payload


# ---------------------------------------------------------------------------
# Severity extraction
# ---------------------------------------------------------------------------


def test_governance_blocks_hard_severity():
    data = {
        "version": 1,
        "events": [
            {
                "event": "governance_blocks",
                "severity_delta": {"hard": 2, "soft": 0, "info": 1},
            }
        ],
    }
    result = normalize_phase1_telemetry(data)
    assert result[0].severity == "HARD"


def test_governance_blocks_soft_severity():
    data = {
        "version": 1,
        "events": [
            {
                "event": "governance_blocks",
                "severity_delta": {"hard": 0, "soft": 1, "info": 0},
            }
        ],
    }
    result = normalize_phase1_telemetry(data)
    assert result[0].severity == "SOFT"


def test_governance_blocks_info_severity():
    data = {
        "version": 1,
        "events": [
            {
                "event": "governance_blocks",
                "severity_delta": {"hard": 0, "soft": 0, "info": 3},
            }
        ],
    }
    result = normalize_phase1_telemetry(data)
    assert result[0].severity == "INFO"


def test_governance_blocks_zero_deltas_empty_severity():
    data = {
        "version": 1,
        "events": [
            {
                "event": "governance_blocks",
                "severity_delta": {"hard": 0, "soft": 0, "info": 0},
            }
        ],
    }
    result = normalize_phase1_telemetry(data)
    assert result[0].severity == ""


def test_non_governance_event_has_empty_severity():
    data = {
        "version": 1,
        "events": [{"event": "state_transitions", "lifecycle_events_delta": 5}],
    }
    result = normalize_phase1_telemetry(data)
    assert result[0].severity == ""


# ---------------------------------------------------------------------------
# event_id structure
# ---------------------------------------------------------------------------


def test_event_id_is_64_char_hex():
    """sha256 hexdigest is always 64 lowercase hex characters."""
    result = normalize_phase1_telemetry(_bare_phase1_dict())
    for ev in result:
        assert len(ev.event_id) == 64
        assert ev.event_id == ev.event_id.lower()
        int(ev.event_id, 16)  # must be valid hex


def test_event_ids_unique_within_run():
    """All events in a single run have distinct event_ids."""
    result = normalize_phase1_telemetry(_bare_phase1_dict())
    ids = [e.event_id for e in result]
    assert len(ids) == len(set(ids))


def test_event_id_matches_manual_sha256():
    """Spot-check: manually compute expected event_id and compare."""
    data = {
        "version": 1,
        "events": [{"event": "state_transitions", "lifecycle_events_delta": 7}],
    }
    result = normalize_phase1_telemetry(data)
    ev = result[0]

    expected_payload = {"lifecycle_events_delta": 7}
    key_parts = {
        "category": "state",
        "position": 0,
        "source": _SOURCE,
        "subtype": "state_transitions",
        "payload": expected_payload,
    }
    canonical = json.dumps(key_parts, sort_keys=True, separators=(",", ":"), default=str)
    expected_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert ev.event_id == expected_id


# ---------------------------------------------------------------------------
# Full-envelope vs bare-dict acceptance
# ---------------------------------------------------------------------------


def test_full_envelope_produces_same_result_as_bare_dict():
    """Full pipeline telemetry envelope and bare phase1_structured dict normalize identically."""
    bare = _bare_phase1_dict()
    envelope = _full_envelope()
    result_bare = normalize_phase1_telemetry(bare)
    result_env = normalize_phase1_telemetry(envelope)
    assert [e.event_id for e in result_bare] == [e.event_id for e in result_env]


def test_accepts_pydantic_model_directly():
    """Passing a Phase1StructuredTelemetryModel directly works without re-validation."""
    model = Phase1StructuredTelemetryModel.model_validate(_bare_phase1_dict())
    result = normalize_phase1_telemetry(model)
    assert len(result) == len(_FULL_EVENTS)


def test_pydantic_model_and_dict_produce_same_ids():
    """Pydantic model input and equivalent dict input yield the same event_ids."""
    data = _bare_phase1_dict()
    model = Phase1StructuredTelemetryModel.model_validate(data)
    assert [e.event_id for e in normalize_phase1_telemetry(model)] == [
        e.event_id for e in normalize_phase1_telemetry(data)
    ]


# ---------------------------------------------------------------------------
# as_dict round-trip
# ---------------------------------------------------------------------------


def test_as_dict_is_json_serializable():
    """NormalizedEvent.as_dict() must produce a JSON-serializable structure."""
    result = normalize_phase1_telemetry(_bare_phase1_dict())
    for ev in result:
        serialized = json.dumps(ev.as_dict())
        recovered = json.loads(serialized)
        assert recovered["event_id"] == ev.event_id
        assert recovered["source"] == _SOURCE
