"""Approval queue persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from client_runtime.file_io import atomic_write_json

from .approval_renderer import render_approval_snapshot


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _build_items(
    *, generated: int, approved: int, sent: int, rejected: int
) -> list[dict[str, Any]]:
    total = max(0, generated)
    approved = max(0, min(total, approved))
    sent = max(0, min(approved, sent))
    rejected = max(0, min(total - approved, rejected))

    items: list[dict[str, Any]] = []
    for idx in range(1, total + 1):
        message_id = f"message-{idx:04d}"
        if idx <= sent:
            state = "sent"
        elif idx <= approved:
            state = "approved"
        elif idx <= approved + rejected:
            state = "rejected"
        else:
            state = "pending_approval"
        items.append({"id": message_id, "state": state})
    return items


def persist_approval_state(
    *,
    run_dir: Path,
    run_report: dict[str, Any],
) -> dict[str, Any]:
    outbound = run_report.get("outbound") if isinstance(run_report, dict) else {}
    outbound = outbound if isinstance(outbound, dict) else {}
    telemetry = outbound.get("pipeline_telemetry") if isinstance(outbound, dict) else {}
    telemetry = telemetry if isinstance(telemetry, dict) else {}
    health = telemetry.get("run_health") if isinstance(telemetry, dict) else {}
    health = health if isinstance(health, dict) else {}
    prospect_batch = (
        outbound.get("prospect_batch") if isinstance(outbound, dict) else {}
    )
    prospect_batch = prospect_batch if isinstance(prospect_batch, dict) else {}

    generated = _safe_int(
        prospect_batch.get("message_gen_pass")
        or prospect_batch.get("approved_pass_rows")
        or health.get("attempted")
        or health.get("sent")
    )
    approved = _safe_int(prospect_batch.get("approved_pass_rows") or health.get("sent"))
    sent = _safe_int(health.get("sent"))
    rejected = _safe_int(prospect_batch.get("message_gen_fail"))

    items = _build_items(
        generated=generated, approved=approved, sent=sent, rejected=rejected
    )
    snapshot = render_approval_snapshot(items)
    payload = {"items": items, "snapshot": snapshot}

    path = run_dir / "approval_queue.json"
    atomic_write_json(path, payload)

    return {
        "approval_queue": payload,
        "paths": {"approval_queue": str(path)},
    }
