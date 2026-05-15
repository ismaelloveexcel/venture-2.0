"""Deterministic executive summary builder."""

from __future__ import annotations

from typing import Any


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _trend_status(comparison: dict[str, Any], health: dict[str, Any]) -> str:
    trend = str(comparison.get("trend") or "BASELINE").upper()
    health_label = str(health.get("label") or "BASELINE").upper()
    breakpoints = list(comparison.get("breakpoints") or [])
    if trend == "BASELINE":
        return "BASELINE"
    if health_label in {"CRITICAL", "LOW"} or breakpoints:
        return "DECLINING" if trend == "DECLINING" else "AT_RISK"
    if trend == "IMPROVING":
        return "IMPROVING"
    if trend == "DECLINING":
        return "DECLINING"
    return "STABLE"


def _business_impact(comparison: dict[str, Any], value_summary: dict[str, Any]) -> str:
    metrics_delta = (
        comparison.get("metrics_delta") if isinstance(comparison, dict) else {}
    )
    metrics_delta = metrics_delta if isinstance(metrics_delta, dict) else {}
    reply_delta = _safe_float(metrics_delta.get("reply_rate_delta"))
    qual_delta = _safe_float(metrics_delta.get("qualification_rate_delta"))

    if reply_delta > 0:
        return f"Reply efficiency improved {int(round(reply_delta * 100))}%"
    if reply_delta < 0:
        return f"Reply efficiency declined {abs(int(round(reply_delta * 100)))}%"
    if qual_delta > 0:
        return f"Qualified lead efficiency improved {int(round(qual_delta * 100))}%"
    if qual_delta < 0:
        return (
            f"Qualified lead efficiency declined {abs(int(round(qual_delta * 100)))}%"
        )

    overview = str(
        (value_summary.get("summary") or {}).get("performance_overview")
        or "Run completed without comparative change."
    )
    return overview


def _primary_risk(comparison: dict[str, Any], health: dict[str, Any]) -> str:
    risk_flags = list(health.get("risk_flags") or [])
    breakpoints = list(comparison.get("breakpoints") or [])
    mapping = {
        "qualification_rate_drop": "Qualified lead velocity below target",
        "reply_rate_drop": "Reply efficiency below target",
        "signal_degradation": "Signal quality weakening",
        "volume_drop": "Send volume below plan",
        "reply_rate_decline": "Reply efficiency below target",
        "qualification_decline": "Qualified lead velocity below target",
        "signal_degradation": "Signal quality weakening",
        "volume_instability": "Send volume below plan",
    }
    for token in breakpoints:
        if token in mapping:
            return mapping[token]
    for token in risk_flags:
        if token in mapping:
            return mapping[token]
    return "No material risk identified"


def _top_opportunity(projection: dict[str, Any], value_summary: dict[str, Any]) -> str:
    summary = value_summary.get("summary") if isinstance(value_summary, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    working = list(summary.get("what_is_working") or [])
    if working:
        return str(working[0])
    ranked = list((projection or {}).get("ranked_signals") or [])
    if ranked:
        first = ranked[0] if isinstance(ranked[0], dict) else {}
        title = str(first.get("title") or first.get("name") or first.get("id") or "")
        if title:
            return title
    return "Highest-performing segment shows room for expansion"


def _recommended_action(
    value_summary: dict[str, Any], comparison: dict[str, Any]
) -> str:
    summary = value_summary.get("summary") if isinstance(value_summary, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    recs = list(summary.get("recommended_actions") or [])
    if recs:
        return str(recs[0])
    trend = str(comparison.get("trend") or "BASELINE").upper()
    if trend == "IMPROVING":
        return "Increase allocation to the highest-performing segment"
    if trend == "DECLINING":
        return "Tighten targeting and refresh messaging before scaling"
    return "Maintain current approach and continue weekly review"


def _confidence_score(health: dict[str, Any], comparison: dict[str, Any]) -> int:
    score = _safe_int(health.get("health_score"))
    trend = str(comparison.get("trend") or "BASELINE").upper()
    if trend == "IMPROVING":
        score += 8
    elif trend == "DECLINING":
        score -= 8
    elif trend == "BASELINE":
        score += 4
    if list(comparison.get("breakpoints") or []):
        score -= 10
    return max(0, min(100, score))


def build_executive_summary(
    *,
    run_report: dict[str, Any],
    projection: dict[str, Any],
    comparison: dict[str, Any],
    health: dict[str, Any],
    value_summary: dict[str, Any],
) -> dict[str, Any]:
    campaign_status = _trend_status(comparison, health)
    summary = {
        "campaign_status": campaign_status,
        "business_impact": _business_impact(comparison, value_summary),
        "primary_risk": _primary_risk(comparison, health),
        "top_opportunity": _top_opportunity(projection, value_summary),
        "recommended_action": _recommended_action(value_summary, comparison),
        "confidence": _confidence_score(health, comparison),
    }
    # Keep the output stable and ordered.
    return summary
