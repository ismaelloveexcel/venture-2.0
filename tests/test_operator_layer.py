from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "04-coding" / "venture-engine"))

from client_runtime.operator import generate_operator_outputs


def test_generate_operator_outputs(tmp_path: Path) -> None:
    run_dir = tmp_path / "clients" / "acme-demo" / "runs" / "run-1"
    run_dir.mkdir(parents=True)

    executive_outputs = {
        "executive_summary": {
            "campaign_status": "DECLINING",
            "business_impact": "Reply efficiency declined 18%",
            "primary_risk": "Qualified lead velocity below target",
            "top_opportunity": "Healthcare ICP outperforming baseline",
            "recommended_action": "Review healthcare messaging",
            "confidence": 78,
        }
    }
    trend_outputs = {
        "trend_projection": {"projected_state": "DECLINING", "risk_probability": "HIGH"}
    }
    health = {"label": "LOW", "health_score": 61}
    value_summary = {
        "summary": {"recommended_actions": ["Review healthcare messaging"]}
    }

    outputs = generate_operator_outputs(
        run_dir=run_dir,
        executive_outputs=executive_outputs,
        trend_outputs=trend_outputs,
        health=health,
        value_summary=value_summary,
    )

    queue_path = run_dir / "operator_queue.json"
    tasks_path = run_dir / "operator_tasks.json"
    priority_path = run_dir / "priority_actions.json"
    workflow_path = run_dir / "workflow_state.json"

    assert queue_path.is_file()
    assert tasks_path.is_file()
    assert priority_path.is_file()
    assert workflow_path.is_file()

    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    priority = json.loads(priority_path.read_text(encoding="utf-8"))
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))

    assert queue["queue"]
    assert tasks["tasks"]
    assert priority["actions"]
    assert workflow["state"] in {
        "ACTION_REQUIRED",
        "REVIEW_REQUIRED",
        "MONITOR",
        "IDLE",
    }
    assert outputs["operator_queue"]["queue_size"] >= 1
