from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "04-coding" / "scripts"


def test_launch_day_executor_help_exits_zero() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "launch_day_executor.py"), "-h"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0
    assert "--outbound-go" in proc.stdout


def test_launch_monitor_help_exits_zero() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "launch_monitor.py"), "-h"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0
    assert "--live" in proc.stdout


def test_parse_checklist_counts(tmp_path: Path) -> None:
    sys.path.insert(0, str(SCRIPTS))
    from launch_day_executor import parse_checklist, verify_checklist_complete  # noqa: PLC0415

    p = tmp_path / "chk.md"
    p.write_text("# T\n- [ ] todo\n- [x] done\n- [X] also\n", encoding="utf-8")
    assert parse_checklist(p) == (1, 2)
    ok, msg = verify_checklist_complete(p)
    assert ok is False
    assert "unchecked=1" in msg

    p.write_text("- [x] only\n", encoding="utf-8")
    assert verify_checklist_complete(p)[0] is True


def test_launch_monitor_render_frame_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    sys.path.insert(0, str(SCRIPTS))
    import launch_monitor as lm  # noqa: PLC0415

    monkeypatch.setattr(
        lm,
        "_load_run_report",
        lambda: {
            "outbound": {
                "funnel_health_snapshots": [
                    {"qualified": 2, "sent": 1, "blocked": 0, "send_timestamp": "t"}
                ],
                "money_path": {"attempted": 1, "sent": 1, "blocked": 0},
            }
        },
    )
    monkeypatch.setattr(lm, "_load_launch_session", lambda: {"status": "COMPLETE"})
    monkeypatch.setattr(
        lm,
        "_sql_counts",
        lambda _db: {
            "bounce_24h": 0,
            "complaint_24h": 0,
            "delay_7d": 0,
            "unsub_7d": 0,
            "block_severity": __import__("collections").Counter(),
        },
    )
    monkeypatch.setattr(lm, "_bounce_ratio_rolling", lambda _db, days=7: (0.01, 0.0, 10))
    monkeypatch.setattr(lm, "_run_report_path", lambda: Path("run_report.json"))

    text = lm.render_frame(10)
    assert "LAUNCH MONITOR" in text
    assert "Sent (sum)" in text
