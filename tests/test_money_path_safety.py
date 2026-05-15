"""Money-path and gate invariants (mock-light; subprocess for CLI gates)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from run_report_schema import MoneyPathModel, RunReport

ROOT = Path(__file__).resolve().parents[1]
VENTURE_PIPELINE = ROOT / "04-coding" / "scripts" / "venture_pipeline.py"
VALIDATE = ROOT / "04-coding" / "scripts" / "validate_repo_contract.py"


def test_money_path_defaults_are_safe():
    m = MoneyPathModel()
    assert m.attempted == m.sent == m.blocked == 0
    assert m.reasons == []


def test_run_report_default_outbound_not_executed():
    r = RunReport(run_id="t", timestamp_utc="2026-01-01T00:00:00Z")
    assert r.outbound.status == "NOT_EXECUTED"
    assert r.outbound.money_path.sent == 0


def test_venture_pipeline_cli_gated_without_dev_main():
    env = os.environ.copy()
    env.pop("VENTURE_DEV_MAIN", None)
    proc = subprocess.run(
        [sys.executable, str(VENTURE_PIPELINE)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert proc.returncode == 2
    out = f"{proc.stderr}\n{proc.stdout}".lower()
    assert "run_daily" in out or "gated" in out


def test_validate_repo_contract_exits_zero():
    proc = subprocess.run(
        [sys.executable, str(VALIDATE)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_validate_repo_contract_enforce_landing_icp_fails_while_pending():
    """VENTURE_ENFORCE_LANDING_ICP requires locked latch (docs/SEMANTIC_CONTRACT.md §8.2)."""
    env = os.environ.copy()
    env["VENTURE_ENFORCE_LANDING_ICP"] = "1"
    proc = subprocess.run(
        [sys.executable, str(VALIDATE)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert proc.returncode == 1, "expected contract failure under enforce with pending latch"
    err = proc.stderr + proc.stdout
    assert "Landing ICP" in err or "LANDING_ICP" in err, err
