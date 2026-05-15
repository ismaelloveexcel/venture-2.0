"""Rule-based narrative mapper for client-readable summaries."""

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


def build_narrative(
    run_report: dict[str, Any],
    projection: dict[str, Any],
    comparison: dict[str, Any],
    health: dict[str, Any],
) -> dict[str, Any]:
    outbound = run_report.get("outbound") if isinstance(run_report, dict) else {}
    outbound = outbound if isinstance(outbound, dict) else {}
    telemetry = outbound.get("pipeline_telemetry")
    telemetry = telemetry if isinstance(telemetry, dict) else {}
    run_health = telemetry.get("run_health")
    run_health = run_health if isinstance(run_health, dict) else {}

    sent = _safe_int(run_health.get("sent"))
    replies = _safe_int(run_health.get("replies"))
    qualified = _safe_int(run_health.get("qualified"))

    if sent > 0:
        overview = (
            f"This run sent {sent} messages, received {replies} replies, "
            f"and produced {qualified} qualified conversations."
        )
    else:
        overview = "This run completed with no outbound sends."

    trend = str(comparison.get("trend") or "BASELINE").upper()
    what_changed: list[str] = []
    if trend == "IMPROVING":
        what_changed.append("Overall momentum improved compared with the previous run.")
    elif trend == "DECLINING":
        what_changed.append("Overall momentum declined compared with the previous run.")
    elif trend == "STABLE":
        what_changed.append(
            "Performance remained stable compared with the previous run."
        )
    else:
        what_changed.append("This is the baseline run for future comparisons.")

    for entry in list(comparison.get("notable_changes") or []):
        what_changed.append(str(entry))

    what_is_working: list[str] = []
    reply_rate_est = _safe_float(
        run_health.get("reply_rate_estimate") or run_health.get("reply_rate")
    )
    if sent > 0 and reply_rate_est >= 0.02:
        what_is_working.append("Reply performance is in a healthy range.")
    if qualified > 0:
        what_is_working.append("The campaign is producing qualified conversations.")
    if trend in {"IMPROVING", "STABLE"}:
        what_is_working.append("Run-to-run consistency is holding.")

    what_is_broken: list[str] = []
    for entry in list(comparison.get("breakpoints") or []):
        token = str(entry)
        if token == "reply_rate_drop":
            what_is_broken.append("Reply rate dropped versus the previous run.")
        elif token == "qualification_rate_drop":
            what_is_broken.append("Qualification rate dropped versus the previous run.")
        elif token == "signal_degradation":
            what_is_broken.append("Risk signals became more severe in this run.")
        elif token == "volume_drop":
            what_is_broken.append(
                "Send volume dropped materially from the previous run."
            )
        else:
            what_is_broken.append(f"Detected breakpoint: {token}.")

    health_label = str(health.get("label") or "BASELINE").upper()
    if health_label in {"CRITICAL", "LOW"}:
        what_is_broken.append("Overall campaign health is below target.")

    recommended_actions: list[str] = []
    if "Reply rate dropped versus the previous run." in what_is_broken:
        recommended_actions.append(
            "Refresh message angles for the current audience segment."
        )
    if "Qualification rate dropped versus the previous run." in what_is_broken:
        recommended_actions.append(
            "Tighten audience criteria before the next send window."
        )
    if "Risk signals became more severe in this run." in what_is_broken:
        recommended_actions.append(
            "Address highest-severity risks before increasing volume."
        )
    if sent == 0:
        recommended_actions.append(
            "Confirm readiness and approvals before the next run."
        )
    if not recommended_actions:
        recommended_actions.append(
            "Maintain current setup and continue weekly monitoring."
        )

    return {
        "performance_overview": overview,
        "what_changed": what_changed,
        "what_is_working": what_is_working,
        "what_is_broken": what_is_broken,
        "recommended_actions": recommended_actions,
    }
