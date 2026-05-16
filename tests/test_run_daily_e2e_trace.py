"""
P2: orchestrator dry-run trace — run_daily writes a valid run_report after outbound subprocess.

Structural Resend POST isolation is enforced in validate_repo_contract (not duplicated here).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from run_report_schema import RunReport

ROOT = Path(__file__).resolve().parents[1]
RUN_DAILY = ROOT / "04-coding" / "scripts" / "run_daily.py"


def test_run_daily_execute_outbound_dry_run_writes_traceable_report(tmp_path: Path):
    report = tmp_path / "run_report.json"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["VENTURE_RUN_ID"] = "pytest_e2e_run_daily"
    env["VENTURE_CLIENT_WORKSPACE"] = str(workspace)
    env["VENTURE_SKIP_SOLO_OPERATOR_SYNC"] = "1"
    env["VENTURE_LOCAL_GENERATION"] = "1"
    proc = subprocess.run(
        [
            sys.executable,
            str(RUN_DAILY),
            "--generate-prospects",
            "--prospects-demo",
            "--prospect-count",
            "25",
            "--execute-outbound",
            "--dry-run",
            "--report-path",
            str(report),
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert report.is_file(), f"no report: stderr={proc.stderr!r} stdout={proc.stdout!r}"
    rep = RunReport.model_validate_json(report.read_text(encoding="utf-8"))
    assert rep.run_id == "pytest_e2e_run_daily"
    assert "prospect_builder_subprocess" in rep.outbound.phases
    assert "message_generator_subprocess" in rep.outbound.phases
    if rep.outbound.status != "BLOCKED":
        assert "venture_pipeline_subprocess" in rep.outbound.phases
    assert rep.outbound.prospect_batch.message_gen_ran is True
    if rep.outbound.status == "SUCCESS":
        assert rep.outbound.prospect_batch.message_gen_exit_code == 0
    else:
        assert rep.outbound.prospect_batch.message_gen_exit_code in {0, 1}
    assert rep.outbound.dry_run is True
    if "venture_pipeline_subprocess" in rep.outbound.phases:
        assert rep.outbound.subprocess_return_code is not None
    else:
        assert rep.outbound.subprocess_return_code is None
    if rep.outbound.status == "SUCCESS":
        assert "dry_run" in rep.outbound.money_path.reasons
        assert rep.outbound.pipeline_telemetry.schema_version == 1
        assert isinstance(rep.outbound.pipeline_telemetry.run_health, dict)
        assert rep.outbound.money_path_source == "pipeline_telemetry"
        assert "unknown_telemetry_schema_version" not in rep.outbound.money_path.reasons


def test_run_daily_no_execute_writes_not_executed(tmp_path: Path):
    report = tmp_path / "run_report_only.json"
    env = os.environ.copy()
    env["VENTURE_SKIP_SOLO_OPERATOR_SYNC"] = "1"
    subprocess.run(
        [
            sys.executable,
            str(RUN_DAILY),
            "--report-path",
            str(report),
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    rep = RunReport.model_validate_json(report.read_text(encoding="utf-8"))
    assert rep.outbound.status == "NOT_EXECUTED"
    assert rep.outbound.dry_run is None
