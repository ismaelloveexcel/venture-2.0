from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "04-coding" / "venture-engine"))

from client_runtime.replies.reply_classifier import classify_reply
from client_runtime.replies.reply_summary import generate_reply_summary


def test_classify_reply_rules() -> None:
    assert classify_reply("Please unsubscribe me") == "unsubscribe"
    assert classify_reply("Can we schedule a call next week?") == "meeting_intent"
    assert classify_reply("Not interested right now") == "objection"
    assert classify_reply("Sounds good, interested") == "positive"
    assert classify_reply("Thanks") in {"positive", "neutral"}


def test_generate_reply_summary_writes_json(tmp_path: Path) -> None:
    run_dir = tmp_path / "clients" / "acme-demo" / "runs" / "run-1"
    run_dir.mkdir(parents=True)

    run_report = {
        "outbound": {
            "pipeline_telemetry": {"run_health": {"replies": 4}}
        }
    }
    texts = [
        "Interested. Send times.",
        "Not interested.",
        "Please unsubscribe me.",
    ]

    outputs = generate_reply_summary(
        run_dir=run_dir,
        run_report=run_report,
        reply_texts=texts,
    )

    summary_path = run_dir / "reply_summary.json"
    assert summary_path.is_file()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["classification_counts"]["meeting_intent"] >= 1
    assert "unsubscribe" in outputs["reply_summary"]["classification_counts"]
