"""Deterministic campaign health scoring from comparison output."""

from __future__ import annotations

from typing import Any


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _component_reply_rate(delta: float) -> float:
    # 0 delta => 50 baseline, +/-10pp gives near extrema.
    return _clamp(50.0 + (delta * 500.0))


def _component_qualification_rate(delta: float) -> float:
    return _clamp(50.0 + (delta * 500.0))


def _component_signal_degradation(severity_delta: float) -> float:
    # Higher severity is worse.
    if severity_delta <= 0:
        return _clamp(75.0 + abs(severity_delta) * 2.0)
    return _clamp(75.0 - (severity_delta * 4.0))


def _component_volume_stability(
    sent_delta: int, baseline_sent: int | None = None
) -> float:
    if baseline_sent and baseline_sent > 0:
        ratio = abs(sent_delta) / baseline_sent
    else:
        ratio = abs(sent_delta) / 100.0
    return _clamp(100.0 - (ratio * 100.0))


def _label(score: int) -> str:
    if score < 35:
        return "CRITICAL"
    if score < 55:
        return "LOW"
    if score < 75:
        return "MEDIUM"
    return "HEALTHY"


def compute_health(comparison: dict[str, Any]) -> dict[str, Any]:
    trend = str(comparison.get("trend") or "BASELINE")
    if trend == "BASELINE":
        return {
            "health_score": 70,
            "label": "BASELINE",
            "drivers": ["No previous run history"],
            "risk_flags": ["no_history"],
        }

    metrics_delta = (
        comparison.get("metrics_delta") if isinstance(comparison, dict) else {}
    )
    metrics_delta = metrics_delta if isinstance(metrics_delta, dict) else {}
    signal_delta = (
        comparison.get("signal_delta") if isinstance(comparison, dict) else {}
    )
    signal_delta = signal_delta if isinstance(signal_delta, dict) else {}

    reply_rate_delta = float(metrics_delta.get("reply_rate_delta") or 0.0)
    qualification_rate_delta = float(
        metrics_delta.get("qualification_rate_delta") or 0.0
    )
    sent_delta = int(metrics_delta.get("sent_delta") or 0)
    severity_delta = float(signal_delta.get("severity_delta") or 0.0)

    reply_component = _component_reply_rate(reply_rate_delta)
    qualification_component = _component_qualification_rate(qualification_rate_delta)
    signal_component = _component_signal_degradation(severity_delta)
    volume_component = _component_volume_stability(sent_delta)

    score = int(
        round(
            (reply_component * 0.40)
            + (qualification_component * 0.30)
            + (signal_component * 0.20)
            + (volume_component * 0.10)
        )
    )

    drivers = [
        f"reply_rate_component={reply_component:.1f}",
        f"qualification_component={qualification_component:.1f}",
        f"signal_component={signal_component:.1f}",
        f"volume_component={volume_component:.1f}",
    ]

    risk_flags: list[str] = []
    if reply_rate_delta < -0.03:
        risk_flags.append("reply_rate_decline")
    if qualification_rate_delta < -0.03:
        risk_flags.append("qualification_decline")
    if severity_delta > 10.0:
        risk_flags.append("signal_degradation")
    if sent_delta < -20:
        risk_flags.append("volume_instability")

    return {
        "health_score": max(0, min(100, score)),
        "label": _label(score),
        "drivers": drivers,
        "risk_flags": risk_flags,
    }
