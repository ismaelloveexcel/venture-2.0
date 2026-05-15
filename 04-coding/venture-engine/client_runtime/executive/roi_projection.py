"""Deterministic ROI projection from current and previous run indicators."""

from __future__ import annotations

from typing import Any


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def build_roi_projection(
    *,
    run_report: dict[str, Any],
    comparison: dict[str, Any],
    health: dict[str, Any],
) -> dict[str, Any]:
    outbound = run_report.get("outbound") if isinstance(run_report, dict) else {}
    outbound = outbound if isinstance(outbound, dict) else {}
    telemetry = outbound.get("pipeline_telemetry")
    telemetry = telemetry if isinstance(telemetry, dict) else {}
    run_health = telemetry.get("run_health")
    run_health = run_health if isinstance(run_health, dict) else {}

    sent = max(0, _safe_int(run_health.get("sent")))
    replies = max(0, _safe_int(run_health.get("replies")))
    qualified = max(0, _safe_int(run_health.get("qualified")))
    reply_rate = _safe_float(
        run_health.get("reply_rate_estimate") or run_health.get("reply_rate")
    )
    if sent > 0 and reply_rate <= 0.0:
        reply_rate = replies / sent
    qualified_rate = (qualified / sent) if sent > 0 else 0.0

    current_trajectory = str(comparison.get("trend") or "BASELINE").upper()
    previous_trajectory = str(health.get("label") or "BASELINE").upper()

    multiplier = 1.0
    if current_trajectory == "IMPROVING":
        multiplier += 0.20
    elif current_trajectory == "DECLINING":
        multiplier -= 0.20
    if previous_trajectory in {"HEALTHY", "MEDIUM"}:
        multiplier += 0.05
    elif previous_trajectory in {"LOW", "CRITICAL"}:
        multiplier -= 0.05

    volume_anchor = max(1, sent)
    projected_replies_30d = max(
        0, int(round(volume_anchor * reply_rate * 30 * multiplier))
    )
    projected_qualified_30d = max(
        0, int(round(volume_anchor * qualified_rate * 30 * multiplier))
    )

    if current_trajectory == "IMPROVING":
        trajectory = "POSITIVE"
    elif current_trajectory == "DECLINING":
        trajectory = "NEGATIVE"
    else:
        trajectory = "STABLE"

    if trajectory == "POSITIVE":
        confidence = "HIGH" if _safe_int(health.get("health_score")) >= 75 else "MEDIUM"
    elif trajectory == "NEGATIVE":
        confidence = "LOW"
    else:
        confidence = "MEDIUM"

    return {
        "projected_replies_30d": projected_replies_30d,
        "projected_qualified_30d": projected_qualified_30d,
        "trajectory": trajectory,
        "confidence": confidence,
    }
