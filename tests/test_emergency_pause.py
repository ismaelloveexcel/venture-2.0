from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "04-coding" / "scripts"
MCP = ROOT / "venture-mcp-server"


def test_reply_analyzer_categorize() -> None:
    sys.path.insert(0, str(SCRIPTS))
    import reply_analyzer as ra  # noqa: PLC0415

    assert ra._categorize("This is too expensive for us") == "PRICE_SENSITIVE"
    assert ra._categorize("We already use Hubspot") == "ALREADY_USING"
    assert ra._categorize("Booked on calendly thanks") == "BOOKED"


def test_emergency_pause_writes_session_json(tmp_path: Path) -> None:
    session = tmp_path / "launch_session.json"
    db = tmp_path / "venture_jobs.db"
    sys.path.insert(0, str(MCP))
    from job_queue import JobQueue  # noqa: PLC0415

    JobQueue(str(db))
    env = {**os.environ, "VENTURE_LAUNCH_SESSION_PATH": str(session), "VENTURE_DB_PATH": str(db)}
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "launch_day_executor.py"),
            "--emergency-pause",
            "--pause-reason",
            "bounce_threshold_unit",
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(session.read_text(encoding="utf-8"))
    assert data.get("status") == "PAUSED"
    assert "bounce_threshold" in str(data.get("paused_reason", ""))


def test_emergency_pause_logs_hard_block(tmp_path: Path) -> None:
    session = tmp_path / "launch_session2.json"
    db = tmp_path / "venture_jobs2.db"
    sys.path.insert(0, str(MCP))
    from job_queue import JobQueue  # noqa: PLC0415

    JobQueue(str(db))
    env = {**os.environ, "VENTURE_LAUNCH_SESSION_PATH": str(session), "VENTURE_DB_PATH": str(db)}
    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "launch_day_executor.py"),
            "--emergency-pause",
            "--pause-reason",
            "pytest_block_log",
        ],
        cwd=str(ROOT),
        env=env,
        check=True,
    )
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            """
            SELECT reason, severity, block_type FROM block_logs
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        assert row is not None
        assert row[0] == "operator_emergency_pause"
        assert str(row[1]).upper() == "HARD"
        assert row[2] == "OPERATOR_PAUSE_BLOCK"
    finally:
        conn.close()


def test_live_send_blocked_if_session_paused(tmp_path: Path) -> None:
    session = tmp_path / "launch_session3.json"
    db = tmp_path / "venture_jobs3.db"
    sys.path.insert(0, str(MCP))
    from job_queue import JobQueue  # noqa: PLC0415

    JobQueue(str(db))
    session.write_text(
        json.dumps({"status": "PAUSED", "paused_reason": "pre_set"}),
        encoding="utf-8",
    )
    env = {**os.environ, "VENTURE_LAUNCH_SESSION_PATH": str(session), "VENTURE_DB_PATH": str(db)}
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "launch_day_executor.py"),
            "--outbound-go",
            "--skip-checklist",
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 3, (proc.stdout, proc.stderr)


def test_preflight_safety_check_help() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "preflight_safety_check.py"), "-h"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "--quick" in proc.stdout


def test_reply_analyzer_help() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "reply_analyzer.py"), "-h"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "--since-hours" in proc.stdout
