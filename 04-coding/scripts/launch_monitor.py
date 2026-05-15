#!/usr/bin/env python3
"""
Launch window TTY monitor — reads run_report.json + venture_jobs.db, refreshes on an interval.

No HTTP server; plain text for Windows PowerShell and POSIX terminals.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_REPO = _SCRIPTS.parent.parent

if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def _repo() -> Path:
    return _REPO


def _db_path() -> Path:
    from runtime_config import resolve_data_base, resolve_venture_db_path  # noqa: PLC0415

    return resolve_venture_db_path(resolve_data_base(_REPO), _REPO)


def _run_report_path() -> Path:
    from run_report_writer import resolve_run_report_path  # noqa: PLC0415

    return resolve_run_report_path(_REPO, client_id=os.environ.get("VENTURE_CLIENT_ID"), explicit=None)


def _load_run_report() -> dict:
    p = _run_report_path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _load_launch_session() -> dict:
    raw = (os.environ.get("VENTURE_LAUNCH_SESSION_PATH") or "").strip()
    p = Path(raw).expanduser().resolve() if raw else _repo() / "04-coding" / "state" / "launch_session.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _sql_counts(db: Path) -> dict:
    out: dict[str, object] = {
        "bounce_24h": 0,
        "complaint_24h": 0,
        "delay_7d": 0,
        "unsub_7d": 0,
        "block_severity": Counter(),
    }
    if not db.is_file():
        return out
    cutoff24 = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
    cutoff7 = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error:
        return out
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) FROM resend_webhook_events
            WHERE created_at >= ? AND lower(event_type) LIKE '%bounc%'
            """,
            [cutoff24],
        )
        out["bounce_24h"] = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT COUNT(*) FROM resend_webhook_events
            WHERE created_at >= ? AND lower(event_type) LIKE '%complain%'
            """,
            [cutoff24],
        )
        out["complaint_24h"] = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT COUNT(*) FROM resend_webhook_events
            WHERE created_at >= ? AND lower(event_type) LIKE '%delay%'
            """,
            [cutoff7],
        )
        out["delay_7d"] = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT COUNT(*) FROM resend_webhook_events
            WHERE created_at >= ? AND lower(event_type) LIKE '%unsub%'
            """,
            [cutoff7],
        )
        out["unsub_7d"] = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT severity, COUNT(*) FROM block_logs WHERE created_at >= ?
            GROUP BY severity
            """,
            [cutoff7],
        )
        for sev, n in cur.fetchall():
            out["block_severity"][str(sev or "UNKNOWN").upper()] = int(n)
    finally:
        conn.close()
    return out


def _snapshot_totals(rr: dict) -> tuple[int, int, int]:
    snaps = ((rr.get("outbound") or {}).get("funnel_health_snapshots")) or []
    if not isinstance(snaps, list):
        return (0, 0, 0)
    gen = sent = blk = 0
    for s in snaps:
        if not isinstance(s, dict):
            continue
        gen += int(s.get("qualified") or 0)
        sent += int(s.get("sent") or 0)
        blk += int(s.get("blocked") or 0)
    return (gen, sent, blk)


def _bounce_ratio_rolling(db: Path, days: int = 7) -> tuple[float, float, int]:
    if not db.is_file():
        return (0.0, 0.0, 0)
    try:
        mcp = _repo() / "venture-mcp-server"
        if str(mcp) not in sys.path:
            sys.path.insert(0, str(mcp))
        from job_queue import JobQueue  # noqa: PLC0415

        m = JobQueue(str(db)).get_delivery_ratio_metrics(days)
        return (
            float(m.get("bounce_ratio") or 0.0),
            float(m.get("complaint_ratio") or 0.0),
            int(m.get("sent") or 0),
        )
    except Exception:
        return (0.0, 0.0, 0)


def _deadline_line() -> str:
    # Launch hard stop: May 18, 2026 end of local calendar day (naive local clock).
    deadline = datetime(2026, 5, 18, 23, 59, 59)
    now = datetime.now()
    if now > deadline:
        return "Deadline: PASSED (May 18, 2026 11:59 PM)"
    delta = deadline - now
    days, rem = divmod(int(delta.total_seconds()), 86400)
    hrs, rem2 = divmod(rem, 3600)
    mins, _ = divmod(rem2, 60)
    return f"Deadline: May 18, 2026 11:59 PM local ({days}d {hrs}h {mins}m remaining)"


def render_frame(interval: int) -> str:
    rr = _load_run_report()
    sess = _load_launch_session()
    db = _db_path()
    sql = _sql_counts(db)
    br, cr, sent_roll = _bounce_ratio_rolling(db, int(os.environ.get("VENTURE_DELIVERY_METRICS_DAYS", "7") or 7))
    gen, sent_snap, blk_snap = _snapshot_totals(rr)
    ob = rr.get("outbound") or {}
    mp = ob.get("money_path") or {}
    thr_b = float(os.environ.get("LAUNCH_MONITOR_BOUNCE_OK_PCT", "5") or 5)
    thr_c = float(os.environ.get("LAUNCH_MONITOR_COMPLAINT_OK_PCT", "0.3") or 0.3)
    b_pct = br * 100.0
    c_pct = cr * 100.0
    b_tag = "OK" if b_pct < thr_b else "WARN"
    c_tag = "OK" if c_pct < thr_c else "WARN"
    bs: Counter[str] = sql["block_severity"]  # type: ignore[assignment]
    hard = int(bs.get("HARD", 0))
    soft = int(bs.get("SOFT", 0))
    info = int(bs.get("INFO", 0))
    lines = [
        "=" * 63,
        " LAUNCH MONITOR — May 13–18, 2026",
        "=" * 63,
        _deadline_line(),
        f"Last session:     status={sess.get('status', 'N/A')} updated={sess.get('updated_at_utc', sess.get('timestamp_utc', 'N/A'))}",
        f"Run report:       {_run_report_path()}",
        "-" * 63,
        "OUTBOUND (run_report funnel_health_snapshots, cumulative)",
        "-" * 63,
        f"Qualified (sum):  {gen}",
        f"Sent (sum):       {sent_snap}",
        f"Blocked (sum):    {blk_snap}",
        f"Money path (last): attempted={mp.get('attempted', 0)} sent={mp.get('sent', 0)} blocked={mp.get('blocked', 0)}",
        "-" * 63,
        "HEALTH (rolling DB)",
        "-" * 63,
        f"Bounce ratio ({sent_roll} sends / {os.environ.get('VENTURE_DELIVERY_METRICS_DAYS', '7')}d window): {b_pct:.2f}% [{b_tag}] guide<{thr_b}%",
        f"Complaint ratio:  {c_pct:.3f}% [{c_tag}] guide<{thr_c}%",
        f"Webhook bounces (24h): {sql['bounce_24h']}",
        f"Webhook complaints (24h): {sql['complaint_24h']}",
        f"Delivery delayed (7d): {sql['delay_7d']}",
        f"Unsubscribe-like events (7d): {sql['unsub_7d']}",
        f"Block logs (7d):    HARD={hard} SOFT={soft} INFO={info}",
        "-" * 63,
        "NEXT ACTIONS",
        "-" * 63,
        "• If bounce WARN: run launch_day_executor.py --emergency-pause then inspect copy + DNS.",
        "• If open rate low after 24h: tighten subject / first line (see cohort lock).",
        "• Rehearse: launch_day_executor.py --outbound-go --dry-run",
        "-" * 63,
        f"Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | interval={interval}s | Ctrl+C exit",
    ]
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="TTY launch monitor (run_report + SQLite).")
    p.add_argument(
        "--live",
        action="store_true",
        help="Refresh until Ctrl+C",
    )
    p.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Seconds between refreshes (default 10)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.live:
        print(render_frame(args.interval), end="")
        return 0
    try:
        while True:
            # Two newlines between frames for readability in PowerShell.
            print("\n" + render_frame(args.interval), end="", flush=True)
            time.sleep(max(1, int(args.interval)))
    except KeyboardInterrupt:
        print("\nlaunch_monitor: stopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
