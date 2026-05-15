from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "04-coding" / "scripts" / "shadow_drift_tracker.py"
V8_1_PROMPT_PATH = REPO_ROOT / "08-prompts" / "CIS_PAIRED_EVAL_AGENT_PROMPT_V8_1.md"
RUN_PIPELINE_PATH = REPO_ROOT / "04-coding" / "scripts" / "run_pipeline.py"
RUN_DAILY_PATH = REPO_ROOT / "04-coding" / "scripts" / "run_daily.py"


REQUIRED_INPUT_FIELDS = {
    "company",
    "v2_motion_score",
    "v3_cis",
    "motion_class",
    "v3_routing_band",
}


def _load_shadow_module():
    spec = importlib.util.spec_from_file_location("shadow_drift_tracker", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot import shadow_drift_tracker")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _make_records(n: int) -> list[dict]:
    rows: list[dict] = []
    for i in range(n):
        v2 = float(i % 11)
        v3 = float((i * 7) % 101)
        v2_decision = "HOT" if v2 >= 7 else "POSSIBLE" if v2 >= 5 else "NO"
        v3_decision = "HOT" if v3 >= 80 else "POSSIBLE" if v3 >= 50 else "DISCARD"
        rows.append(
            {
                "company": f"Company {i:03d}",
                "v2_motion_score": v2,
                "v3_cis": v3,
                "motion_class": v2_decision,
                "v3_routing_band": v3_decision,
                "v2_percentile": float(i * 100 / max(1, n - 1)),
                "v3_percentile": float(((i * 9) % n) * 100 / max(1, n - 1)),
                "variant_dimension": "spend_1_motion_0_urgency_0",
            }
        )
    return rows


def _make_baseline(path: Path, n: int = 200) -> None:
    baseline = {
        "frozen_at": "2026-05-10T00:00:00+00:00",
        "v2": {"scores": list(range(0, n))},
        "v3": {"scores": list(range(0, n))},
    }
    path.write_text(json.dumps(baseline, indent=2), encoding="utf-8")


def _normalize_dashboard(dashboard: dict) -> dict:
    normalized = json.loads(json.dumps(dashboard, sort_keys=True))
    normalized.pop("timestamp", None)
    return normalized


@pytest.fixture()
def contract_case(tmp_path: Path):
    mod = _load_shadow_module()
    shadow = tmp_path / "shadow_decisions.jsonl"
    baseline = tmp_path / "baseline_distributions.json"
    output = tmp_path / "experiment_dashboard.json"
    return mod, shadow, baseline, output


def test_prompt_file_exists_and_is_locked():
    assert V8_1_PROMPT_PATH.exists(), "v8.1 prompt artifact missing"
    text = V8_1_PROMPT_PATH.read_text(encoding="utf-8")
    assert "ACCEPTANCE" in text.upper(), "prompt must contain acceptance criteria"
    assert "RANDOM_SEED = 42" in text


def test_acceptance_rule_sample_gate_enforced(contract_case):
    mod, shadow, baseline, output = contract_case
    _make_baseline(baseline)
    _write_jsonl(shadow, _make_records(40))

    dashboard = mod.generate_experiment_dashboard(shadow, baseline, output)

    # v8.1 requires hard stop for n < 50 with explicit status payload.
    assert dashboard.get("decision_status") == "INSUFFICIENT_SAMPLE_SIZE"


def test_acceptance_rule_dashboard_contract_sections_present(contract_case):
    mod, shadow, baseline, output = contract_case
    _make_baseline(baseline)
    _write_jsonl(shadow, _make_records(60))

    mod.generate_experiment_dashboard(shadow, baseline, output)
    data = json.loads(output.read_text(encoding="utf-8"))

    required_sections = {
        "metadata",
        "invariance_checks",
        "sample_gate",
        "metrics_point_estimates",
        "metrics_bootstrap",
        "risk_components",
        "final_decision",
        "stress_test_summary",
        "semantic_labels",
    }
    missing = sorted(required_sections - set(data.keys()))
    assert not missing, f"Missing dashboard sections: {missing}"


def test_acceptance_rule_deterministic_output(contract_case):
    mod, shadow, baseline, output = contract_case
    _make_baseline(baseline)
    _write_jsonl(shadow, _make_records(60))

    d1 = mod.generate_experiment_dashboard(shadow, baseline, output)
    d2 = mod.generate_experiment_dashboard(shadow, baseline, output)

    assert _normalize_dashboard(d1) == _normalize_dashboard(d2)


def test_acceptance_rule_no_forbidden_causal_or_outcome_logic():
    source = SCRIPT_PATH.read_text(encoding="utf-8").lower()

    forbidden_fragments = [
        "expected conversion",
        "outcome proxy",
        "uplift",
        "causal",
    ]
    present = [frag for frag in forbidden_fragments if frag in source]
    assert not present, f"Forbidden logic found: {present}"


def test_acceptance_rule_percentile_spearman_only():
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    # v8.1 requires spearman on percentile vectors, not baseline raw score arrays.
    assert "compute_rank_correlation(v2_baseline, v3_baseline)" not in source


def test_acceptance_rule_bootstrap_required():
    source = SCRIPT_PATH.read_text(encoding="utf-8").lower()

    markers = ["bootstrap", "ci95_low", "ci95_high", "p2.5", "p97.5"]
    present = [m for m in markers if m in source]
    assert len(present) >= 3, "Bootstrap CI implementation markers missing"


def test_acceptance_rule_no_raw_score_cross_metric_leakage():
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    # raw scale allowed for collapse only; this check catches common leakage signals.
    disallowed = [
        "v3_score - v2_score",
        "v3_cis - v2_motion_score",
    ]
    present = [x for x in disallowed if x in source]
    assert not present, f"Found disallowed raw-score delta expressions: {present}"


def test_acceptance_rule_cli_exists_and_supports_contract():
    assert RUN_PIPELINE_PATH.exists(), "legacy CIS runner run_pipeline.py missing"
    assert RUN_DAILY_PATH.exists(), "canonical orchestrator run_daily.py missing"

    result = subprocess.run(
        [sys.executable, str(RUN_DAILY_PATH), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = f"{result.stdout}\n{result.stderr}".lower()

    assert "--cis" in combined
    assert "--shadow-input" in combined
    assert "--report-path" in combined
    assert "--generate-prospects" in combined
    assert "--execute-outbound" in combined


def test_acceptance_rule_numeric_hygiene_finite_only(contract_case):
    mod, shadow, baseline, output = contract_case
    _make_baseline(baseline)

    rows = _make_records(60)
    rows[0]["v2_motion_score"] = float("nan")
    _write_jsonl(shadow, rows)

    with pytest.raises(Exception):
        mod.generate_experiment_dashboard(shadow, baseline, output)


def test_acceptance_rule_risk_engine_outputs_continuous_score(contract_case):
    mod, shadow, baseline, output = contract_case
    _make_baseline(baseline)
    _write_jsonl(shadow, _make_records(60))

    mod.generate_experiment_dashboard(shadow, baseline, output)
    data = json.loads(output.read_text(encoding="utf-8"))

    assert "risk_components" in data, "risk_components section missing"
    risk_score = (
        data["risk_components"].get("risk")
        if isinstance(data.get("risk_components"), dict)
        else None
    )
    assert isinstance(risk_score, (float, int)) and math.isfinite(float(risk_score))
