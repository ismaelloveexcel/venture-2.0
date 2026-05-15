"""Executive stakeholder snapshot builder."""

from __future__ import annotations

from typing import Any


def build_stakeholder_snapshot(
    *,
    client_id: str,
    executive_summary: dict[str, Any],
    roi_projection: dict[str, Any],
    value_summary: dict[str, Any],
) -> dict[str, Any]:
    summary = value_summary.get("summary") if isinstance(value_summary, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    return {
        "client_id": client_id,
        "audience": "executive",
        "campaign_status": executive_summary.get("campaign_status", "BASELINE"),
        "decision_focus": executive_summary.get(
            "recommended_action", "Maintain current approach"
        ),
        "proof_points": [
            str(executive_summary.get("business_impact") or ""),
            str(executive_summary.get("top_opportunity") or ""),
            str((summary.get("performance_overview") or "")),
        ],
        "roi_projection": roi_projection,
    }
