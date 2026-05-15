"""Reply intelligence summary writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from client_runtime.file_io import atomic_write_json

from .intent_detector import (
    extract_cta_requests,
    extract_objections,
    extract_positive_intent_phrases,
)
from .reply_classifier import classify_reply

_REPLY_BUCKETS: tuple[str, ...] = (
    "positive",
    "neutral",
    "objection",
    "unsubscribe",
    "meeting_intent",
)


def _summary_path(run_dir: Path) -> Path:
    return run_dir / "reply_summary.json"


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def generate_reply_summary(
    *,
    run_dir: Path,
    run_report: dict[str, Any],
    reply_texts: list[str] | None = None,
) -> dict[str, Any]:
    texts = [str(item or "") for item in (reply_texts or [])]

    outbound = run_report.get("outbound") if isinstance(run_report, dict) else {}
    outbound = outbound if isinstance(outbound, dict) else {}
    telemetry = outbound.get("pipeline_telemetry") if isinstance(outbound, dict) else {}
    telemetry = telemetry if isinstance(telemetry, dict) else {}
    health = telemetry.get("run_health") if isinstance(telemetry, dict) else {}
    health = health if isinstance(health, dict) else {}
    observed_replies = _safe_int(health.get("replies"))

    counts = {bucket: 0 for bucket in _REPLY_BUCKETS}
    objections: list[str] = []
    positive_intents: list[str] = []
    cta_requests: list[str] = []

    for text in texts:
        category = classify_reply(text)
        counts[category] += 1
        objections.extend(extract_objections(text))
        positive_intents.extend(extract_positive_intent_phrases(text))
        cta_requests.extend(extract_cta_requests(text))

    if observed_replies > len(texts):
        counts["neutral"] += observed_replies - len(texts)

    payload = {
        "total_replies": sum(counts.values()),
        "classification_counts": counts,
        "objections": sorted(set(objections)),
        "positive_intent_phrases": sorted(set(positive_intents)),
        "cta_requests": sorted(set(cta_requests)),
    }

    path = _summary_path(run_dir)
    atomic_write_json(path, payload)

    return {
        "reply_summary": payload,
        "paths": {"reply_summary": str(path)},
    }
