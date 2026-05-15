from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "04-coding" / "venture-engine"))

from client_runtime.patterns import update_pattern_memory


def test_update_pattern_memory_writes_ranked_output(tmp_path: Path) -> None:
    run_dir = tmp_path / "clients" / "acme-demo" / "runs" / "run-2"
    run_dir.mkdir(parents=True)

    run_report = {
        "outbound": {
            "pipeline_telemetry": {
                "run_health": {"sent": 10, "replies": 3, "qualified": 2}
            }
        }
    }
    reply_summary = {
        "classification_counts": {
            "positive": 2,
            "neutral": 0,
            "objection": 1,
            "unsubscribe": 0,
            "meeting_intent": 1,
        }
    }
    intake_context = {
        "execution_intent": {
            "persona": "Founder",
            "industry": "Healthcare",
            "icp": "Healthcare founders",
        }
    }

    outputs = update_pattern_memory(
        repo_root=tmp_path,
        run_dir=run_dir,
        client_id="acme-demo",
        run_id="run-2",
        intake_context=intake_context,
        subject_line="When they ask for the receipt",
        cta_pattern="Reply and I will show the trail",
        run_report=run_report,
        reply_summary=reply_summary,
    )

    memory_path = run_dir / "pattern_memory.json"
    assert memory_path.is_file()
    payload = json.loads(memory_path.read_text(encoding="utf-8"))
    assert payload["best_subject_lines"]
    assert payload["best_response_categories"][0]["pattern"] in {
        "positive",
        "meeting_intent",
    }
    assert outputs["paths"]["pattern_memory"].endswith("pattern_memory.json")
