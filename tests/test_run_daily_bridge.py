"""P5: run_daily bridge validate (contract + fast pytest subset)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_DAILY = ROOT / "04-coding" / "scripts" / "run_daily.py"


def test_run_daily_bridge_validate_exits_zero():
    proc = subprocess.run(
        [sys.executable, str(RUN_DAILY), "bridge", "validate"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_run_daily_bridge_secrets_exits_zero_and_reports_status_lines():
    proc = subprocess.run(
        [sys.executable, str(RUN_DAILY), "bridge", "secrets"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    out = proc.stdout
    assert "DOTENV_FILE\t" in out
    for name in (
        "APOLLO_API_KEY",
        "HUNTER_API_KEY",
        "OPENAI_API_KEY",
        "RESEND_API_KEY",
    ):
        assert f"SECRET_STATUS\t{name}\t" in out
