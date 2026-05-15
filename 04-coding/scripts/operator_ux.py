"""
Operator-facing CLI helpers: ANSI highlights (NO_COLOR aware), artifact paths, exit hints.
No ArgumentParser here - import-only module (contract allowlist safe).
"""

from __future__ import annotations

import json
import os
import sys
import csv
from pathlib import Path
from typing import Any

# Human-readable explanations for send_skipped_log.csv skip_reason values
# (must stay aligned with outbound_eligibility.append_send_skipped_log).
SKIP_REASON_HUMAN: dict[str, str] = {
    "validation_status_not_READY": (
        "Row is not READY in prospects.csv - only READY rows reach outbound after message approval."
    ),
    "missing_run_id_on_prospect_row": (
        "prospects.csv row has no run_id and VENTURE_RUN_ID/BATCH_RUN_ID was empty - re-run "
        "prospect_builder with VENTURE_RUN_ID set (run_daily sets this)."
    ),
    "run_id_mismatch": (
        "Row run_id does not match this execution's run id - regenerate the batch or align env VENTURE_RUN_ID."
    ),
    "not_ELIGIBLE_in_audit_log": (
        "No ELIGIBLE audit row for (run_id, normalized email) in 07-kpis/prospect_audit_log.csv - "
        "re-run prospect_builder / gate for this cohort."
    ),
    "audit_log_unreadable_or_empty_index": (
        "Audit file missing rows, failed to parse, or produced an empty index - fix or replace "
        "07-kpis/prospect_audit_log.csv (see OPERATOR_RUNBOOK)."
    ),
}


def humanize_skip_reason(code: str | None) -> str:
    c = (code or "").strip()
    if not c:
        return "No skip_reason recorded."
    return SKIP_REASON_HUMAN.get(
        c, f"Code {c!r} - see OPERATOR_RUNBOOK (outbound eligibility)."
    )


def _use_color() -> bool:
    return sys.stdout.isatty() and not (os.environ.get("NO_COLOR", "").strip())


def _c(code: str, text: str) -> str:
    if not _use_color():
        return text
    return f"{code}{text}\033[0m"


def format_abs_path(p: Path | str) -> str:
    try:
        return str(Path(p).expanduser().resolve())
    except OSError:
        return str(p)


PROSPECT_BUILDER_EXIT_HINTS: dict[int, str] = {
    1: "Fix sourcing (API keys or --demo), or fix prospect_audit_log.csv header so append succeeds.",
    2: "Eligible set vs audit ELIGIBLE mismatch - do not hand-edit mid-batch; re-run prospect_builder after code/data fix.",
    3: "prospects.csv round-trip failed after write - check disk permissions and schema; see strict summary JSON if enabled.",
    11: "VENTURE_STRICT_PROSPECT_AUDIT=1 and forensic checks failed - inspect 07-kpis/strict_mode_summary/*.json.",
}


VENTURE_PIPELINE_EXIT_HINTS: dict[int, str] = {
    2: "CLI / environment gate - read stderr; often missing VENTURE_DEV_MAIN for direct pipeline invocations.",
    3: "Configuration or dependency failure - validate .env and integration readiness messages above.",
    4: "Runtime guard - see printed [fail] lines (capacity, config, or provider).",
    5: "Integrity monitor blocked live outreach - review printed reasons; check job_queue freeze state.",
    6: "Outreach frozen by system control - clear freeze after investigation.",
    7: "Batch 1 guard / lock / preflight - open printed preflight log path; resolve manifest or lock issues.",
    8: "Generation batch aborted mid-run - see batch_abort_reason in logs.",
    9: "Outbound eligibility HALT - missing or bad audit header, or send_skipped_log.csv header mismatch. "
    "Fix 07-kpis/prospect_audit_log.csv or logs/send_skipped_log.csv per message.",
}


def print_prospect_builder_exit_card(code: int) -> None:
    hint = PROSPECT_BUILDER_EXIT_HINTS.get(
        code, "See OPERATOR_RUNBOOK - Troubleshooting (exit codes)."
    )
    print()
    print(_c("\033[1;31m", f"-- prospect_builder stopped (exit {code}) --"))
    print(_c("\033[33m", f"Next: {hint}"))
    print(
        _c("\033[2m", "Docs: OPERATOR_RUNBOOK.md (Troubleshooting -> prospect_builder)")
    )


def print_prospect_builder_success_banner(
    *,
    output_file: Path,
    data_base: Path,
    run_id: str,
    rows_written: int,
) -> None:
    from prospect_gate import sanitize_run_id_fs

    rid_fs = sanitize_run_id_fs(run_id)
    digest = data_base / "07-kpis" / "prospect_generation_digest" / f"{rid_fs}.json"
    audit = data_base / "07-kpis" / "prospect_audit_log.csv"
    print()
    print(_c("\033[1;32m", f"-- prospect_builder OK ({rows_written} READY rows) --"))
    print(f"  prospects.csv:  {format_abs_path(output_file)}")
    print(f"  audit log:      {format_abs_path(audit)}")
    print(f"  digest:         {format_abs_path(digest)}")
    print(
        _c(
            "\033[2m",
            "  Next: message_generator_solo.py or set VENTURE_CANONICAL_ENTRY=1 && run_daily.py --execute",
        )
    )


def print_run_daily_operator_footer(
    *,
    report_path: Path,
    data_base: Path,
    outbound_status: str,
    run_id: str,
    ran_generate: bool,
    ran_outbound: bool,
    pipeline_rc: int | None,
    dry_run: bool,
) -> None:
    skip_log = data_base / "logs" / "send_skipped_log.csv"
    print()
    title = "SUCCESS" if outbound_status == "SUCCESS" else outbound_status
    color = "\033[1;32m" if outbound_status == "SUCCESS" else "\033[1;33m"
    if outbound_status == "FAILED":
        color = "\033[1;31m"
    print(_c(color, f"-- run_daily complete - outbound {title} --"))
    print(f"  run_report.json: {format_abs_path(report_path)}")
    print(f"  DATA_BASE:       {format_abs_path(data_base)}")
    if ran_generate:
        print(
            _c(
                "\033[2m",
                "  (prospect_builder ran - see digest under DATA_BASE/07-kpis/prospect_generation_digest/)",
            )
        )
    if ran_outbound:
        mode = "dry-run" if dry_run else "live"
        print(f"  pipeline child:  exit {pipeline_rc!r} ({mode})")
        if pipeline_rc not in (None, 0):
            hint = VENTURE_PIPELINE_EXIT_HINTS.get(
                int(pipeline_rc),
                "See stderr tail in run_report outbound.errors and venture-pipeline log.",
            )
            print(_c("\033[33m", f"  Next: {hint}"))
    if skip_log.is_file():
        print(f"  send_skipped:    {format_abs_path(skip_log)}")
    print(
        _c(
            "\033[2m",
            "  Tab summary line above: status | records | risk | outbound_state",
        )
    )


def operator_status_payload(
    *,
    repo_root: Path,
    data_base: Path,
) -> dict[str, Any]:
    """JSON-serializable snapshot for dashboard / tools."""
    report_path = repo_root / "run_report.json"
    out: dict[str, Any] = {
        "run_report_path": format_abs_path(report_path),
        "data_base": format_abs_path(data_base),
        "outbound_status": None,
        "run_id": None,
        "generation_digest_path": None,
        "send_skipped_log_path": format_abs_path(
            data_base / "logs" / "send_skipped_log.csv"
        ),
        "skipped_rows": [],
    }
    if report_path.is_file():
        try:
            rep = json.loads(report_path.read_text(encoding="utf-8"))
            ob = rep.get("outbound") or {}
            out["outbound_status"] = ob.get("status")
            out["run_id"] = rep.get("run_id")
            rid = (rep.get("run_id") or "").strip()
            if rid:
                from prospect_gate import sanitize_run_id_fs

                dig = (
                    data_base
                    / "07-kpis"
                    / "prospect_generation_digest"
                    / f"{sanitize_run_id_fs(rid)}.json"
                )
                if dig.is_file():
                    out["generation_digest_path"] = format_abs_path(dig)
        except (OSError, json.JSONDecodeError):
            pass
    sk = data_base / "logs" / "send_skipped_log.csv"
    if sk.is_file():
        try:
            with sk.open(newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            for row in rows[-30:]:
                reason = (row.get("skip_reason") or "").strip()
                out["skipped_rows"].append(
                    {
                        "email": (row.get("email") or "").strip(),
                        "skip_reason": reason,
                        "why": humanize_skip_reason(reason),
                        "audit_classification": (
                            row.get("audit_classification") or ""
                        ).strip(),
                        "timestamp_utc": (row.get("timestamp_utc") or "").strip(),
                    }
                )
        except OSError:
            pass
    return out
