"""Winning pattern memory tracker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from client_runtime.file_io import atomic_write_json

from .pattern_ranker import score_pattern
from .performance_memory import load_latest_pattern_memory

_PATTERN_KEYS: tuple[str, ...] = (
    "subject_lines",
    "cta_patterns",
    "personas",
    "industries",
    "response_categories",
)


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _ensure_scoreboard(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    scoreboard = payload.get("scoreboard")
    if not isinstance(scoreboard, dict):
        scoreboard = {}
    for key in _PATTERN_KEYS:
        bucket = scoreboard.get(key)
        scoreboard[key] = bucket if isinstance(bucket, dict) else {}
    return scoreboard


def _record_pattern(
    bucket: dict[str, Any],
    *,
    pattern: str,
    sent: int,
    replies: int,
    qualified: int,
) -> None:
    token = str(pattern or "").strip()
    if not token:
        return
    current = bucket.get(token)
    if not isinstance(current, dict):
        current = {"appearances": 0, "sent": 0, "replies": 0, "qualified": 0}
    current["appearances"] = _safe_int(current.get("appearances")) + 1
    current["sent"] = _safe_int(current.get("sent")) + max(0, int(sent))
    current["replies"] = _safe_int(current.get("replies")) + max(0, int(replies))
    current["qualified"] = _safe_int(current.get("qualified")) + max(0, int(qualified))
    current["score"] = score_pattern(
        sent=_safe_int(current.get("sent")),
        replies=_safe_int(current.get("replies")),
        qualified=_safe_int(current.get("qualified")),
        appearances=_safe_int(current.get("appearances")),
    )
    bucket[token] = current


def _rank_bucket(bucket: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, metrics in bucket.items():
        if not isinstance(metrics, dict):
            continue
        rows.append({"pattern": key, **metrics})
    return sorted(
        rows, key=lambda row: (-float(row.get("score") or 0.0), row["pattern"])
    )


def update_pattern_memory(
    *,
    repo_root: Path,
    run_dir: Path,
    client_id: str,
    run_id: str,
    intake_context: dict[str, Any],
    subject_line: str,
    cta_pattern: str,
    run_report: dict[str, Any],
    reply_summary: dict[str, Any],
) -> dict[str, Any]:
    base = load_latest_pattern_memory(
        repo_root=repo_root,
        client_id=client_id,
        current_run_id=run_id,
    )
    if not isinstance(base, dict):
        base = {}

    scoreboard = _ensure_scoreboard(base)
    outbound = run_report.get("outbound") if isinstance(run_report, dict) else {}
    outbound = outbound if isinstance(outbound, dict) else {}
    telemetry = outbound.get("pipeline_telemetry") if isinstance(outbound, dict) else {}
    telemetry = telemetry if isinstance(telemetry, dict) else {}
    health = telemetry.get("run_health") if isinstance(telemetry, dict) else {}
    health = health if isinstance(health, dict) else {}

    sent = _safe_int(health.get("sent"))
    replies = _safe_int(health.get("replies"))
    qualified = _safe_int(health.get("qualified"))

    execution_intent = (
        intake_context.get("execution_intent")
        if isinstance(intake_context, dict)
        else {}
    )
    execution_intent = execution_intent if isinstance(execution_intent, dict) else {}
    persona = str(
        execution_intent.get("persona") or execution_intent.get("icp") or "unknown"
    )
    industry = str(
        execution_intent.get("industry") or execution_intent.get("icp") or "unknown"
    )

    reply_categories = (
        reply_summary.get("classification_counts")
        if isinstance(reply_summary, dict)
        else {}
    )
    reply_categories = reply_categories if isinstance(reply_categories, dict) else {}
    top_category = "neutral"
    if reply_categories:
        top_category = sorted(
            reply_categories.items(),
            key=lambda item: (-_safe_int(item[1]), str(item[0])),
        )[0][0]

    _record_pattern(
        scoreboard["subject_lines"],
        pattern=subject_line,
        sent=sent,
        replies=replies,
        qualified=qualified,
    )
    _record_pattern(
        scoreboard["cta_patterns"],
        pattern=cta_pattern,
        sent=sent,
        replies=replies,
        qualified=qualified,
    )
    _record_pattern(
        scoreboard["personas"],
        pattern=persona,
        sent=sent,
        replies=replies,
        qualified=qualified,
    )
    _record_pattern(
        scoreboard["industries"],
        pattern=industry,
        sent=sent,
        replies=replies,
        qualified=qualified,
    )
    _record_pattern(
        scoreboard["response_categories"],
        pattern=top_category,
        sent=sent,
        replies=replies,
        qualified=qualified,
    )

    payload = {
        "client_id": client_id,
        "run_id": run_id,
        "scoreboard": scoreboard,
        "best_subject_lines": _rank_bucket(scoreboard["subject_lines"])[:5],
        "best_cta_patterns": _rank_bucket(scoreboard["cta_patterns"])[:5],
        "best_performing_personas": _rank_bucket(scoreboard["personas"])[:5],
        "best_industries": _rank_bucket(scoreboard["industries"])[:5],
        "best_response_categories": _rank_bucket(scoreboard["response_categories"])[:5],
    }

    path = atomic_write_json(run_dir / "pattern_memory.json", payload)

    return {
        "pattern_memory": payload,
        "paths": {"pattern_memory": str(path)},
    }
