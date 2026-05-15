"""Prospect queue lifecycle persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from client_runtime.file_io import atomic_write_json

VALID_QUEUE_STATES: tuple[str, ...] = (
    "queued",
    "processing",
    "sent",
    "replied",
    "bounced",
    "qualified",
    "disqualified",
)


def normalize_queue_state(value: str) -> str:
    state = (value or "").strip().lower()
    if state not in VALID_QUEUE_STATES:
        raise ValueError(f"invalid queue state: {value!r}")
    return state


def _queue_path(run_dir: Path) -> Path:
    return run_dir / "queue.json"


def load_queue(run_dir: Path) -> dict[str, Any]:
    path = _queue_path(run_dir)
    if not path.is_file():
        return {"items": [], "state_index": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"items": [], "state_index": {}}
    if not isinstance(payload, dict):
        return {"items": [], "state_index": {}}
    payload.setdefault("items", [])
    payload.setdefault("state_index", {})
    return payload


def save_queue(run_dir: Path, payload: dict[str, Any]) -> Path:
    path = _queue_path(run_dir)
    return atomic_write_json(path, payload)


def build_queue_items(
    *,
    queued_count: int,
    sent_count: int,
    replied_count: int,
    qualified_count: int,
    bounced_count: int = 0,
    disqualified_count: int = 0,
) -> list[dict[str, Any]]:
    total = max(0, int(queued_count))
    sent = max(0, min(total, int(sent_count)))
    replied = max(0, min(sent, int(replied_count)))
    qualified = max(0, min(replied, int(qualified_count)))
    bounced = max(0, min(sent - replied, int(bounced_count)))
    disqualified = max(0, min(replied - qualified, int(disqualified_count)))

    items: list[dict[str, Any]] = []
    for idx in range(1, total + 1):
        item_id = f"prospect-{idx:04d}"
        if idx <= qualified:
            state = "qualified"
        elif idx <= replied:
            state = "disqualified" if idx <= (qualified + disqualified) else "replied"
        elif idx <= sent:
            state = "bounced" if idx <= (replied + bounced) else "sent"
        else:
            state = "queued"
        items.append({"id": item_id, "state": state})
    return items
