"""Deterministic timeline builder for client run history."""

from __future__ import annotations

from typing import Any


def build_timeline(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        records,
        key=lambda item: (
            str(item.get("timestamp_utc") or ""),
            str(item.get("run_id") or ""),
        ),
    )
    timeline: list[dict[str, Any]] = []
    for record in ordered:
        timeline.append(
            {
                "run_id": str(record.get("run_id") or ""),
                "timestamp_utc": str(record.get("timestamp_utc") or ""),
                "health_score": int(record.get("health_score") or 0),
                "trend": str(record.get("trend") or "BASELINE"),
                "reply_rate_pct": round(float(record.get("reply_rate_pct") or 0.0), 2),
            }
        )
    return timeline
