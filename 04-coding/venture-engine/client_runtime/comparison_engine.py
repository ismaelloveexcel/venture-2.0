"""Deterministic run comparison using run_report + projection artifacts only."""

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


def _extract_metrics(run_report: dict[str, Any]) -> dict[str, float]:
    outbound = run_report.get("outbound") if isinstance(run_report, dict) else {}
    outbound = outbound if isinstance(outbound, dict) else {}
    telemetry = outbound.get("pipeline_telemetry")
    telemetry = telemetry if isinstance(telemetry, dict) else {}
    run_health = telemetry.get("run_health")
    run_health = run_health if isinstance(run_health, dict) else {}

    sent = _safe_int(run_health.get("sent"))
    replies = _safe_int(run_health.get("replies"))
    qualified = _safe_int(run_health.get("qualified"))
    reply_rate = _safe_float(
        run_health.get("reply_rate_estimate") or run_health.get("reply_rate")
    )
    if sent > 0 and reply_rate <= 0.0:
        reply_rate = replies / sent
    qualification_rate = (qualified / sent) if sent > 0 else 0.0

    return {
        "sent": float(sent),
        "replies": float(replies),
        "qualified": float(qualified),
        "reply_rate": reply_rate,
        "qualification_rate": qualification_rate,
    }


def _extract_ranked_signals(projection: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(projection, dict):
        return []
    ranked = projection.get("ranked_signals")
    if isinstance(ranked, list):
        return [x for x in ranked if isinstance(x, dict)]
    meta = projection.get("insight_metadata")
    if isinstance(meta, dict) and isinstance(meta.get("ranked_signals"), list):
        return [x for x in meta["ranked_signals"] if isinstance(x, dict)]
    return []


def _avg_severity(signals: list[dict[str, Any]]) -> float:
    if not signals:
        return 0.0
    values: list[float] = []
    for signal in signals:
        values.append(
            _safe_float(
                signal.get("severity_score")
                or signal.get("severity")
                or signal.get("score")
            )
        )
    return (sum(values) / len(values)) if values else 0.0


def _rank_map(signals: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for index, signal in enumerate(signals):
        key = str(
            signal.get("id")
            or signal.get("signal_id")
            or signal.get("title")
            or signal.get("name")
            or f"signal_{index + 1}"
        )
        out[key] = index + 1
    return out


def run_comparison(
    *,
    current_report: dict[str, Any],
    current_projection: dict[str, Any] | None,
    previous_report: dict[str, Any] | None,
    previous_projection: dict[str, Any] | None,
) -> dict[str, Any]:
    current_metrics = _extract_metrics(current_report)

    if not previous_report:
        return {
            "trend": "BASELINE",
            "metrics_delta": {
                "sent_delta": 0,
                "replies_delta": 0,
                "qualified_delta": 0,
                "reply_rate_delta": 0.0,
                "qualification_rate_delta": 0.0,
            },
            "signal_delta": {
                "severity_delta": 0.0,
                "ranked_signal_changes": [],
            },
            "notable_changes": ["Baseline run: no previous history"],
            "breakpoints": [],
        }

    previous_metrics = _extract_metrics(previous_report)
    sent_delta = int(current_metrics["sent"] - previous_metrics["sent"])
    replies_delta = int(current_metrics["replies"] - previous_metrics["replies"])
    qualified_delta = int(current_metrics["qualified"] - previous_metrics["qualified"])
    reply_rate_delta = current_metrics["reply_rate"] - previous_metrics["reply_rate"]
    qualification_rate_delta = (
        current_metrics["qualification_rate"] - previous_metrics["qualification_rate"]
    )

    curr_signals = _extract_ranked_signals(current_projection or {})
    prev_signals = _extract_ranked_signals(previous_projection or {})
    curr_sev = _avg_severity(curr_signals)
    prev_sev = _avg_severity(prev_signals)
    severity_delta = curr_sev - prev_sev

    curr_rank = _rank_map(curr_signals)
    prev_rank = _rank_map(prev_signals)
    rank_changes: list[dict[str, Any]] = []
    for key in sorted(set(curr_rank) | set(prev_rank)):
        rank_changes.append(
            {
                "signal": key,
                "current_rank": curr_rank.get(key),
                "previous_rank": prev_rank.get(key),
            }
        )

    notable_changes: list[str] = []
    breakpoints: list[str] = []

    if reply_rate_delta > 0.01:
        notable_changes.append("Reply rate improved")
    elif reply_rate_delta < -0.01:
        notable_changes.append("Reply rate declined")

    if qualification_rate_delta > 0.01:
        notable_changes.append("Qualification rate improved")
    elif qualification_rate_delta < -0.01:
        notable_changes.append("Qualification rate declined")

    if severity_delta > 5.0:
        notable_changes.append("Signal severity increased")
    elif severity_delta < -5.0:
        notable_changes.append("Signal severity decreased")

    if reply_rate_delta <= -0.03:
        breakpoints.append("reply_rate_drop")
    if qualification_rate_delta <= -0.03:
        breakpoints.append("qualification_rate_drop")
    if severity_delta >= 10.0:
        breakpoints.append("signal_degradation")
    if sent_delta <= -20:
        breakpoints.append("volume_drop")

    improving_score = 0
    declining_score = 0
    if reply_rate_delta > 0:
        improving_score += 1
    elif reply_rate_delta < 0:
        declining_score += 1
    if qualification_rate_delta > 0:
        improving_score += 1
    elif qualification_rate_delta < 0:
        declining_score += 1
    if severity_delta < 0:
        improving_score += 1
    elif severity_delta > 0:
        declining_score += 1

    if improving_score > declining_score:
        trend = "IMPROVING"
    elif declining_score > improving_score:
        trend = "DECLINING"
    else:
        trend = "STABLE"

    return {
        "trend": trend,
        "metrics_delta": {
            "sent_delta": sent_delta,
            "replies_delta": replies_delta,
            "qualified_delta": qualified_delta,
            "reply_rate_delta": round(reply_rate_delta, 6),
            "qualification_rate_delta": round(qualification_rate_delta, 6),
        },
        "signal_delta": {
            "severity_delta": round(severity_delta, 4),
            "ranked_signal_changes": rank_changes,
        },
        "notable_changes": notable_changes,
        "breakpoints": breakpoints,
    }
