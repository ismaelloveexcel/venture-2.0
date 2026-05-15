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
