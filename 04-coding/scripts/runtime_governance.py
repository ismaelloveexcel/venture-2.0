"""Deterministic runtime governance model for outbound execution dashboards."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_report_schema import RunReport

RUNTIME_STATES = {
    "HEALTHY",
    "DEGRADED",
    "UNSTABLE",
    "MISLEADING",
    "BLOCKED",
    "STALE",
    "LOW_CONFIDENCE",
    "DANGEROUS",
}


@dataclass(frozen=True)
class ModuleDefinition:
    module_id: str
    name: str
    depends_on: tuple[str, ...]
    soft_dependencies: tuple[str, ...]
    scoring_category: str


MODULE_GRAPH: tuple[ModuleDefinition, ...] = (
    ModuleDefinition("stage_1_prospecting", "Prospecting", (), (), "data_quality"),
    ModuleDefinition(
        "stage_2_enrichment",
        "Enrichment",
        ("stage_1_prospecting",),
        (),
        "data_quality",
    ),
    ModuleDefinition(
        "stage_3_scoring",
        "Scoring",
        ("stage_2_enrichment",),
        (),
        "execution_health",
    ),
    ModuleDefinition(
        "stage_4_message_generation",
        "Message Generation",
        ("stage_3_scoring",),
        (),
        "messaging_health",
    ),
    ModuleDefinition(
        "stage_5_delivery",
        "Delivery",
        ("stage_4_message_generation",),
        (),
        "infrastructure_health",
    ),
    ModuleDefinition(
        "stage_6_tracking",
        "Tracking",
        ("stage_5_delivery",),
        ("stage_2_enrichment",),
        "execution_health",
    ),
    ModuleDefinition(
        "stage_7_optimization",
        "Optimization",
        ("stage_6_tracking",),
        ("stage_3_scoring",),
        "execution_health",
    ),
)


def _safe_ratio(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return max(0.0, min(1.0, num / den))


def _clamp_0_100(value: float) -> int:
    return int(max(0, min(100, round(value))))


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_recent_history(
    repo_root: Path, client_id: str | None, limit: int = 30
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if client_id:
        runs_dir = repo_root / "clients" / client_id / "runs"
        if runs_dir.is_dir():
            run_files = sorted(runs_dir.glob("*/run_report.json"))[-limit:]
            for run_file in run_files:
                try:
                    rows.append(json.loads(run_file.read_text(encoding="utf-8")))
                except (OSError, json.JSONDecodeError):
                    continue
    else:
        root_report = repo_root / "run_report.json"
        if root_report.is_file():
            try:
                rows.append(json.loads(root_report.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                pass
    return rows


def _telemetry_from_report(report: RunReport) -> dict[str, Any]:
    telemetry = report.outbound.pipeline_telemetry.model_dump(
        mode="json", exclude_none=True
    )
    run_health = telemetry.get("run_health") or {}
    funnel = telemetry.get("funnel_counts_7d") or {}
    summary = telemetry.get("job_queue_summary") or {}

    sent = int(run_health.get("sent") or 0)
    blocked = int(run_health.get("blocked") or 0)
    qualified = int(run_health.get("qualified") or 0)
    generated = int(run_health.get("generated") or 0)
    replied = int(funnel.get("replied") or 0)
    loaded = int(funnel.get("prospect_loaded") or 0)
    msg_generated = int(funnel.get("message_generated") or 0)
    failed_jobs = int(summary.get("failed") or 0)

    return {
        "sent": sent,
        "blocked": blocked,
        "qualified": qualified,
        "generated": generated,
        "replied": replied,
        "loaded": loaded,
        "msg_generated": msg_generated,
        "failed_jobs": failed_jobs,
    }


def _build_descendants() -> dict[str, set[str]]:
    descendants: dict[str, set[str]] = {m.module_id: set() for m in MODULE_GRAPH}
    for module in MODULE_GRAPH:
        for dep in (*module.depends_on, *module.soft_dependencies):
            descendants[dep].add(module.module_id)

    changed = True
    while changed:
        changed = False
        for node, children in list(descendants.items()):
            expanded = set(children)
            for child in list(children):
                expanded |= descendants.get(child, set())
            if expanded != children:
                descendants[node] = expanded
                changed = True
    return descendants


def _execution_state(report: RunReport) -> str:
    status = report.outbound.status
    if status == "SUCCESS":
        return "COMPLETED"
    if status == "BLOCKED":
        return "BLOCKED"
    if status == "FAILED":
        return "FAILED"
    if status == "SKIPPED":
        return "SKIPPED"
    return "RUNNING"


def _module_dimension_scores(
    module_id: str, t: dict[str, Any]
) -> tuple[int | None, int, int, str]:
    if module_id == "stage_1_prospecting":
        if t["loaded"] <= 0:
            return None, 22, 40, "insufficient_data"
        usefulness = _clamp_0_100(100 * _safe_ratio(t["qualified"], t["loaded"]))
        confidence = 72 if t["loaded"] >= 25 else 48
        stability = _clamp_0_100(100 - min(45, t["failed_jobs"] * 4))
        return usefulness, confidence, stability, "evidence_based"

    if module_id == "stage_2_enrichment":
        if t["loaded"] <= 0:
            return None, 20, 35, "insufficient_data"
        completeness = _safe_ratio(t["qualified"], t["loaded"])
        usefulness = _clamp_0_100(100 * completeness)
        confidence = 64 if t["qualified"] >= 10 else 42
        stability = _clamp_0_100(90 - min(50, t["failed_jobs"] * 5))
        return usefulness, confidence, stability, "partial_evidence"

    if module_id == "stage_3_scoring":
        if t["qualified"] <= 0:
            return None, 18, 34, "insufficient_data"
        consistency = _safe_ratio(t["replied"], max(1, t["qualified"]))
        usefulness = _clamp_0_100(100 * consistency)
        confidence = 60 if t["replied"] >= 5 else 36
        stability = _clamp_0_100(88 - min(54, t["failed_jobs"] * 6))
        return usefulness, confidence, stability, "partial_evidence"

    if module_id == "stage_4_message_generation":
        if t["qualified"] <= 0:
            return None, 20, 38, "insufficient_data"
        personalization = _safe_ratio(t["msg_generated"], max(1, t["qualified"]))
        usefulness = _clamp_0_100(100 * personalization)
        confidence = 62 if t["msg_generated"] >= 20 else 40
        stability = _clamp_0_100(85 - min(48, t["failed_jobs"] * 6))
        return usefulness, confidence, stability, "partial_evidence"

    if module_id == "stage_5_delivery":
        if t["msg_generated"] <= 0:
            return None, 20, 36, "insufficient_data"
        placement = _safe_ratio(t["sent"], max(1, t["msg_generated"]))
        usefulness = _clamp_0_100(100 * placement)
        confidence = 74 if t["sent"] >= 20 else 50
        stability = _clamp_0_100(92 - min(60, t["blocked"] * 4))
        return usefulness, confidence, stability, "evidence_based"

    if module_id == "stage_6_tracking":
        if t["sent"] <= 0:
            return None, 20, 40, "insufficient_data"
        telemetry_integrity = _safe_ratio(t["replied"], max(1, t["sent"]))
        usefulness = _clamp_0_100(100 * telemetry_integrity)
        confidence = 66 if t["sent"] >= 20 else 44
        stability = _clamp_0_100(90 - min(40, t["failed_jobs"] * 5))
        return usefulness, confidence, stability, "evidence_based"

    if module_id == "stage_7_optimization":
        if t["sent"] <= 0:
            return None, 20, 30, "insufficient_data"
        validity = _safe_ratio(t["replied"], max(1, t["sent"]))
        usefulness = _clamp_0_100(100 * validity)
        confidence = 58 if t["replied"] >= 3 else 34
        stability = _clamp_0_100(80 - min(50, t["failed_jobs"] * 6))
        return usefulness, confidence, stability, "derived_evidence"

    return None, 20, 30, "insufficient_data"


def _module_baselines(history: list[dict[str, Any]]) -> dict[str, list[int]]:
    baselines: dict[str, list[int]] = {}
    for item in history:
        modules = (
            item.get("outbound", {})
            .get("runtime_governance", {})
            .get("module_governance_grid", [])
        )
        if not isinstance(modules, list):
            continue
        for row in modules:
            if not isinstance(row, dict):
                continue
            module_id = str(row.get("id") or "").strip()
            usefulness = row.get("usefulness_score")
            if module_id and isinstance(usefulness, (int, float)):
                baselines.setdefault(module_id, []).append(int(usefulness))
    return baselines


def _last_known_good_run(history: list[dict[str, Any]], module_id: str) -> str:
    for item in reversed(history):
        run_id = str(item.get("run_id") or "").strip()
        modules = (
            item.get("outbound", {})
            .get("runtime_governance", {})
            .get("module_governance_grid", [])
        )
        if not isinstance(modules, list):
            continue
        row = next(
            (m for m in modules if isinstance(m, dict) and m.get("id") == module_id),
            None,
        )
        if not row:
            continue
        state = str(row.get("runtime_state") or row.get("resolved_state") or "").upper()
        usefulness = row.get("usefulness_score")
        confidence = row.get("confidence_score") or row.get("confidence")
        if (
            state == "HEALTHY"
            and isinstance(usefulness, (int, float))
            and usefulness >= 70
            and isinstance(confidence, (int, float))
            and confidence >= 60
        ):
            return run_id
    return ""


def _state_from_scores(
    *,
    execution_state: str,
    usefulness: int | None,
    confidence: int,
    stability: int,
    trust: int,
    evidence_quality: str,
    contradiction: bool,
    age_min: int | None,
) -> str:
    if execution_state in {"FAILED", "BLOCKED"}:
        return "BLOCKED"
    if age_min is not None and age_min > 360:
        return "STALE"
    if usefulness is None or evidence_quality == "insufficient_data":
        return "LOW_CONFIDENCE"
    if contradiction:
        return "DANGEROUS" if confidence < 55 else "MISLEADING"
    if trust < 35:
        return "DANGEROUS"
    if confidence < 45:
        return "LOW_CONFIDENCE"
    if stability < 45:
        return "UNSTABLE"
    if usefulness < 45 or trust < 55:
        return "DEGRADED"
    return "HEALTHY"


def _build_invariants(t: dict[str, Any]) -> list[dict[str, Any]]:
    checks = [
        ("replied_leq_sent", t["replied"] <= t["sent"], "replied <= sent"),
        (
            "sent_leq_generated_messages",
            t["sent"] <= max(t["msg_generated"], t["sent"]),
            "sent <= generated messages",
        ),
        (
            "qualified_leq_loaded",
            t["qualified"] <= max(t["loaded"], t["qualified"]),
            "qualified <= loaded",
        ),
    ]
    out: list[dict[str, Any]] = []
    for code, ok, detail in checks:
        out.append(
            {
                "code": code,
                "ok": bool(ok),
                "severity": "critical" if not ok else "none",
                "detail": detail,
            }
        )
    return out


def _previous_module_snapshot(
    history: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    for item in reversed(history):
        modules = (
            item.get("outbound", {})
            .get("runtime_governance", {})
            .get("module_governance_grid", [])
        )
        if isinstance(modules, list) and modules:
            by_id = {}
            for row in modules:
                if isinstance(row, dict) and row.get("id"):
                    by_id[str(row["id"])] = row
            if by_id:
                return by_id
    return {}


def build_runtime_governance(
    report: RunReport, *, repo_root: Path, client_id: str | None
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    report_ts = _parse_ts(report.timestamp_utc)
    age_min = int((now - report_ts).total_seconds() // 60) if report_ts else None

    telemetry = _telemetry_from_report(report)
    history = _load_recent_history(repo_root, client_id, limit=30)
    descendants = _build_descendants()
    baselines = _module_baselines(history)
    previous_modules = _previous_module_snapshot(history)

    modules: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}

    execution_state = _execution_state(report)

    for module in MODULE_GRAPH:
        usefulness, confidence, stability, evidence_quality = _module_dimension_scores(
            module.module_id, telemetry
        )
        downstream_impact = _clamp_0_100(
            100
            * _safe_ratio(
                len(descendants[module.module_id]), max(1, len(MODULE_GRAPH) - 1)
            )
        )
        local_trust = _clamp_0_100(
            0.45 * (usefulness if usefulness is not None else 0)
            + 0.3 * confidence
            + 0.25 * stability
        )

        baseline_values = baselines.get(module.module_id, [])
        historical_baseline = (
            int(sum(baseline_values) / len(baseline_values))
            if baseline_values
            else None
        )
        historical_baseline_delta = (
            int((usefulness or 0) - historical_baseline)
            if historical_baseline is not None and usefulness is not None
            else 0
        )

        previous = previous_modules.get(module.module_id, {})
        previous_usefulness = previous.get("usefulness_score")
        previous_trust = previous.get("trust_score")
        usefulness_drop = (
            int(usefulness - previous_usefulness)
            if usefulness is not None and isinstance(previous_usefulness, (int, float))
            else 0
        )
        trust_drop = (
            int(local_trust - previous_trust)
            if isinstance(previous_trust, (int, float))
            else 0
        )

        contradiction = (
            execution_state in {"COMPLETED", "RUNNING"}
            and usefulness is not None
            and usefulness < 45
            and confidence < 55
        )

        runtime_state = _state_from_scores(
            execution_state=execution_state,
            usefulness=usefulness,
            confidence=confidence,
            stability=stability,
            trust=local_trust,
            evidence_quality=evidence_quality,
            contradiction=contradiction,
            age_min=age_min,
        )

        regression_detected = bool(
            usefulness_drop <= -15
            or trust_drop <= -12
            or historical_baseline_delta <= -15
        )

        module_row = {
            "id": module.module_id,
            "name": module.name,
            "runtime_state": runtime_state,
            "resolved_state": runtime_state,
            "execution_state": execution_state,
            "usefulness_score": usefulness,
            "confidence_score": confidence,
            "stability_score": stability,
            "downstream_impact_score": downstream_impact,
            "trust_score": local_trust,
            "evidence_quality": evidence_quality,
            "regression_detected": regression_detected,
            "degraded_by": [],
            "affects": sorted(descendants[module.module_id]),
            "root_cause": "",
            "operator_action_required": runtime_state
            in {"DANGEROUS", "MISLEADING", "UNSTABLE", "BLOCKED"},
            "last_known_good_run": _last_known_good_run(history, module.module_id),
            "historical_baseline_delta": historical_baseline_delta,
            "depends_on": list(module.depends_on),
            "soft_dependencies": list(module.soft_dependencies),
            "causal_chain_depth": len(module.depends_on)
            + len(module.soft_dependencies),
            "upstream_degradation_sources": [],
            "downstream_modules_affected": sorted(descendants[module.module_id]),
            "scoring_category": module.scoring_category,
            "trend_direction": "stable",
            "blast_radius": downstream_impact,
            "runtime_status": runtime_state,
            "confidence": confidence,
            "dependencies": {
                "hard": list(module.depends_on),
                "soft": list(module.soft_dependencies),
            },
            "regression_events": [],
            "trust_decay_multiplier": 1.0,
            "confidence_penalty": 0,
            "derived_trustworthiness": local_trust,
        }
        modules.append(module_row)
        by_id[module.module_id] = module_row

    # Causal trust propagation.
    for module in MODULE_GRAPH:
        row = by_id[module.module_id]
        weighted_deficit = 0.0
        upstream_sources: list[str] = []

        for dep in module.depends_on:
            dep_row = by_id.get(dep)
            if not dep_row:
                continue
            dep_trust = int(dep_row.get("trust_score") or 0)
            deficit = max(0, 100 - dep_trust)
            weighted_deficit += deficit
            dep_state = str(dep_row.get("runtime_state") or "")
            if dep_state in {
                "DEGRADED",
                "UNSTABLE",
                "MISLEADING",
                "DANGEROUS",
                "BLOCKED",
                "LOW_CONFIDENCE",
                "STALE",
            }:
                upstream_sources.append(dep)

        for dep in module.soft_dependencies:
            dep_row = by_id.get(dep)
            if not dep_row:
                continue
            dep_trust = int(dep_row.get("trust_score") or 0)
            deficit = max(0, 100 - dep_trust)
            weighted_deficit += deficit * 0.6
            dep_state = str(dep_row.get("runtime_state") or "")
            if dep_state in {
                "DEGRADED",
                "UNSTABLE",
                "MISLEADING",
                "DANGEROUS",
                "BLOCKED",
                "LOW_CONFIDENCE",
                "STALE",
            }:
                upstream_sources.append(dep)

        confidence_penalty = _clamp_0_100(weighted_deficit * 0.35)
        trust_decay_multiplier = max(0.25, 1.0 - weighted_deficit / 220.0)

        row["confidence_penalty"] = confidence_penalty
        row["trust_decay_multiplier"] = round(trust_decay_multiplier, 4)
        row["confidence_score"] = max(
            0, int(row["confidence_score"]) - confidence_penalty
        )
        row["confidence"] = row["confidence_score"]

        decayed_trust = _clamp_0_100(
            int(row["trust_score"]) * trust_decay_multiplier - confidence_penalty * 0.15
        )
        row["derived_trustworthiness"] = decayed_trust
        row["trust_score"] = decayed_trust

        row["upstream_degradation_sources"] = sorted(set(upstream_sources))
        row["degraded_by"] = sorted(set(upstream_sources))
        if not row["root_cause"] and row["degraded_by"]:
            row["root_cause"] = row["degraded_by"][0]

        contradiction = (
            row["execution_state"] in {"COMPLETED", "RUNNING"}
            and isinstance(row.get("usefulness_score"), int)
            and int(row["usefulness_score"]) < 45
            and int(row["trust_score"]) < 45
        )
        row["runtime_state"] = _state_from_scores(
            execution_state=row["execution_state"],
            usefulness=row["usefulness_score"],
            confidence=int(row["confidence_score"]),
            stability=int(row["stability_score"]),
            trust=int(row["trust_score"]),
            evidence_quality=str(row["evidence_quality"]),
            contradiction=contradiction,
            age_min=age_min,
        )
        row["resolved_state"] = row["runtime_state"]
        row["runtime_status"] = row["runtime_state"]

    # Trend and regression events.
    regressions: list[dict[str, Any]] = []
    for row in modules:
        if row["regression_detected"]:
            row["trend_direction"] = "degrading"
        elif row["runtime_state"] in {
            "UNSTABLE",
            "MISLEADING",
            "LOW_CONFIDENCE",
            "STALE",
        }:
            row["trend_direction"] = "unstable"
        elif row["runtime_state"] in {"DEGRADED", "DANGEROUS", "BLOCKED"}:
            row["trend_direction"] = "degrading"
        else:
            row["trend_direction"] = "improving"

        if row["trend_direction"] in {"degrading", "unstable"}:
            severity = (
                "high"
                if row["runtime_state"] in {"DANGEROUS", "BLOCKED", "MISLEADING"}
                else "medium"
            )
            event = {
                "module": row["id"],
                "previous_usefulness": (
                    previous_modules.get(row["id"], {}).get("usefulness_score")
                    if previous_modules.get(row["id"])
                    else None
                ),
                "current_usefulness": row["usefulness_score"],
                "cause": row["root_cause"] or "internal_regression",
                "severity": severity,
                "blast_radius": row["blast_radius"],
                "timestamp_utc": report.timestamp_utc,
            }
            row["regression_events"].append(event)
            regressions.append(event)

    # Root cause intelligence.
    root_origin = ""
    root_confidence = 0
    if regressions:
        candidate = max(
            regressions,
            key=lambda r: (
                int(r.get("blast_radius") or 0),
                1 if r.get("severity") == "high" else 0,
            ),
        )
        root_origin = str(candidate.get("cause") or candidate.get("module") or "")
        impacted = (
            by_id.get(root_origin, {}).get("downstream_modules_affected")
            if root_origin
            else []
        )
        root_confidence = _clamp_0_100(
            55 + 0.4 * int(candidate.get("blast_radius") or 0)
        )
    else:
        impacted = []

    # Invariants and integrity.
    invariants = _build_invariants(telemetry)
    broken_invariants = [inv for inv in invariants if not inv["ok"]]

    coverage = _safe_ratio(
        sum(1 for m in modules if m["usefulness_score"] is not None), len(modules)
    )
    avg_trust = sum(int(m["trust_score"]) for m in modules) / max(1, len(modules))
    avg_conf = sum(int(m["confidence_score"]) for m in modules) / max(1, len(modules))
    instability = _clamp_0_100(
        sum(
            1
            for m in modules
            if m["runtime_state"] in {"UNSTABLE", "MISLEADING", "DANGEROUS", "DEGRADED"}
        )
        * (100 / max(1, len(modules)))
    )
    freshness_score = (
        100
        if age_min is None
        else _clamp_0_100(max(0, 100 - max(0, age_min - 5) * 0.45))
    )
    integrity_score = 100 if not broken_invariants else 30

    system_trust_score = _clamp_0_100(
        0.34 * avg_trust
        + 0.22 * avg_conf
        + 0.2 * freshness_score
        + 0.14 * (coverage * 100)
        + 0.1 * integrity_score
    )

    prev_system_scores: list[int] = []
    for item in history:
        score = (
            item.get("outbound", {})
            .get("runtime_governance", {})
            .get("system_trust_center", {})
            .get("system_trust_score")
        )
        if isinstance(score, (int, float)):
            prev_system_scores.append(int(score))

    baseline_system = (
        int(sum(prev_system_scores) / len(prev_system_scores))
        if prev_system_scores
        else system_trust_score
    )
    system_delta = int(system_trust_score - baseline_system)

    if system_delta >= 6:
        system_trend = "improving"
    elif system_delta <= -6:
        system_trend = "degrading"
    elif abs(system_delta) >= 3:
        system_trend = "unstable"
    else:
        system_trend = "plateaued"

    active_regressions = [
        r for r in regressions if r.get("severity") in {"high", "medium"}
    ]
    misleading_modules = [
        m["id"] for m in modules if m["runtime_state"] in {"MISLEADING", "DANGEROUS"}
    ]

    safe_to_scale = (
        system_trust_score >= 72
        and not broken_invariants
        and not misleading_modules
        and len(active_regressions) <= 1
    )
    safe_to_change_messaging = all(
        by_id[mid]["runtime_state"] not in {"BLOCKED", "DANGEROUS", "MISLEADING"}
        for mid in ("stage_3_scoring", "stage_4_message_generation", "stage_6_tracking")
    )
    safe_to_change_audience = all(
        by_id[mid]["runtime_state"]
        not in {"BLOCKED", "DANGEROUS", "MISLEADING", "LOW_CONFIDENCE"}
        for mid in ("stage_1_prospecting", "stage_2_enrichment", "stage_3_scoring")
    )
    safe_to_run_ab_test = (
        safe_to_change_messaging
        and system_trust_score >= 62
        and instability <= 35
        and not broken_invariants
    )

    confidence_in_recommendation = _clamp_0_100(
        0.55 * avg_conf + 0.3 * system_trust_score + 0.15 * (100 - instability)
    )

    historical_records = []
    for item in history[-15:]:
        gov = item.get("outbound", {}).get("runtime_governance", {})
        historical_records.append(
            {
                "run_id": item.get("run_id"),
                "timestamp": item.get("timestamp_utc"),
                "system_trust_score": gov.get("system_trust_center", {}).get(
                    "system_trust_score"
                ),
                "module_scores": {
                    str(m.get("id")): {
                        "usefulness_score": m.get("usefulness_score"),
                        "trust_score": m.get("trust_score"),
                        "runtime_state": m.get("runtime_state")
                        or m.get("resolved_state"),
                    }
                    for m in (gov.get("module_governance_grid") or [])
                    if isinstance(m, dict) and m.get("id")
                },
                "regressions": gov.get("regression_center", {}).get(
                    "top_regressions", []
                ),
                "operator_changes": gov.get("historical_intelligence", {}).get(
                    "latest_operator_changes", []
                ),
                "root_cause_events": gov.get("root_cause_intelligence", {}).get(
                    "events", []
                ),
            }
        )

    return {
        "model_version": "2.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "system_trust_center": {
            "system_trust_score": system_trust_score,
            "confidence_score": _clamp_0_100(avg_conf),
            "instability_level": instability,
            "system_trend": system_trend,
            "active_regressions": len(active_regressions),
            "misleading_modules": misleading_modules,
            "blast_radius": max(
                (int(r.get("blast_radius") or 0) for r in active_regressions), default=0
            ),
            "critical_blockers": [
                m["id"]
                for m in modules
                if m["runtime_state"] in {"BLOCKED", "DANGEROUS"}
            ],
        },
        "executive_health": {
            "trust_score": system_trust_score,
            "system_trend": system_trend,
            "revenue_readiness": (
                "ready"
                if system_trust_score >= 72
                else "guarded" if system_trust_score >= 52 else "at_risk"
            ),
            "critical_blockers": [
                m["id"]
                for m in modules
                if m["runtime_state"] in {"BLOCKED", "DANGEROUS"}
            ],
            "major_regressions": [r["module"] for r in active_regressions[:5]],
        },
        "telemetry_integrity": {
            "coverage_score": _clamp_0_100(coverage * 100),
            "freshness_score": freshness_score,
            "integrity_score": integrity_score,
            "age_minutes": age_min,
            "invariants": invariants,
        },
        "module_governance_grid": modules,
        "causal_impact_map": {
            "edges": [
                {
                    "from": module.module_id,
                    "to": dep,
                    "type": "hard",
                }
                for module in MODULE_GRAPH
                for dep in module.depends_on
            ]
            + [
                {
                    "from": module.module_id,
                    "to": dep,
                    "type": "soft",
                }
                for module in MODULE_GRAPH
                for dep in module.soft_dependencies
            ],
            "degradation_paths": [
                {
                    "origin": m["id"],
                    "downstream_modules_affected": m["downstream_modules_affected"],
                    "state": m["runtime_state"],
                }
                for m in modules
                if m["runtime_state"]
                in {"DEGRADED", "UNSTABLE", "MISLEADING", "DANGEROUS", "BLOCKED"}
            ],
        },
        "regression_center": {
            "top_regressions": [
                {
                    "module_id": r.get("module"),
                    "state": by_id.get(str(r.get("module")), {}).get("runtime_state"),
                    "blast_radius": r.get("blast_radius"),
                    "root_cause": r.get("cause"),
                    "confidence": by_id.get(str(r.get("module")), {}).get(
                        "confidence_score"
                    ),
                }
                for r in active_regressions[:7]
            ],
            "system_delta_vs_baseline": system_delta,
        },
        "regression_timeline": {
            "events": sorted(
                active_regressions,
                key=lambda r: int(r.get("blast_radius") or 0),
                reverse=True,
            )[:20],
            "first_regression_timestamp": (
                min((r.get("timestamp_utc") for r in active_regressions), default="")
            ),
        },
        "change_impact_timeline": {
            "points": [
                {
                    "timestamp_utc": rec.get("timestamp"),
                    "trust_score": rec.get("system_trust_score"),
                    "regression_count": len(rec.get("regressions") or []),
                }
                for rec in historical_records[-10:]
            ]
            + [
                {
                    "timestamp_utc": report.timestamp_utc,
                    "trust_score": system_trust_score,
                    "regression_count": len(active_regressions),
                }
            ]
        },
        "root_cause_intelligence": {
            "root_cause": {
                "origin": root_origin,
                "confidence": root_confidence,
                "downstream_affected": impacted,
            },
            "events": [
                {
                    "origin": r.get("cause") or r.get("module"),
                    "module": r.get("module"),
                    "severity": r.get("severity"),
                    "blast_radius": r.get("blast_radius"),
                    "timestamp_utc": r.get("timestamp_utc"),
                }
                for r in active_regressions
            ],
        },
        "decision_safety": {
            "safe_to_scale": safe_to_scale,
            "safe_to_change_messaging": safe_to_change_messaging,
            "safe_to_change_audience": safe_to_change_audience,
            "safe_to_run_ab_test": safe_to_run_ab_test,
            "confidence_in_recommendation": confidence_in_recommendation,
            "unsafe_reasons": [
                "active_regressions" if active_regressions else "",
                "misleading_modules_present" if misleading_modules else "",
                "invariant_violation" if broken_invariants else "",
            ],
            "recommended_next_move": (
                "stabilize_upstream_data"
                if not safe_to_change_audience
                else (
                    "refine_message_quality"
                    if safe_to_change_messaging and not safe_to_scale
                    else "scale_cautiously" if safe_to_scale else "hold_and_investigate"
                )
            ),
        },
        "historical_intelligence": {
            "records": historical_records,
            "degradation_acceleration": _clamp_0_100(
                len([r for r in active_regressions if r.get("severity") == "high"]) * 18
                + max(0, -system_delta) * 2
            ),
            "last_stable_configuration": {
                "run_id": _last_known_good_run(history, "stage_7_optimization")
                or _last_known_good_run(history, "stage_5_delivery")
                or "",
                "trust_score": baseline_system,
            },
            "latest_operator_changes": [],
        },
    }
