"""Commercial snapshot builder for sales acceleration artifacts."""

from __future__ import annotations

from typing import Any


def build_commercial_snapshot(
    *,
    client_id: str,
    executive_outputs: dict[str, Any],
    trend_outputs: dict[str, Any],
    operator_outputs: dict[str, Any],
    roi_projection: dict[str, Any],
) -> dict[str, Any]:
    executive_summary = executive_outputs.get("executive_summary") or {}
    trend_summary = trend_outputs.get("trend_summary") or {}
    workflow_state = operator_outputs.get("workflow_state") or {}
    proof_points = [
        str(executive_summary.get("business_impact") or ""),
        str(executive_summary.get("top_opportunity") or ""),
        str((trend_summary.get("trend_projection") or {}).get("projected_state") or ""),
    ]
    return {
        "client": client_id,
        "headline": str(executive_summary.get("campaign_status") or "BASELINE"),
        "proof_points": proof_points,
        "priority_action": str(workflow_state.get("next_action") or "None"),
        "risk": str(
            executive_summary.get("primary_risk") or "No material risk identified"
        ),
        "roi_projection": roi_projection,
    }
