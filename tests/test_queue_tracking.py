from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "04-coding" / "venture-engine"))

from client_runtime.queue import update_prospect_queue


def test_update_prospect_queue_writes_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "clients" / "acme-demo" / "runs" / "run-1"
    run_dir.mkdir(parents=True)

    run_report = {
        "outbound": {
            "pipeline_telemetry": {
                "run_health": {
                    "attempted": 10,
                    "sent": 8,
                    "replies": 3,
                    "qualified": 1,
                    "blocked": 2,
                }
            }
        }
    }

    outputs = update_prospect_queue(run_dir=run_dir, run_report=run_report)

    queue_path = run_dir / "queue.json"
    metrics_path = run_dir / "queue_metrics.json"
    assert queue_path.is_file()
    assert metrics_path.is_file()

    queue_payload = json.loads(queue_path.read_text(encoding="utf-8"))
    metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8"))

    assert len(queue_payload["items"]) == 10
    assert metrics_payload["status_counts"]["qualified"] == 1
    assert outputs["paths"]["queue"].endswith("queue.json")
