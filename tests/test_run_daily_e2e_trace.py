"""
P2: orchestrator dry-run trace — run_daily writes a valid run_report after outbound subprocess.

Structural Resend POST isolation is enforced in validate_repo_contract (not duplicated here).
"""
from __future__ import annotations

import csv
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
    (workspace / "openai.py").write_text(
        "class OpenAI:\n    def __init__(self, *args, **kwargs):\n        pass\n",
        encoding="utf-8",
    )
    prospects_dir = workspace / "06-sales"
    prospects_dir.mkdir(parents=True, exist_ok=True)
    prospects = prospects_dir / "prospects.csv"
    with prospects.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "company_name",
                "domain",
                "name",
                "email",
                "role",
                "industry",
                "pain_signal",
                "linkedin_url",
                "validation_status",
                "validation_reason",
                "source",
                "run_id",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "company_name": "Auditbound Labs",
                "domain": "auditboundlabs.com",
                "name": "Avery Quinn",
                "email": "avery@auditboundlabs.com",
                "role": "Founder",
                "industry": "outbound agency",
                "pain_signal": "pipeline_visibility",
                "linkedin_url": "",
                "validation_status": "READY",
                "validation_reason": "complete_profile",
                "source": "pytest_seed",
                "run_id": "pytest_e2e_run_daily",
            }
        )
    env = os.environ.copy()
    env["VENTURE_RUN_ID"] = "pytest_e2e_run_daily"
    env["VENTURE_CLIENT_WORKSPACE"] = str(workspace)
    env["VENTURE_SKIP_SOLO_OPERATOR_SYNC"] = "1"
    env["VENTURE_LOCAL_GENERATION"] = "1"
    env["PYTHONPATH"] = str(workspace) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [
            sys.executable,
            str(RUN_DAILY),
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
    assert proc.returncode == 0, f"stderr={proc.stderr!r} stdout={proc.stdout!r}"
    assert report.is_file(), f"no report: stderr={proc.stderr!r} stdout={proc.stdout!r}"
    rep = RunReport.model_validate_json(report.read_text(encoding="utf-8"))
    assert rep.run_id == "pytest_e2e_run_daily"
    assert "message_generator_subprocess" in rep.outbound.phases
    assert "venture_pipeline_subprocess" in rep.outbound.phases
    assert rep.outbound.prospect_batch.message_gen_ran is True
    assert rep.outbound.prospect_batch.message_gen_exit_code == 0
    assert rep.outbound.dry_run is True
    assert rep.outbound.subprocess_return_code == 0
    assert rep.outbound.status == "SUCCESS"
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
