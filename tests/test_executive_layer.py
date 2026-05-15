from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "04-coding" / "venture-engine"))

from client_runtime.executive import generate_executive_outputs


def _sample_inputs() -> tuple[dict, dict, dict, dict, dict]:
    run_report = {
        "run_id": "run-1",
        "timestamp_utc": "2026-05-15T10:00:00Z",
        "outbound": {
            "pipeline_telemetry": {
                "run_health": {
                    "sent": 40,
                    "replies": 8,
                    "qualified": 2,
                    "reply_rate_estimate": 0.2,
                }
            }
        },
    }
    projection = {"ranked_signals": [{"title": "Healthcare ICP", "severity_score": 88}]}
    comparison = {
        "trend": "IMPROVING",
        "metrics_delta": {"reply_rate_delta": 0.22, "qualification_rate_delta": 0.05},
        "breakpoints": [],
        "notable_changes": ["Reply rate improved"],
    }
    health = {"health_score": 81, "label": "HEALTHY", "risk_flags": []}
    value_summary = {
        "summary": {
            "performance_overview": "This run sent 40 messages, received 8 replies, and produced 2 qualified conversations.",
            "what_is_working": ["Healthcare ICP is outperforming the baseline."],
            "recommended_actions": ["Increase healthcare segment allocation"],
        }
    }
    return run_report, projection, comparison, health, value_summary


def test_generate_executive_outputs(tmp_path: Path) -> None:
    run_dir = tmp_path / "clients" / "acme-demo" / "runs" / "run-1"
    run_dir.mkdir(parents=True)

    run_report, projection, comparison, health, value_summary = _sample_inputs()
    outputs = generate_executive_outputs(
        run_dir=run_dir,
        client_id="acme-demo",
        run_report=run_report,
        projection=projection,
        comparison=comparison,
        health=health,
        value_summary=value_summary,
    )

    summary_path = run_dir / "executive_summary.json"
    brief_path = run_dir / "executive_brief.html"
    snapshot_path = run_dir / "stakeholder_snapshot.json"
    roi_path = run_dir / "roi_projection.json"

    assert summary_path.is_file()
    assert brief_path.is_file()
    assert snapshot_path.is_file()
    assert roi_path.is_file()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    roi = json.loads(roi_path.read_text(encoding="utf-8"))
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert summary["campaign_status"] == "IMPROVING"
    assert summary["business_impact"] == "Reply efficiency improved 22%"
    assert summary["recommended_action"] == "Increase healthcare segment allocation"
    assert roi["trajectory"] == "POSITIVE"
    assert snapshot["audience"] == "executive"
    assert "Executive Brief" in outputs["executive_brief"]
