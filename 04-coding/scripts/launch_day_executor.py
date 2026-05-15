#!/usr/bin/env python3
"""
Launch day orchestrator — rehearsal and live outbound around run_daily.py (non-interactive).

Does not replace run_daily.py; wraps it with preflight, session heartbeat, and optional batch loop.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_REPO = _SCRIPTS.parent.parent
_STATE_DIR = _REPO / "04-coding" / "state"


def launch_session_path() -> Path:
    raw = (os.environ.get("VENTURE_LAUNCH_SESSION_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (_STATE_DIR / "launch_session.json").resolve()


def operator_checklist_path() -> Path:
    raw = (os.environ.get("VENTURE_OPERATOR_CHECKLIST_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (_REPO / "04-coding" / "OPERATOR_LAUNCH_READINESS.md").resolve()


if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_launch_session() -> dict:
    p = launch_session_path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_launch_session(**kwargs: object) -> dict:
    prev = read_launch_session()
    body = {**prev, **{k: v for k, v in kwargs.items() if v is not None}}
    body.setdefault("updated_at_utc", _utc_iso())
    _atomic_write_json(launch_session_path(), body)
    return body


def parse_checklist(path: Path) -> tuple[int, int]:
    """Return (unchecked_count, checked_count) for markdown `- [ ]` / `- [x]` lines."""
    if not path.is_file():
        return (1, 0)
    text = path.read_text(encoding="utf-8", errors="replace")
    unchecked = len(re.findall(r"^-\s*\[\s*\]\s", text, flags=re.MULTILINE))
    checked = len(re.findall(r"^-\s*\[[xX]\]\s", text, flags=re.MULTILINE))
    return (unchecked, checked)


def verify_checklist_complete(path: Path) -> tuple[bool, str]:
    unchecked, checked = parse_checklist(path)
    if unchecked == 0 and checked > 0:
        return True, f"checklist_ok items_marked_done={checked}"
    if checked == 0 and unchecked == 0:
        return False, "checklist_empty_or_unrecognized_format"
    return False, f"checklist_incomplete unchecked={unchecked} checked={checked}"


def _env_bool(name: str, default: bool = False) -> bool:
    v = (os.environ.get(name, "") or "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "y", "on"}


def _effective_secret(name: str) -> bool:
    v = (os.environ.get(name, "") or "").strip()
    if not v:
        return False
    low = v.lower()
    if any(x in low for x in ("...", "your", "example", "changeme")):
        return False
    return True


def verify_env_for_live() -> tuple[bool, str]:
    if not _effective_secret("RESEND_API_KEY"):
        return False, "RESEND_API_KEY missing or placeholder"
    if not _env_bool("ENABLE_SUPPRESSION_CHECKS", False):
        return False, "ENABLE_SUPPRESSION_CHECKS must be true for live launch"
    if _env_bool("ALLOW_OPERATOR_OVERRIDE", False):
        return False, "ALLOW_OPERATOR_OVERRIDE must be false for live launch"
    return True, "env_ok"


def verify_db_unlocked() -> tuple[bool, str]:
    try:
        import sqlite3

        from runtime_config import (
            resolve_data_base,
            resolve_venture_db_path,
        )  # noqa: PLC0415

        db = resolve_venture_db_path(resolve_data_base(_REPO), _REPO)
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        return False, f"db_open_failed:{exc}"
    return True, "db_ok"


def load_run_report_summary() -> dict:
    try:
        from run_report_writer import (
            parse_run_report,
            resolve_run_report_path,
        )  # noqa: PLC0415

        p = resolve_run_report_path(
            _REPO, client_id=os.environ.get("VENTURE_CLIENT_ID"), explicit=None
        )
        if not p.is_file():
            return {"error": "run_report_missing", "path": str(p)}
        rr = parse_run_report(p)
        ob = rr.outbound
        snaps = list(ob.funnel_health_snapshots or [])
        last = snaps[-1].model_dump(mode="json") if snaps else {}
        mp = ob.money_path.model_dump(mode="json")
        return {
            "path": str(p),
            "outbound_status": ob.status,
            "money_path": mp,
            "last_snapshot": last,
            "snapshot_count": len(snaps),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _bounce_ratio_from_db() -> float:
    try:
        mcp = _REPO / "venture-mcp-server"
        if str(mcp) not in sys.path:
            sys.path.insert(0, str(mcp))
        from runtime_config import (
            resolve_data_base,
            resolve_venture_db_path,
        )  # noqa: PLC0415
        from job_queue import get_queue  # noqa: PLC0415

        db = str(resolve_venture_db_path(resolve_data_base(_REPO), _REPO))
        jq = get_queue(db_path=db)
        m = jq.get_delivery_ratio_metrics(
            int(os.environ.get("VENTURE_DELIVERY_METRICS_DAYS", "7") or 7)
        )
        return float(m.get("bounce_ratio") or 0.0)
    except Exception:
        return 0.0


def run_daily_subprocess(*, dry_run: bool) -> int:
    cmd = [
        sys.executable,
        str(_SCRIPTS / "run_daily.py"),
        "--generate-prospects",
        "--execute",
    ]
    if dry_run:
        cmd.append("--dry-run")
    env = os.environ.copy()
    env["VENTURE_CANONICAL_ENTRY"] = "1"
    proc = subprocess.run(
        cmd,
        cwd=str(_REPO),
        env=env,
        check=False,
    )
    return int(proc.returncode)


def cmd_outbound_go(args: argparse.Namespace) -> int:
    dry = bool(args.dry_run)
    if not dry:
        if read_launch_session().get("status") == "PAUSED":
            write_launch_session(
                status="PAUSED",
                paused_reason="launch_blocked_session_already_paused",
                timestamp_utc=_utc_iso(),
            )
            print(
                "launch_day_executor: session is PAUSED; refusing live outbound-go.",
                file=sys.stderr,
            )
            return 3
        if not args.skip_checklist:
            ok_ch, msg_ch = verify_checklist_complete(operator_checklist_path())
            if not ok_ch:
                print(
                    f"launch_day_executor: checklist failed: {msg_ch}", file=sys.stderr
                )
                return 1
        ok_env, msg_env = verify_env_for_live()
        if not ok_env:
            print(
                f"launch_day_executor: env preflight failed: {msg_env}", file=sys.stderr
            )
            return 1
    ok_db, msg_db = verify_db_unlocked()
    if not ok_db:
        print(f"launch_day_executor: db preflight failed: {msg_db}", file=sys.stderr)
        return 1

    write_launch_session(
        status="RUNNING",
        timestamp_utc=_utc_iso(),
        paused_reason="",
        dry_run=dry,
        prospects_sent=0,
        bounce_count=0,
    )

    batches = max(1, int(args.batches or 1))
    gap = max(0, int(args.inter_batch_seconds or 0))
    last_rc = 0
    for i in range(batches):
        if i:
            print(f"launch_day_executor: inter-batch sleep {gap}s ({i + 1}/{batches})")
            time.sleep(float(gap))
        print(f"launch_day_executor: run_daily batch {i + 1}/{batches} dry_run={dry}")
        last_rc = run_daily_subprocess(dry_run=dry)
        if last_rc != 0:
            write_launch_session(
                status="FAILED",
                timestamp_utc=_utc_iso(),
                paused_reason=f"run_daily_exit_{last_rc}",
            )
            return 2

    summary = load_run_report_summary()
    print(
        json.dumps(
            {"launch": "batch_complete", "summary": summary}, indent=2, default=str
        )
    )

    bounce_ratio = _bounce_ratio_from_db()
    thr = float(os.environ.get("LAUNCH_BOUNCE_EMERGENCY_RATIO", "0.05") or 0.05)
    sent = int((summary.get("money_path") or {}).get("sent") or 0)
    if not dry and bounce_ratio >= thr:
        write_launch_session(
            status="FAILED",
            timestamp_utc=_utc_iso(),
            prospects_sent=sent,
            bounce_ratio_after_run=bounce_ratio,
            paused_reason=f"bounce_ratio>={thr}",
        )
        print(
            f"launch_day_executor: bounce_ratio {bounce_ratio:.4f} >= emergency {thr}; marking FAILED.",
            file=sys.stderr,
        )
        return 2
    write_launch_session(
        status="COMPLETE",
        timestamp_utc=_utc_iso(),
        prospects_sent=sent,
        bounce_ratio_after_run=bounce_ratio,
        paused_reason="",
    )
    return 0


def cmd_emergency_pause(args: argparse.Namespace) -> int:
    reason = (args.pause_reason or "operator_emergency_pause").strip()
    write_launch_session(
        status="PAUSED",
        timestamp_utc=_utc_iso(),
        paused_reason=reason,
    )
    try:
        mcp = _REPO / "venture-mcp-server"
        if str(mcp) not in sys.path:
            sys.path.insert(0, str(mcp))
        from runtime_config import (
            resolve_data_base,
            resolve_venture_db_path,
        )  # noqa: PLC0415
        from job_queue import get_queue  # noqa: PLC0415

        db = str(resolve_venture_db_path(resolve_data_base(_REPO), _REPO))
        jq = get_queue(db_path=db)
        jq.log_block(
            "system",
            "launch_orchestrator",
            "operator_emergency_pause",
            details=reason,
            block_type="OPERATOR_PAUSE_BLOCK",
            severity="HARD",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"launch_day_executor: freeze failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "status": "PAUSED", "reason": reason}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Launch day orchestrator (run_daily wrapper)."
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--outbound-go",
        action="store_true",
        help="Run prospect generation + outbound via run_daily.py",
    )
    g.add_argument(
        "--emergency-pause",
        action="store_true",
        help="Hard freeze outreach + mark launch_session PAUSED",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="With --outbound-go: pass --dry-run to run_daily (no live Resend sends)",
    )
    p.add_argument(
        "--skip-checklist",
        action="store_true",
        help="Live only: skip OPERATOR_LAUNCH_READINESS.md checkbox enforcement (emergency)",
    )
    p.add_argument(
        "--pause-reason",
        default="operator_emergency_pause",
        help="With --emergency-pause: reason string stored in session + job_queue",
    )
    p.add_argument(
        "--batches",
        type=int,
        default=1,
        help="Repeat run_daily this many times (stagger with --inter-batch-seconds)",
    )
    p.add_argument(
        "--inter-batch-seconds",
        type=int,
        default=0,
        help="Sleep between batches (honor SEND_* caps inside each run_daily child)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.emergency_pause:
        return cmd_emergency_pause(args)
    if args.outbound_go:
        return cmd_outbound_go(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
