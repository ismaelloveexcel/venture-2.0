#!/usr/bin/env python3
"""
CI-level repo contract (vFINAL.1): CLI allowlist, CIS isolation, __main__ gates, schema import,
Resend POST endpoint isolation (P2), landing ICP semantic latch (docs/SEMANTIC_CONTRACT.md §8.2).

Run from repository root:
  python 04-coding/scripts/validate_repo_contract.py
"""
from __future__ import annotations

import ast
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

_DEADLINE = time.perf_counter() + 14.0


def _check_time() -> None:
    if time.perf_counter() > _DEADLINE:
        raise RuntimeError("validate_repo_contract exceeded time budget")


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    # .../VENTURE 2.0/04-coding/scripts/validate_repo_contract.py
    return here.parents[2]


def _scripts_dir(repo: Path) -> Path:
    return repo / "04-coding" / "scripts"


def _load_allowlist(scripts: Path) -> set[str]:
    path = scripts / "contract_cli_allowlist.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("allowlist must be a JSON array of filenames")
    return {str(x) for x in data}


def _check_argparse_allowlist(scripts: Path, allowlist: set[str]) -> list[str]:
    errors: list[str] = []
    if "run_daily.py" not in allowlist:
        errors.append("contract_cli_allowlist.json must include run_daily.py")
    rd = scripts / "run_daily.py"
    if not rd.is_file():
        errors.append("run_daily.py missing (canonical orchestrator)")
    elif "ArgumentParser" not in rd.read_text(encoding="utf-8"):
        errors.append("run_daily.py must define argparse.ArgumentParser")
    skip_scan = {"validate_repo_contract.py"}
    for py in sorted(scripts.glob("*.py")):
        _check_time()
        if py.name in skip_scan:
            continue
        text = py.read_text(encoding="utf-8")
        if "ArgumentParser(" not in text:
            continue
        if py.name not in allowlist:
            errors.append(
                f"ArgumentParser in {py.name} but file not in contract_cli_allowlist.json "
                f"(add to allowlist or remove CLI from this module)"
            )
    return errors


def _check_main_gates(scripts: Path) -> list[str]:
    errors: list[str] = []
    for name in ("venture_pipeline.py", "shadow_drift_tracker.py", "run_pipeline.py"):
        _check_time()
        p = scripts / name
        text = p.read_text(encoding="utf-8")
        if "if __name__ ==" not in text:
            errors.append(f"{name}: missing __main__ block")
            continue
        if "VENTURE_DEV_MAIN" not in text:
            errors.append(f"{name}: __main__ must gate on VENTURE_DEV_MAIN")
    return errors


def _cis_import_isolation(scripts: Path) -> list[str]:
    errors: list[str] = []
    src = (scripts / "shadow_drift_tracker.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    banned = {"venture_pipeline", "send_guard", "job_queue"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split(".")[0]
                if mod in banned:
                    errors.append(f"shadow_drift_tracker.py must not import {mod}")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod = node.module.split(".")[0]
                if mod in banned:
                    errors.append(f"shadow_drift_tracker.py must not import from {mod}")
    return errors


def _check_schema_import(scripts: Path) -> list[str]:
    errors: list[str] = []
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    try:
        from run_report_schema import RunReport  # noqa: PLC0415

        # Single source of truth: contract keys must match Pydantic model fields (no parallel field list).
        required_top = {
            "schema_version",
            "run_id",
            "timestamp_utc",
            "outbound",
            "cis_eval",
            "system",
        }
        if required_top != set(RunReport.model_fields.keys()):
            errors.append(
                "run_report RunReport model fields drifted from contract "
                f"(expected keys={sorted(required_top)})"
            )

        sample = RunReport(
            run_id="test",
            timestamp_utc="2026-01-01T00:00:00Z",
        )
        sample.model_dump_json()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"run_report_schema import/round-trip failed: {exc}")
    return errors


def _check_prospects_csv_schema(repo: Path) -> list[str]:
    """Committed prospects.csv must include governed columns (single source for gating)."""
    p = repo / "06-sales" / "prospects.csv"
    if not p.is_file():
        return []
    try:
        with p.open(newline="", encoding="utf-8") as fh:
            row = next(csv.reader(fh), None)
    except OSError as exc:
        return [f"06-sales/prospects.csv unreadable: {exc}"]
    if not row:
        return ["06-sales/prospects.csv has no header row"]
    headers = {h.strip() for h in row}
    required = {
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
    }
    missing = sorted(required - headers)
    if missing:
        return [f"06-sales/prospects.csv missing columns: {missing}"]
    return []


def _check_prospects_csv_write_isolation(scripts: Path) -> list[str]:
    """
    Only prospect_gate (ELIGIBLE projection), venture_pipeline (status sync), and
    client_manager (workspace bootstrap) may open PROSPECTS_FILE / prospects.csv for write.
    """
    allow = frozenset({"prospect_gate.py", "venture_pipeline.py", "client_manager.py"})
    errs: list[str] = []
    open_prospects_write = re.compile(
        r"open\s*\(\s*PROSPECTS_FILE\s*,[^\)]*[\"']([wa])[\"']",
        re.MULTILINE,
    )
    literal_open_write = re.compile(
        r"open\s*\([^)]*prospects\.csv[^)]*[\"']([wa])[\"']",
        re.MULTILINE,
    )
    for py in sorted(scripts.glob("*.py")):
        if py.name in allow:
            continue
        _check_time()
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if open_prospects_write.search(text):
            errs.append(
                f"prospects write isolation: {py.name} opens PROSPECTS_FILE for write/append "
                "(canonical writers: prospect_gate.write_eligible_prospects_csv, "
                "venture_pipeline.sync_prospect_status_to_source_csv, client_manager bootstrap)"
            )
        if literal_open_write.search(text):
            errs.append(
                f"prospects write isolation: {py.name} opens a prospects.csv path for write/append"
            )
    return errs


def _check_venture_phase_state(repo: Path) -> list[str]:
    """Light machine-readable phase tracking (P3-P6 orchestration)."""
    p = repo / "04-coding" / ".venture_phase_state.json"
    if not p.is_file():
        return ["04-coding/.venture_phase_state.json missing"]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [f"venture_phase_state invalid JSON: {exc}"]
    for key in ("schema_version", "current_phase", "completed"):
        if key not in data:
            return [f"venture_phase_state missing key: {key!r}"]
    if not isinstance(data["completed"], list):
        return ["venture_phase_state.completed must be a list"]
    return []


def _check_landing_icp_semantic_latch(repo: Path) -> list[str]:
    """
    Machine-readable ICP state on static landing draft (docs/SEMANTIC_CONTRACT.md §8.2).

    Always: exactly one of PENDING or LOCKED marker in index.html.
    When VENTURE_ENFORCE_LANDING_ICP is set OR launch_execution_state.json
    has landing_icp == locked: marker must be LOCKED (not pending).
    """
    landing = repo / "04-coding" / "boilerplates" / "landing-page" / "index.html"
    if not landing.is_file():
        return []

    text = landing.read_text(encoding="utf-8")
    marker_pending = "<!-- VENTURE_SEMANTIC:LANDING_ICP=pending -->"
    marker_locked = "<!-- VENTURE_SEMANTIC:LANDING_ICP=locked -->"
    has_p = marker_pending in text
    has_l = marker_locked in text
    if has_p == has_l:
        return [
            "Landing ICP latch: index.html must contain exactly one of "
            f"{marker_pending!r} or {marker_locked!r} (see docs/SEMANTIC_CONTRACT.md §8.2)"
        ]

    enforce_env = os.environ.get("VENTURE_ENFORCE_LANDING_ICP", "").lower() in (
        "1",
        "true",
        "yes",
    )
    state_enforce = False
    state_path = repo / "04-coding" / "state" / "launch_execution_state.json"
    if state_path.is_file():
        _check_time()
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            if data.get("landing_icp") == "locked":
                state_enforce = True
        except Exception:
            pass

    if enforce_env or state_enforce:
        _check_time()
        if not has_l:
            return [
                "Landing ICP must be LOCKED: set "
                f"{marker_locked!r} in boilerplates/landing-page/index.html "
                "and replace placeholder ICP copy (VENTURE_ENFORCE_LANDING_ICP or "
                "launch_execution_state.json landing_icp=locked)"
            ]
        if has_p:
            return [
                "Landing ICP locked mode: remove pending marker; only "
                f"{marker_locked!r} must be present"
            ]
    return []


def _check_resend_emails_endpoint_isolation(repo: Path) -> list[str]:
    """
    P2: outbound Resend POST URL must not appear outside send_guard.py
    (same invariant as batch1_release_gate static_gate; behavioral chokepoint).
    """
    # Substring must stay out of repo docs (.md etc.) or they appear in this scan.
    endpoint = "api.resend.com/emails"
    skip_dirs = {".git", ".venv", "node_modules", "__pycache__", ".tox", "dist", "build"}
    matches: list[str] = []
    for path in repo.rglob("*"):
        if not path.is_file() or any(part in skip_dirs for part in path.parts):
            continue
        if path.suffix.lower() not in {".py", ".ps1", ".md", ".json", ".txt"}:
            continue
        if path.name == "validate_repo_contract.py":
            continue
        _check_time()
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if endpoint in text:
            matches.append(str(path.relative_to(repo)).replace("\\", "/"))
    expected = ["04-coding/scripts/send_guard.py"]
    if sorted(matches) != sorted(expected):
        return [
            "P2 Resend isolation: "
            f"substring {endpoint!r} must appear only in {expected}, "
            f"found {sorted(matches)}"
        ]
    return []


def _check_e2e_trace_artifact_isolation(repo: Path) -> list[str]:
    """
    Guard against test-driven churn in governed artifact files.

    The run_daily e2e trace test must execute in an isolated client workspace and
    skip solo-operator mirror writes.
    """
    test_path = repo / "tests" / "test_run_daily_e2e_trace.py"
    if not test_path.is_file():
        return ["tests/test_run_daily_e2e_trace.py missing (trace guard required)"]
    text = test_path.read_text(encoding="utf-8")
    errs: list[str] = []
    if "VENTURE_CLIENT_WORKSPACE" not in text:
        errs.append(
            "e2e trace isolation: tests/test_run_daily_e2e_trace.py must set "
            "VENTURE_CLIENT_WORKSPACE to avoid writing governed repo artifacts"
        )
    if "VENTURE_SKIP_SOLO_OPERATOR_SYNC" not in text:
        errs.append(
            "e2e trace isolation: tests/test_run_daily_e2e_trace.py must set "
            "VENTURE_SKIP_SOLO_OPERATOR_SYNC=1 to avoid mutating docs/solo-operator/run_report.json"
        )
    return errs


def main() -> int:
    repo = _repo_root()
    scripts = _scripts_dir(repo)
    if not scripts.is_dir():
        print("FATAL: 04-coding/scripts not found", file=sys.stderr)
        return 1

    errs: list[str] = []
    try:
        allowlist = _load_allowlist(scripts)
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: allowlist: {exc}", file=sys.stderr)
        return 1

    errs.extend(_check_argparse_allowlist(scripts, allowlist))
    errs.extend(_check_main_gates(scripts))
    errs.extend(_cis_import_isolation(scripts))
    errs.extend(_check_schema_import(scripts))
    errs.extend(_check_venture_phase_state(repo))
    errs.extend(_check_prospects_csv_schema(repo))
    errs.extend(_check_prospects_csv_write_isolation(scripts))
    errs.extend(_check_resend_emails_endpoint_isolation(repo))
    errs.extend(_check_e2e_trace_artifact_isolation(repo))
    errs.extend(_check_landing_icp_semantic_latch(repo))

    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        return 1
    print("validate_repo_contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
