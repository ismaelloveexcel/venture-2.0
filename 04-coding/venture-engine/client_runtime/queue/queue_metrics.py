"""Queue metrics generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from client_runtime.file_io import atomic_write_json

from .prospect_queue import VALID_QUEUE_STATES


def _metrics_path(run_dir: Path) -> Path:
    return run_dir / "queue_metrics.json"


def build_queue_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {state: 0 for state in VALID_QUEUE_STATES}
    for item in items:
        state = str(item.get("state") or "").strip().lower()
        if state in counts:
            counts[state] += 1

    sent_or_beyond = (
        counts["sent"]
        + counts["replied"]
        + counts["bounced"]
        + counts["qualified"]
        + counts["disqualified"]
    )
    replied_or_beyond = counts["replied"] + counts["qualified"] + counts["disqualified"]
    qualified = counts["qualified"]

    return {
        "total": len(items),
        "status_counts": counts,
        "sent_rate": round((sent_or_beyond / len(items)) if items else 0.0, 6),
        "reply_rate": round((replied_or_beyond / len(items)) if items else 0.0, 6),
        "qualification_rate": round((qualified / len(items)) if items else 0.0, 6),
    }


def save_queue_metrics(run_dir: Path, payload: dict[str, Any]) -> Path:
    path = _metrics_path(run_dir)
    return atomic_write_json(path, payload)
