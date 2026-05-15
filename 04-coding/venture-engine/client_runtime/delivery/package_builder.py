"""Assemble deterministic delivery package payloads from existing artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_delivery_package(
    *,
    client_id: str,
    run_id: str,
    run_timestamp: str,
    engine_version: str,
    run_dir: Path,
    artifact_paths: dict[str, str],
    intake_context: dict[str, Any],
) -> dict[str, Any]:
    ordered_items = {
        "dashboard": str(run_dir / "dashboard.html"),
        "health": str(run_dir / "health.json"),
        "comparison": str(run_dir / "comparison.json"),
        "summary": str(run_dir / "value_summary.json"),
    }

    # Keep explicit values from caller when provided, fall back to deterministic defaults.
    for key, path in artifact_paths.items():
        if key in ordered_items and path:
            ordered_items[key] = str(Path(path))

    return {
        "client_id": client_id,
        "run_id": run_id,
        "delivery_items": ordered_items,
        "execution_metadata": {
            "run_timestamp": run_timestamp,
            "engine_version": engine_version,
        },
        "intake_context": intake_context,
    }
