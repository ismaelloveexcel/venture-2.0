from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "04-coding" / "venture-engine"))

from client_runtime.approval import persist_approval_state


def test_persist_approval_state(tmp_path: Path) -> None:
    run_dir = tmp_path / "clients" / "acme-demo" / "runs" / "run-1"
    run_dir.mkdir(parents=True)

    run_report = {
        "outbound": {
            "prospect_batch": {
                "message_gen_pass": 6,
                "approved_pass_rows": 5,
                "message_gen_fail": 1,
            },
            "pipeline_telemetry": {"run_health": {"sent": 4}},
        }
    }

    outputs = persist_approval_state(run_dir=run_dir, run_report=run_report)

    approval_path = run_dir / "approval_queue.json"
    assert approval_path.is_file()
    payload = json.loads(approval_path.read_text(encoding="utf-8"))
    assert payload["snapshot"]["status_counts"]["sent"] == 4
    assert outputs["paths"]["approval_queue"].endswith("approval_queue.json")
