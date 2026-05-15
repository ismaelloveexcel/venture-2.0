"""Windowed trend interpretation for client run history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def _parse_ts(value: str) -> datetime:
    text = (value or "").strip()
    if not text:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _window_stats(records: list[dict[str, Any]], days: int) -> dict[str, Any]:
    if not records:
        return {"trend": "BASELINE"}
    latest_ts = max(_parse_ts(str(r.get("timestamp_utc") or "")) for r in records)
    cutoff = latest_ts - timedelta(days=days)
    window = [
        r for r in records if _parse_ts(str(r.get("timestamp_utc") or "")) >= cutoff
    ]
    if len(window) < 2:
        return {"trend": "BASELINE", "run_count": len(window)}

    window = sorted(
        window,
        key=lambda item: (
            str(item.get("timestamp_utc") or ""),
            str(item.get("run_id") or ""),
        ),
    )
    first = window[0]
    last = window[-1]
    delta_reply_rate = round(
        float(last.get("reply_rate_pct") or 0.0)
        - float(first.get("reply_rate_pct") or 0.0)
    )
    delta_health = int(last.get("health_score") or 0) - int(
        first.get("health_score") or 0
    )

    if delta_reply_rate >= 3 or delta_health >= 3:
        trend = "IMPROVING"
    elif delta_reply_rate <= -3 or delta_health <= -3:
        trend = "DECLINING"
    else:
        trend = "STABLE"

    return {
        "trend": trend,
        "delta_reply_rate": delta_reply_rate,
        "delta_health_score": delta_health,
        "run_count": len(window),
        "first_run_id": str(first.get("run_id") or ""),
        "last_run_id": str(last.get("run_id") or ""),
    }


def build_performance_windows(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "7_day": _window_stats(records, 7),
        "30_day": _window_stats(records, 30),
    }
