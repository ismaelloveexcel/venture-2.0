from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "04-coding" / "venture-engine"))

from client_runtime.trends import build_trend_outputs


def _write_run(
    run_dir: Path,
    run_id: str,
    timestamp: datetime,
    health_score: int,
    reply_rate_pct: float,
    trend: str,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "run_report.json": {
            "run_id": run_id,
            "timestamp_utc": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "projection.json": {"run_id": run_id, "reply_rate_pct": reply_rate_pct},
        "comparison.json": {"trend": trend},
        "health.json": {"health_score": health_score, "label": trend},
    }
    for name, payload in payloads.items():
        (run_dir / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_build_trend_outputs(tmp_path: Path) -> None:
    repo_root = tmp_path
    client_dir = repo_root / "clients" / "acme-demo" / "runs"
    now = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    _write_run(
        client_dir / "run-1", "run-1", now - timedelta(days=10), 70, 16.0, "STABLE"
    )
    _write_run(
        client_dir / "run-2", "run-2", now - timedelta(days=3), 74, 18.0, "IMPROVING"
    )
    _write_run(client_dir / "run-3", "run-3", now, 81, 24.0, "IMPROVING")

    outputs = build_trend_outputs(
        repo_root=repo_root,
        client_id="acme-demo",
        run_id="run-3",
        run_dir=client_dir / "run-3",
    )

    summary_path = client_dir / "run-3" / "trend_summary.json"
    timeline_path = client_dir / "run-3" / "timeline.json"
    windows_path = client_dir / "run-3" / "performance_windows.json"
    projection_path = client_dir / "run-3" / "trend_projection.json"

    assert summary_path.is_file()
    assert timeline_path.is_file()
    assert windows_path.is_file()
    assert projection_path.is_file()

    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    windows = json.loads(windows_path.read_text(encoding="utf-8"))
    projection = json.loads(projection_path.read_text(encoding="utf-8"))

    assert [item["run_id"] for item in timeline] == ["run-1", "run-2", "run-3"]
    assert windows["7_day"]["trend"] in {"IMPROVING", "STABLE", "DECLINING", "BASELINE"}
    assert projection["projected_state"] in {
        "IMPROVING",
        "STABLE",
        "DECLINING",
        "BASELINE",
    }
    assert outputs["trend_summary"]["history_count"] == 3
