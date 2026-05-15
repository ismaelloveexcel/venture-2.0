from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = REPO_ROOT / "04-coding" / "venture-engine"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from client_runtime.comparison_engine import run_comparison
from client_runtime.health_score import compute_health
from client_runtime.run_history import get_previous_run


def _mk_report(run_id: str, sent: int, replies: int, qualified: int) -> dict:
    return {
        "run_id": run_id,
        "timestamp_utc": "2026-05-14T00:00:00Z",
        "outbound": {
            "pipeline_telemetry": {
                "schema_version": 1,
                "run_health": {
                    "sent": sent,
                    "replies": replies,
                    "qualified": qualified,
                },
            }
        },
    }


def test_comparison_baseline_and_health_baseline():
    current = _mk_report("r1", 100, 10, 5)
    comparison = run_comparison(
        current_report=current,
        current_projection={},
        previous_report=None,
        previous_projection=None,
    )
    assert comparison["trend"] == "BASELINE"

    health = compute_health(comparison)
    assert health["label"] == "BASELINE"
    assert health["health_score"] == 70
    assert "no_history" in health["risk_flags"]


def test_comparison_and_health_deterministic_deltas():
    previous = _mk_report("r0", 100, 12, 6)
    current = _mk_report("r1", 110, 8, 4)
    prev_projection = {
        "ranked_signals": [{"id": "s1", "severity_score": 40}],
    }
    curr_projection = {
        "ranked_signals": [{"id": "s1", "severity_score": 65}],
    }

    comparison = run_comparison(
        current_report=current,
        current_projection=curr_projection,
        previous_report=previous,
        previous_projection=prev_projection,
    )
    assert comparison["trend"] in {"IMPROVING", "DECLINING", "STABLE"}
    assert comparison["metrics_delta"]["sent_delta"] == 10
    assert comparison["signal_delta"]["severity_delta"] > 0

    health = compute_health(comparison)
    assert 0 <= health["health_score"] <= 100
    assert health["label"] in {"CRITICAL", "LOW", "MEDIUM", "HEALTHY"}


def test_get_previous_run_excludes_current(tmp_path: Path):
    client_id = "c1"
    runs_dir = tmp_path / "clients" / client_id / "runs"
    runs_dir.mkdir(parents=True)

    old_run = runs_dir / "old"
    current_run = runs_dir / "current"
    old_run.mkdir()
    current_run.mkdir()

    (old_run / "x.txt").write_text("old", encoding="utf-8")
    (current_run / "x.txt").write_text("new", encoding="utf-8")

    prev = get_previous_run(client_id, "current", repo_root=tmp_path)
    assert prev is not None
    assert prev.name == "old"
