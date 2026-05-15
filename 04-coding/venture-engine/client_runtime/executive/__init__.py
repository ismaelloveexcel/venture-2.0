"""Executive delivery layer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from client_runtime.file_io import atomic_write_json, atomic_write_text

from .executive_brief import render_executive_brief_html
from .executive_summary import build_executive_summary
from .roi_projection import build_roi_projection
from .stakeholder_snapshot import build_stakeholder_snapshot


def generate_executive_outputs(
    *,
    run_dir: Path,
    client_id: str,
    run_report: dict[str, Any],
    projection: dict[str, Any],
    comparison: dict[str, Any],
    health: dict[str, Any],
    value_summary: dict[str, Any],
) -> dict[str, Any]:
    executive_summary = build_executive_summary(
        run_report=run_report,
        projection=projection,
        comparison=comparison,
        health=health,
        value_summary=value_summary,
    )
    roi_projection = build_roi_projection(
        run_report=run_report,
        comparison=comparison,
        health=health,
    )
    stakeholder_snapshot = build_stakeholder_snapshot(
        client_id=client_id,
        executive_summary=executive_summary,
        roi_projection=roi_projection,
        value_summary=value_summary,
    )
    brief_html = render_executive_brief_html(
        client_id=client_id,
        executive_summary=executive_summary,
        roi_projection=roi_projection,
        stakeholder_snapshot=stakeholder_snapshot,
    )

    summary_path = run_dir / "executive_summary.json"
    brief_path = run_dir / "executive_brief.html"
    snapshot_path = run_dir / "stakeholder_snapshot.json"
    roi_path = run_dir / "roi_projection.json"

    atomic_write_json(summary_path, executive_summary)
    atomic_write_text(brief_path, brief_html)
    atomic_write_json(snapshot_path, stakeholder_snapshot)
    atomic_write_json(roi_path, roi_projection)

    return {
        "executive_summary": executive_summary,
        "executive_brief": brief_html,
        "stakeholder_snapshot": stakeholder_snapshot,
        "roi_projection": roi_projection,
        "paths": {
            "executive_summary": str(summary_path),
            "executive_brief": str(brief_path),
            "stakeholder_snapshot": str(snapshot_path),
            "roi_projection": str(roi_path),
        },
    }
