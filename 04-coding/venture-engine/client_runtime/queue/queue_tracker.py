"""Queue update orchestrator for a run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .prospect_queue import build_queue_items, load_queue, save_queue
from .queue_metrics import build_queue_metrics, save_queue_metrics


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def update_prospect_queue(*, run_dir: Path, run_report: dict[str, Any]) -> dict[str, Any]:
    outbound = run_report.get("outbound") if isinstance(run_report, dict) else {}
    outbound = outbound if isinstance(outbound, dict) else {}
    telemetry = outbound.get("pipeline_telemetry") if isinstance(outbound, dict) else {}
    telemetry = telemetry if isinstance(telemetry, dict) else {}
    health = telemetry.get("run_health") if isinstance(telemetry, dict) else {}
    health = health if isinstance(health, dict) else {}
    prospect_batch = outbound.get("prospect_batch") if isinstance(outbound, dict) else {}
    prospect_batch = prospect_batch if isinstance(prospect_batch, dict) else {}

    queued = _safe_int(
        health.get("attempted")
        or health.get("generated")
        or prospect_batch.get("approved_pass_rows")
        or prospect_batch.get("ready")
        or health.get("sent")
    )
    sent = _safe_int(health.get("sent"))
    replied = _safe_int(health.get("replies"))
    qualified = _safe_int(health.get("qualified"))
    blocked = _safe_int(health.get("blocked"))

    load_queue(run_dir)  # Maintains deterministic behavior if previous file exists.
    items = build_queue_items(
        queued_count=max(queued, sent, replied, qualified),
        sent_count=sent,
        replied_count=replied,
        qualified_count=qualified,
        bounced_count=blocked,
    )

    state_index = {item["id"]: item["state"] for item in items}
    queue_payload = {"items": items, "state_index": state_index}
    queue_path = save_queue(run_dir, queue_payload)

    metrics_payload = build_queue_metrics(items)
    metrics_path = save_queue_metrics(run_dir, metrics_payload)

    return {
        "queue": queue_payload,
        "metrics": metrics_payload,
        "paths": {
            "queue": str(queue_path),
            "queue_metrics": str(metrics_path),
        },
    }
