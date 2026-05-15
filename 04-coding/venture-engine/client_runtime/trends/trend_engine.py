"""Filesystem-scanned multi-run trend intelligence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from client_runtime.file_io import atomic_write_json

from .performance_windows import build_performance_windows
from .timeline_builder import build_timeline
from .trend_projection import build_trend_projection


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


def _safe_read_json(path: Path) -> dict[str, Any]:
    try:
        if not path.is_file():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def load_history(repo_root: Path, client_id: str) -> list[dict[str, Any]]:
    runs_dir = repo_root / "clients" / client_id / "runs"
    if not runs_dir.is_dir():
        return []

    records: list[dict[str, Any]] = []
    for run_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        run_report = _safe_read_json(run_dir / "run_report.json")
        health = _safe_read_json(run_dir / "health.json")
        comparison = _safe_read_json(run_dir / "comparison.json")
        projection = _safe_read_json(run_dir / "projection.json")

        timestamp_utc = str(run_report.get("timestamp_utc") or "")
        if not timestamp_utc:
            try:
                timestamp_utc = datetime.fromtimestamp(
                    run_dir.stat().st_mtime, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
            except OSError:
                timestamp_utc = "1970-01-01T00:00:00Z"

        records.append(
            {
                "run_id": run_dir.name,
                "timestamp_utc": timestamp_utc,
                "health_score": int(health.get("health_score") or 0),
                "trend": str(
                    comparison.get("trend") or health.get("label") or "BASELINE"
                ),
                "reply_rate_pct": float(
                    projection.get("reply_rate_pct")
                    or projection.get("reply_rate")
                    or 0.0
                ),
                "qualified_pct": float(
                    projection.get("qualified_pct")
                    or projection.get("qualified_rate")
                    or 0.0
                ),
                "run_report": run_report,
                "comparison": comparison,
                "health": health,
                "projection": projection,
                "_sort_ts": _parse_ts(timestamp_utc),
            }
        )

    return sorted(records, key=lambda item: (item["_sort_ts"], item["run_id"]))


def build_trend_outputs(
    *,
    repo_root: Path,
    client_id: str,
    run_id: str,
    run_dir: Path,
) -> dict[str, Any]:
    history = load_history(repo_root, client_id)
    timeline = build_timeline(history)
    performance_windows = build_performance_windows(history)
    trend_projection = build_trend_projection(timeline, performance_windows)

    latest = timeline[-1] if timeline else {"trend": "BASELINE", "health_score": 0}
    trend_summary = {
        "client_id": client_id,
        "run_id": run_id,
        "history_count": len(history),
        "current_trend": latest.get("trend", "BASELINE"),
        "latest_health_score": latest.get("health_score", 0),
        "window_trends": {
            "7_day": performance_windows.get("7_day", {}).get("trend", "BASELINE"),
            "30_day": performance_windows.get("30_day", {}).get("trend", "BASELINE"),
        },
        "trend_projection": trend_projection,
    }

    atomic_write_json(run_dir / "timeline.json", timeline)
    atomic_write_json(run_dir / "performance_windows.json", performance_windows)
    atomic_write_json(run_dir / "trend_projection.json", trend_projection)
    atomic_write_json(run_dir / "trend_summary.json", trend_summary)

    return {
        "trend_summary": trend_summary,
        "timeline": timeline,
        "performance_windows": performance_windows,
        "trend_projection": trend_projection,
        "paths": {
            "trend_summary": str(run_dir / "trend_summary.json"),
            "timeline": str(run_dir / "timeline.json"),
            "performance_windows": str(run_dir / "performance_windows.json"),
            "trend_projection": str(run_dir / "trend_projection.json"),
        },
    }
