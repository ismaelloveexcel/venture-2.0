"""Build deterministic client value summary from existing run artifacts."""

from __future__ import annotations

from typing import Any

from .narrative_builder import build_narrative


def generate_value_summary(
    run_report: dict[str, Any],
    projection: dict[str, Any],
    comparison: dict[str, Any],
    health: dict[str, Any],
) -> dict[str, Any]:
    narrative = build_narrative(
        run_report=run_report,
        projection=projection,
        comparison=comparison,
        health=health,
    )
    return {"summary": narrative}
