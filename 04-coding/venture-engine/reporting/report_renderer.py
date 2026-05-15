from __future__ import annotations

import html
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_report_schema import OutboundSection, RunReport

REPORT_PROJECTION_VERSION = "1.1"
INSIGHT_CALIBRATION_VERSION = "2.0"
INSIGHT_SCORING_MODEL = "deterministic_v1"


@dataclass(frozen=True)
class ReportProjection:
    health_score: int
    health_tier: str
    health_class: str
    sent: int
    blocked: int
    qualified: int
    reply_rate_pct: float
    risk_signal_count: int
    eligibility_failures: int
    suppression_hits: int
    issues: list[str]
    actions: list[str]
    impact_summary: str


@dataclass(frozen=True)
class ReportInsight:
    summary: str
    trend_label: str
    trend_class: str
    severity_label: str
    severity_score: int
    confidence_score: int
    confidence_label: str
    what_changed: list[str]
    what_broke: list[str]
    what_to_do_next: list[str]
    primary_signals: list[dict[str, Any]]
    secondary_signals: list[dict[str, Any]]


@dataclass(frozen=True)
class ProjectionArtifact:
    run_id: str
    projection_version: str
    generated_at_utc: str
    health_score: int
    sent: int
    blocked: int
    qualified: int
    reply_rate_pct: float
    risk_signal_count: int
    eligibility_failures: int
    suppression_hits: int


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


def _severity_label(score: int) -> str:
    if score >= 80:
        return "CRITICAL"
    if score >= 60:
        return "HIGH"
    if score >= 45:
        return "MEDIUM"
    return "LOW"


def _confidence_label(score: int) -> str:
    if score >= 75:
        return "HIGH"
    if score >= 50:
        return "MEDIUM"
    return "LOW"


def _find_risk_signals(outbound: OutboundSection) -> tuple[int, int, int, list[str]]:
    reasons = list(outbound.money_path.reasons or [])
    errors = list(outbound.errors or [])
    all_text = [str(x).lower() for x in reasons + errors]

    suppression_hits = sum(1 for t in all_text if "suppression" in t)
    eligibility_failures = sum(1 for t in all_text if "eligib" in t or "ready" in t)
    risk_signal_count = sum(
        1 for t in all_text if "block" in t or "risk" in t or "suppression" in t
    )

    issues: list[str] = []
    if suppression_hits:
        issues.append("Suppression indicators detected in outbound decision trail.")
    if eligibility_failures:
        issues.append(
            "Eligibility filtering reduced sendable rows; review cohort readiness upstream."
        )
    if outbound.status in {"BLOCKED", "FAILED"}:
        issues.append(
            "Outbound execution ended in non-success state; inspect run-level gates before next batch."
        )
    if not issues:
        issues.append("No critical issues detected in this run projection.")

    return risk_signal_count, eligibility_failures, suppression_hits, issues


def project_outbound_state(report: RunReport) -> ReportProjection:
    outbound = report.outbound
    run_health = {}
    if outbound.pipeline_telemetry and outbound.pipeline_telemetry.run_health:
        run_health = dict(outbound.pipeline_telemetry.run_health)

    sent = _safe_int(run_health.get("sent") if run_health else outbound.money_path.sent)
    blocked = _safe_int(
        run_health.get("blocked") if run_health else outbound.money_path.blocked
    )
    qualified = _safe_int(
        run_health.get("qualified")
        if run_health
        else outbound.prospect_batch.approved_pass_rows
    )
    reply_rate = _safe_float(
        run_health.get("reply_rate_estimate") or run_health.get("reply_rate")
    )

    risk_signal_count, eligibility_failures, suppression_hits, issues = (
        _find_risk_signals(outbound)
    )

    score = 100
    score -= min(blocked * 7, 42)
    score -= min(eligibility_failures * 3, 18)
    score -= min(risk_signal_count * 2, 20)
    if outbound.status in {"BLOCKED", "FAILED"}:
        score -= 15
    if sent == 0 and outbound.status == "SUCCESS":
        score -= 8
    score = max(0, min(100, score))

    if score >= 80:
        tier, css = "LOW RISK", "health-good"
    elif score >= 60:
        tier, css = "MODERATE RISK", "health-warn"
    else:
        tier, css = "HIGH RISK", "health-bad"

    actions: list[str] = []
    if blocked > 0:
        actions.append("Review latest block reasons before increasing batch size.")
    if suppression_hits > 0:
        actions.append("Validate suppression source freshness before next send window.")
    if eligibility_failures > 0:
        actions.append("Tighten upstream READY criteria to reduce execution friction.")
    if sent > 0 and reply_rate < 0.01:
        actions.append(
            "Run copy and ICP review; low reply estimate suggests mismatch risk."
        )
    if not actions:
        actions.append(
            "Hold current controls and continue monitored execution with weekly review."
        )

    est_value_per_block = _safe_float(
        os.environ.get("VENTURE_RISK_VALUE_PER_BLOCK", "85")
    )
    est_avoided = round((blocked + suppression_hits) * est_value_per_block, 2)
    impact_summary = (
        f"This run prevented or intercepted {blocked + suppression_hits} risky send conditions. "
        f"Estimated protected pipeline-risk value: ${est_avoided}."
    )

    return ReportProjection(
        health_score=score,
        health_tier=tier,
        health_class=css,
        sent=sent,
        blocked=blocked,
        qualified=qualified,
        reply_rate_pct=round(reply_rate * 100.0, 2),
        risk_signal_count=risk_signal_count,
        eligibility_failures=eligibility_failures,
        suppression_hits=suppression_hits,
        issues=issues,
        actions=actions,
        impact_summary=impact_summary,
    )


def compute_insight_score(
    insight: dict[str, Any],
    previous_run: ProjectionArtifact | None,
    current_run: ProjectionArtifact,
) -> dict[str, Any]:
    """Compute deterministic severity/confidence/weighted scores for a signal."""
    kind = str(insight.get("kind") or "informational")
    delta = _safe_float(insight.get("delta") or 0.0)
    prior_delta = _safe_float(insight.get("prior_delta") or 0.0)
    degradation_pct = _safe_float(insight.get("degradation_pct") or 0.0)
    is_critical = bool(insight.get("is_critical") or False)
    conflicting_signals = _safe_int(insight.get("conflicting_signals") or 0)
    missing_fields = _safe_int(insight.get("missing_fields") or 0)
    total_fields = max(1, _safe_int(insight.get("total_fields") or 1))

    severity_base = {
        "send_blocking": 85,
        "deliverability_risk": 72,
        "performance_drop": 58,
        "instability": 44,
        "informational": 20,
    }
    severity = severity_base.get(kind, 25)

    if is_critical:
        severity = max(severity, 90)
    if degradation_pct >= 20:
        severity += 12
    if degradation_pct >= 35:
        severity += 10
    if delta < 0:
        severity += 4
    if current_run.blocked > 0 and kind in {"send_blocking", "deliverability_risk"}:
        severity += 8

    sample_size = max(0, current_run.sent + current_run.qualified)
    if sample_size == 0 and not is_critical:
        # Prevent zero-volume campaigns from producing inflated severity.
        severity = min(severity, 25)
    severity_score = max(0, min(100, int(round(severity))))

    confidence = 20
    if sample_size >= 80:
        confidence += 35
    elif sample_size >= 30:
        confidence += 25
    elif sample_size > 0:
        confidence += 12
    else:
        confidence += 5

    if previous_run is not None:
        if prior_delta == 0.0:
            confidence += 8
        elif (delta > 0 and prior_delta > 0) or (delta < 0 and prior_delta < 0):
            confidence += 15
        else:
            confidence += 6

    completeness_ratio = max(
        0.0, min(1.0, (total_fields - missing_fields) / total_fields)
    )
    confidence += int(round(completeness_ratio * 25))
    confidence -= min(conflicting_signals * 10, 25)

    if sample_size == 0 and not is_critical:
        confidence = min(confidence, 45)
    confidence_score = max(0, min(100, int(round(confidence))))

    weighted_score = int(round((severity_score * 0.6) + (confidence_score * 0.4)))

    return {
        "severity_score": severity_score,
        "severity_label": _severity_label(severity_score),
        "confidence_score": confidence_score,
        "confidence_label": _confidence_label(confidence_score),
        "weighted_score": weighted_score,
    }


def _render_list(items: list[str]) -> str:
    if not items:
        return "<p>None.</p>"
    inner = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f"<ul>{inner}</ul>"


def _render_signals(signals: list[dict[str, Any]]) -> str:
    if not signals:
        return "<p>None.</p>"
    rows: list[str] = []
    for signal in signals:
        title = html.escape(str(signal.get("title") or "Signal"))
        detail = html.escape(str(signal.get("detail") or ""))
        sev_label = html.escape(str(signal.get("severity_label") or "LOW"))
        sev_score = _safe_int(signal.get("severity_score"))
        conf_label = html.escape(str(signal.get("confidence_label") or "LOW"))
        conf_score = _safe_int(signal.get("confidence_score"))
        weighted = _safe_int(signal.get("weighted_score"))
        rows.append(
            "<li>"
            f"<strong>{title}</strong>: {detail} "
            f"<span>(Severity: {sev_label} {sev_score} | Confidence: {conf_label} {conf_score} | Score: {weighted})</span>"
            "</li>"
        )
    return f"<ul>{''.join(rows)}</ul>"


def _load_template(repo_root: Path) -> str:
    template_path = (
        repo_root
        / "04-coding"
        / "venture-engine"
        / "reporting"
        / "templates"
        / "weekly_report.html"
    )
    return template_path.read_text(encoding="utf-8")


def _projection_to_artifact(
    report: RunReport,
    projection: ReportProjection,
) -> ProjectionArtifact:
    return ProjectionArtifact(
        run_id=report.run_id,
        projection_version=REPORT_PROJECTION_VERSION,
        generated_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        health_score=projection.health_score,
        sent=projection.sent,
        blocked=projection.blocked,
        qualified=projection.qualified,
        reply_rate_pct=projection.reply_rate_pct,
        risk_signal_count=projection.risk_signal_count,
        eligibility_failures=projection.eligibility_failures,
        suppression_hits=projection.suppression_hits,
    )


def _artifact_to_dict(artifact: ProjectionArtifact) -> dict[str, Any]:
    return {
        "run_id": artifact.run_id,
        "projection_version": artifact.projection_version,
        "generated_at_utc": artifact.generated_at_utc,
        "health_score": artifact.health_score,
        "sent": artifact.sent,
        "blocked": artifact.blocked,
        "qualified": artifact.qualified,
        "reply_rate_pct": artifact.reply_rate_pct,
        "risk_signal_count": artifact.risk_signal_count,
        "eligibility_failures": artifact.eligibility_failures,
        "suppression_hits": artifact.suppression_hits,
    }


def _dict_to_artifact(data: dict[str, Any]) -> ProjectionArtifact | None:
    try:
        return ProjectionArtifact(
            run_id=str(data.get("run_id") or ""),
            projection_version=str(data.get("projection_version") or "1.0"),
            generated_at_utc=str(data.get("generated_at_utc") or ""),
            health_score=_safe_int(data.get("health_score")),
            sent=_safe_int(data.get("sent")),
            blocked=_safe_int(data.get("blocked")),
            qualified=_safe_int(data.get("qualified")),
            reply_rate_pct=_safe_float(data.get("reply_rate_pct")),
            risk_signal_count=_safe_int(data.get("risk_signal_count")),
            eligibility_failures=_safe_int(data.get("eligibility_failures")),
            suppression_hits=_safe_int(data.get("suppression_hits")),
        )
    except Exception:
        return None


def _load_previous_projection(
    output_dir: Path,
    *,
    current_run_id: str,
) -> ProjectionArtifact | None:
    files = sorted(
        output_dir.glob("campaign-report-*.projection.json"),
        key=lambda p: p.stat().st_mtime,
    )
    for path in reversed(files):
        if current_run_id in path.name:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        artifact = _dict_to_artifact(payload if isinstance(payload, dict) else {})
        if artifact is not None:
            return artifact
    return None


def build_report_insight(
    projection: ReportProjection,
    current: ProjectionArtifact,
    previous: ProjectionArtifact | None,
) -> ReportInsight:
    missing_fields = int(current.sent == 0) + int(current.qualified == 0)
    total_fields = 6

    if previous is None:
        baseline_signal = {
            "title": "Baseline initialized",
            "detail": "No prior projection artifact exists for comparison.",
            "kind": "informational",
            "delta": 0,
            "prior_delta": 0,
            "degradation_pct": 0,
            "is_critical": False,
            "conflicting_signals": 0,
            "missing_fields": missing_fields,
            "total_fields": total_fields,
        }
        baseline_signal.update(compute_insight_score(baseline_signal, None, current))
        return ReportInsight(
            summary="Baseline report established. Next run will include week-over-week movement.",
            trend_label="BASELINE",
            trend_class="health-warn",
            severity_label=str(baseline_signal["severity_label"]),
            severity_score=_safe_int(baseline_signal["severity_score"]),
            confidence_score=_safe_int(baseline_signal["confidence_score"]),
            confidence_label=str(baseline_signal["confidence_label"]),
            what_changed=["No prior projection artifact exists for comparison."],
            what_broke=["No newly detected break conditions in baseline mode."],
            what_to_do_next=list(projection.actions),
            primary_signals=[baseline_signal],
            secondary_signals=[],
        )

    health_delta = current.health_score - previous.health_score
    sent_delta = current.sent - previous.sent
    blocked_delta = current.blocked - previous.blocked
    rr_delta = round(current.reply_rate_pct - previous.reply_rate_pct, 2)
    suppression_delta = current.suppression_hits - previous.suppression_hits
    eligibility_delta = current.eligibility_failures - previous.eligibility_failures

    send_drop_pct = 0.0
    if previous.sent > 0:
        send_drop_pct = ((previous.sent - current.sent) / previous.sent) * 100.0
    reply_drop_pct = 0.0
    if previous.reply_rate_pct > 0:
        reply_drop_pct = (
            (previous.reply_rate_pct - current.reply_rate_pct) / previous.reply_rate_pct
        ) * 100.0

    changed: list[str] = [
        f"Health score moved by {health_delta:+d} points ({previous.health_score} -> {current.health_score}).",
        f"Sent volume moved by {sent_delta:+d} ({previous.sent} -> {current.sent}).",
        f"Blocked events moved by {blocked_delta:+d} ({previous.blocked} -> {current.blocked}).",
        f"Reply rate estimate moved by {rr_delta:+.2f}pp ({previous.reply_rate_pct:.2f}% -> {current.reply_rate_pct:.2f}%).",
    ]

    conflict_count = 0
    if health_delta > 0 and blocked_delta > 0:
        conflict_count += 1
    if rr_delta > 0 and current.risk_signal_count > previous.risk_signal_count:
        conflict_count += 1

    candidate_signals: list[dict[str, Any]] = [
        {
            "title": "Send blocking pressure",
            "detail": f"Blocked events delta {blocked_delta:+d}.",
            "kind": "send_blocking",
            "delta": blocked_delta,
            "prior_delta": previous.blocked,
            "degradation_pct": 0.0,
            "is_critical": blocked_delta > 0 or current.blocked > 0,
            "conflicting_signals": conflict_count,
            "missing_fields": missing_fields,
            "total_fields": total_fields,
        },
        {
            "title": "Deliverability suppression pressure",
            "detail": f"Suppression indicator delta {suppression_delta:+d}.",
            "kind": "deliverability_risk",
            "delta": suppression_delta,
            "prior_delta": previous.suppression_hits,
            "degradation_pct": 0.0,
            "is_critical": suppression_delta > 0,
            "conflicting_signals": conflict_count,
            "missing_fields": missing_fields,
            "total_fields": total_fields,
        },
        {
            "title": "Health degradation",
            "detail": f"Health score delta {health_delta:+d}.",
            "kind": "performance_drop" if health_delta < 0 else "informational",
            "delta": health_delta,
            "prior_delta": previous.health_score,
            "degradation_pct": max(0.0, float(-health_delta)),
            "is_critical": health_delta <= -20,
            "conflicting_signals": conflict_count,
            "missing_fields": missing_fields,
            "total_fields": total_fields,
        },
        {
            "title": "Reply-rate movement",
            "detail": f"Reply-rate estimate delta {rr_delta:+.2f}pp.",
            "kind": "performance_drop" if rr_delta < 0 else "informational",
            "delta": rr_delta,
            "prior_delta": previous.reply_rate_pct,
            "degradation_pct": max(0.0, reply_drop_pct),
            "is_critical": reply_drop_pct >= 20,
            "conflicting_signals": conflict_count,
            "missing_fields": missing_fields,
            "total_fields": total_fields,
        },
        {
            "title": "Send-volume stability",
            "detail": f"Send-volume change {send_drop_pct:+.1f}%.",
            "kind": "instability" if send_drop_pct >= 20 else "informational",
            "delta": -send_drop_pct,
            "prior_delta": previous.sent,
            "degradation_pct": max(0.0, send_drop_pct),
            "is_critical": send_drop_pct >= 35,
            "conflicting_signals": conflict_count,
            "missing_fields": missing_fields,
            "total_fields": total_fields,
        },
        {
            "title": "Eligibility friction",
            "detail": f"Eligibility-failure delta {eligibility_delta:+d}.",
            "kind": "instability" if eligibility_delta > 0 else "informational",
            "delta": eligibility_delta,
            "prior_delta": previous.eligibility_failures,
            "degradation_pct": max(0.0, float(eligibility_delta * 10)),
            "is_critical": eligibility_delta >= 2,
            "conflicting_signals": conflict_count,
            "missing_fields": missing_fields,
            "total_fields": total_fields,
        },
    ]

    scored_signals: list[dict[str, Any]] = []
    for signal in candidate_signals:
        signal.update(compute_insight_score(signal, previous, current))
        scored_signals.append(signal)

    scored_signals.sort(
        key=lambda s: (
            _safe_int(s.get("severity_score")),
            _safe_int(s.get("confidence_score")),
            _safe_int(s.get("weighted_score")),
        ),
        reverse=True,
    )
    primary_signals = scored_signals[:3]
    secondary_signals = scored_signals[3:]

    top_severity = _safe_int(
        primary_signals[0].get("severity_score") if primary_signals else 0
    )
    severity_label = _severity_label(top_severity)

    if primary_signals:
        avg_confidence = int(
            round(
                sum(_safe_int(s.get("confidence_score")) for s in primary_signals)
                / len(primary_signals)
            )
        )
    else:
        avg_confidence = 0
    confidence_label = _confidence_label(avg_confidence)

    broke: list[str] = []
    if blocked_delta > 0:
        broke.append("Block volume increased versus the previous run.")
    if eligibility_delta > 0:
        broke.append("Eligibility failures increased in the current run.")
    if suppression_delta > 0:
        broke.append(
            "Suppression indicators increased and require data freshness checks."
        )
    if health_delta < 0 and not broke:
        broke.append(
            "Overall health declined without a single dominant failure signal."
        )
    if not broke:
        broke.append("No material new break pattern detected versus the prior run.")

    next_actions = list(projection.actions)
    if blocked_delta > 0:
        next_actions.insert(0, "Run gate-level review before widening campaign volume.")
    if rr_delta < 0:
        next_actions.append(
            "Review targeting and copy fit for cohorts with declining estimated replies."
        )

    if health_delta >= 5 and blocked_delta <= 0:
        trend_label, trend_class = "IMPROVING", "health-good"
    elif health_delta <= -5 or blocked_delta > 0:
        trend_label, trend_class = "DETERIORATING", "health-bad"
    else:
        trend_label, trend_class = "STABLE", "health-warn"

    summary = (
        f"Trend is {trend_label.lower()} with health delta {health_delta:+d} and blocked-event delta {blocked_delta:+d}. "
        f"Severity={severity_label} ({top_severity}) with {confidence_label.lower()} confidence ({avg_confidence})."
    )

    return ReportInsight(
        summary=summary,
        trend_label=trend_label,
        trend_class=trend_class,
        severity_label=severity_label,
        severity_score=top_severity,
        confidence_score=avg_confidence,
        confidence_label=confidence_label,
        what_changed=changed,
        what_broke=broke,
        what_to_do_next=next_actions,
        primary_signals=primary_signals,
        secondary_signals=secondary_signals,
    )


def render_campaign_report_html(
    report: RunReport,
    *,
    repo_root: Path,
    insight: ReportInsight,
    projection: ReportProjection,
) -> str:
    tpl = _load_template(repo_root)
    replacements = {
        "run_id": html.escape(report.run_id),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "health_score": str(projection.health_score),
        "health_tier": html.escape(projection.health_tier),
        "health_class": projection.health_class,
        "outbound_status": html.escape(report.outbound.status),
        "money_path_source": html.escape(report.outbound.money_path_source),
        "sent": str(projection.sent),
        "blocked": str(projection.blocked),
        "qualified": str(projection.qualified),
        "reply_rate": f"{projection.reply_rate_pct:.2f}",
        "risk_signal_count": str(projection.risk_signal_count),
        "eligibility_failures": str(projection.eligibility_failures),
        "suppression_hits": str(projection.suppression_hits),
        "issues_html": _render_list(projection.issues),
        "actions_html": _render_list(projection.actions),
        "impact_summary": html.escape(projection.impact_summary),
        "insight_summary": html.escape(insight.summary),
        "trend_label": html.escape(insight.trend_label),
        "trend_class": insight.trend_class,
        "severity_label": html.escape(insight.severity_label),
        "severity_score": str(insight.severity_score),
        "confidence_score": str(insight.confidence_score),
        "confidence_label": html.escape(insight.confidence_label),
        "what_changed_html": _render_list(insight.what_changed),
        "what_broke_html": _render_list(insight.what_broke),
        "what_next_html": _render_list(insight.what_to_do_next),
        "primary_signals_html": _render_signals(insight.primary_signals),
        "secondary_signals_html": _render_signals(insight.secondary_signals),
        "projection_version": REPORT_PROJECTION_VERSION,
        "insight_calibration_version": INSIGHT_CALIBRATION_VERSION,
    }
    rendered = tpl
    for key, value in replacements.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def _render_pdf_if_available(html_path: Path) -> Path | None:
    try:
        from weasyprint import HTML  # type: ignore
    except Exception:
        return None

    pdf_path = html_path.with_suffix(".pdf")
    try:
        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
    except Exception:
        return None
    return pdf_path


def _validate_artifact_integrity(
    *,
    manifest_path: Path,
    projection_path: Path,
) -> None:
    if not manifest_path.is_file() or not projection_path.is_file():
        raise RuntimeError(
            "Artifact integrity violation: run_id mismatch or missing fields"
        )
    try:
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        projection_payload = json.loads(projection_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "Artifact integrity violation: run_id mismatch or missing fields"
        ) from exc
    if not isinstance(manifest_payload, dict) or not isinstance(
        projection_payload, dict
    ):
        raise RuntimeError(
            "Artifact integrity violation: run_id mismatch or missing fields"
        )
    if not manifest_payload.get("run_id") or not projection_payload.get("run_id"):
        raise RuntimeError(
            "Artifact integrity violation: run_id mismatch or missing fields"
        )
    assert manifest_payload["run_id"] == projection_payload["run_id"]


def build_campaign_report_artifacts(
    report: RunReport,
    *,
    repo_root: Path,
    output_dir: Path,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    projection = project_outbound_state(report)
    current_artifact = _projection_to_artifact(report, projection)
    previous_artifact = _load_previous_projection(
        output_dir, current_run_id=report.run_id
    )
    insight = build_report_insight(projection, current_artifact, previous_artifact)

    projection_path = output_dir / f"campaign-report-{report.run_id}.projection.json"
    projection_payload = _artifact_to_dict(current_artifact)
    if not projection_payload.get("run_id") or not report.run_id:
        raise RuntimeError(
            "Artifact integrity violation: run_id mismatch or missing fields"
        )
    if projection_payload["run_id"] != report.run_id:
        raise RuntimeError(
            "Artifact integrity violation: run_id mismatch or missing fields"
        )
    projection_payload["insight_metadata"] = {
        "calibration_version": INSIGHT_CALIBRATION_VERSION,
        "scoring_model": INSIGHT_SCORING_MODEL,
    }
    projection_path.write_text(
        json.dumps(projection_payload, indent=2),
        encoding="utf-8",
    )

    html_path = output_dir / f"campaign-report-{report.run_id}.html"
    html_path.write_text(
        render_campaign_report_html(
            report,
            repo_root=repo_root,
            insight=insight,
            projection=projection,
        ),
        encoding="utf-8",
    )

    artifacts: dict[str, str] = {
        "run_id": report.run_id,
        "html": str(html_path),
        "projection": str(projection_path),
        "projection_version": REPORT_PROJECTION_VERSION,
        "insight_calibration_version": INSIGHT_CALIBRATION_VERSION,
        "insight_scoring_model": INSIGHT_SCORING_MODEL,
    }
    pdf_path = _render_pdf_if_available(html_path)
    if pdf_path is not None:
        artifacts["pdf"] = str(pdf_path)

    manifest_path = output_dir / f"campaign-report-{report.run_id}.json"
    manifest_path.write_text(json.dumps(artifacts, indent=2), encoding="utf-8")
    _validate_artifact_integrity(
        manifest_path=manifest_path,
        projection_path=projection_path,
    )
    artifacts["manifest"] = str(manifest_path)
    return artifacts
