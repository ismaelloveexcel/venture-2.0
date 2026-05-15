"""Orchestrator telemetry merge: schema soft-reasons and provenance."""
from __future__ import annotations

from run_daily import _merge_pipeline_telemetry
from run_report_schema import MoneyPathModel, OutboundSection


def _base_outbound() -> OutboundSection:
    return OutboundSection(
        status="SUCCESS",
        money_path_source="orchestrator",
        money_path=MoneyPathModel(
            attempted=1,
            sent=0,
            blocked=0,
            reasons=["venture_pipeline_exit_0", "dry_run"],
        ),
        dry_run=True,
    )


def test_merge_unknown_schema_version_appends_soft_reason_with_run_health():
    o = _base_outbound()
    merged = _merge_pipeline_telemetry(
        o,
        {"schema_version": 2, "run_health": {"sent": 0, "blocked": 0}},
        dry_run=True,
    )
    assert merged.money_path_source == "pipeline_telemetry"
    assert "unknown_telemetry_schema_version" in merged.money_path.reasons


def test_merge_unknown_schema_without_run_health_keeps_orchestrator_source():
    o = _base_outbound()
    merged = _merge_pipeline_telemetry(
        o,
        {"schema_version": 2, "job_queue_summary": {"pending": 0}},
        dry_run=True,
    )
    assert merged.money_path_source == "orchestrator"
    assert "unknown_telemetry_schema_version" in merged.money_path.reasons


def test_merge_invalid_phase1_structured_dropped_without_crash():
    o = _base_outbound()
    merged = _merge_pipeline_telemetry(
        o,
        {
            "schema_version": 1,
            "run_health": {"sent": 1, "blocked": 0},
            "phase1_structured": {"version": 1, "events": [{"event": "bad_type", "x": 1}]},
        },
        dry_run=True,
    )
    assert merged.pipeline_telemetry.phase1_structured is None
    assert "phase1_structured_dropped_invalid" in merged.money_path.reasons
    assert merged.money_path.sent == 1
    assert merged.money_path.blocked == 0


def test_merge_non_phase1_invalid_preserves_valid_phase1():
    o = _base_outbound()
    merged = _merge_pipeline_telemetry(
        o,
        {
            "schema_version": 1,
            "run_health": ["invalid-shape"],
            "phase1_structured": {
                "version": 1,
                "events": [{"event": "queue_operations", "jobs_total_delta": 2}],
            },
        },
        dry_run=True,
    )
    assert merged.pipeline_telemetry.phase1_structured is not None
    assert merged.pipeline_telemetry.phase1_structured.events[0].event == "queue_operations"
    assert "pipeline_telemetry_invalid" in merged.money_path.reasons
    assert "phase1_structured_dropped_invalid" not in merged.money_path.reasons
