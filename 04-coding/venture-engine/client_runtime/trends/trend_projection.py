"""Deterministic next-state projection from historical trend windows."""

from __future__ import annotations

from typing import Any


def _clamp(low: int, high: int, value: int) -> int:
    return max(low, min(high, value))


def build_trend_projection(
    timeline: list[dict[str, Any]],
    performance_windows: dict[str, Any],
) -> dict[str, Any]:
    recent = timeline[-3:]
    if not recent:
        return {
            "projected_state": "BASELINE",
            "risk_probability": "MEDIUM",
            "expected_health_range": [0, 100],
        }

    health_values = [int(item.get("health_score") or 0) for item in recent]
    reply_values = [float(item.get("reply_rate_pct") or 0.0) for item in recent]
    slope = health_values[-1] - health_values[0] if len(health_values) > 1 else 0
    reply_slope = reply_values[-1] - reply_values[0] if len(reply_values) > 1 else 0.0
    window_7 = (
        performance_windows.get("7_day")
        if isinstance(performance_windows, dict)
        else {}
    )
    window_7 = window_7 if isinstance(window_7, dict) else {}
    window_trend = str(window_7.get("trend") or "BASELINE")

    if slope >= 3 and reply_slope >= 1.0:
        projected_state = "IMPROVING"
        risk_probability = "LOW"
    elif slope <= -3 or reply_slope <= -1.0 or window_trend == "DECLINING":
        projected_state = "DECLINING"
        risk_probability = "HIGH"
    else:
        projected_state = "STABLE"
        risk_probability = "MEDIUM"

    last_health = health_values[-1]
    spread = max(3, abs(slope) + int(abs(reply_slope)))
    low = _clamp(0, 100, last_health - spread)
    high = _clamp(0, 100, last_health + spread)
    if high < low:
        low, high = high, low

    return {
        "projected_state": projected_state,
        "risk_probability": risk_probability,
        "expected_health_range": [low, high],
    }
