"""Load prior pattern memory for deterministic continuation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_latest_pattern_memory(
    *, repo_root: Path, client_id: str, current_run_id: str
) -> dict[str, Any]:
    runs_dir = repo_root / "clients" / str(client_id) / "runs"
    if not runs_dir.is_dir():
        return {}

    candidates = sorted(
        [
            path
            for path in runs_dir.glob("*/pattern_memory.json")
            if path.parent.name != current_run_id
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return {}
