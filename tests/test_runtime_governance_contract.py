from __future__ import annotations

from pathlib import Path

from run_report_schema import OutboundSection, RunReport
from runtime_governance import MODULE_GRAPH, build_runtime_governance


def test_runtime_governance_contract_has_required_sections(tmp_path: Path) -> None:
    report = RunReport(
        run_id="gov-contract-1",
        timestamp_utc="2026-05-15T00:00:00Z",
        outbound=OutboundSection(status="SUCCESS"),
    )

    payload = build_runtime_governance(report, repo_root=tmp_path, client_id=None)

    assert "system_trust_center" in payload
    assert "causal_impact_map" in payload
    assert "regression_timeline" in payload
    assert "decision_safety" in payload
    assert "root_cause_intelligence" in payload
    assert "module_governance_grid" in payload


def test_module_grid_contains_required_runtime_fields(tmp_path: Path) -> None:
    report = RunReport(
        run_id="gov-contract-2",
        timestamp_utc="2026-05-15T00:00:00Z",
        outbound=OutboundSection(status="SUCCESS"),
    )

    payload = build_runtime_governance(report, repo_root=tmp_path, client_id=None)
    modules = payload["module_governance_grid"]

    assert len(modules) == len(MODULE_GRAPH)

    required = {
        "runtime_state",
        "execution_state",
        "usefulness_score",
        "confidence_score",
        "stability_score",
        "downstream_impact_score",
        "trust_score",
        "evidence_quality",
        "regression_detected",
        "degraded_by",
        "affects",
        "root_cause",
        "operator_action_required",
        "last_known_good_run",
        "historical_baseline_delta",
        "depends_on",
        "soft_dependencies",
        "causal_chain_depth",
        "upstream_degradation_sources",
        "downstream_modules_affected",
    }

    for module in modules:
        assert required.issubset(module.keys())


def test_decision_safety_contract_shape(tmp_path: Path) -> None:
    report = RunReport(
        run_id="gov-contract-3",
        timestamp_utc="2026-05-15T00:00:00Z",
        outbound=OutboundSection(status="SUCCESS"),
    )

    payload = build_runtime_governance(report, repo_root=tmp_path, client_id=None)
    safety = payload["decision_safety"]

    assert set(
        [
            "safe_to_scale",
            "safe_to_change_messaging",
            "safe_to_change_audience",
            "safe_to_run_ab_test",
            "confidence_in_recommendation",
            "recommended_next_move",
        ]
    ).issubset(safety.keys())
