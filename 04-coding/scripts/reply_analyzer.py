#!/usr/bin/env python3
"""
Reply funnel snapshot — May 19+ daily ops.

Reads funnel/lifecycle signals from SQLite and run_report.json, exports a simple CSV.
Does not call external APIs. Heuristic categories only (not legal advice).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_REPO = _SCRIPTS.parent.parent

if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def _db_path() -> Path:
    from runtime_config import resolve_data_base, resolve_venture_db_path  # noqa: PLC0415

    return resolve_venture_db_path(resolve_data_base(_REPO), _REPO)


def _run_report_path() -> Path:
    from run_report_writer import resolve_run_report_path  # noqa: PLC0415

    return resolve_run_report_path(_REPO, client_id=os.environ.get("VENTURE_CLIENT_ID"), explicit=None)


def _categorize(text: str) -> str:
    t = (text or "").lower()
    if re.search(r"\b(scheduled|booked|calendly)\b", t):
        return "BOOKED"
    if re.search(r"\b(yes|interested|tell me more|sounds good)\b", t):
        return "INTERESTED"
    if re.search(r"\b(budget|expensive|price|cost)\b", t):
        return "PRICE_SENSITIVE"
    if re.search(r"\b(already|using|vendor|competitor)\b", t):
        return "ALREADY_USING"
    if re.search(r"\b(not interested|no thanks|unsubscribe|stop)\b", t):
        return "NOT_INTERESTED"
    return "OTHER"


def fetch_reply_rows(since_hours: int) -> list[dict]:
    db = _db_path()
    if not db.is_file():
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(1, since_hours))).isoformat()
    rows: list[dict] = []
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=3.0)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT prospect_id, stage, metadata, created_at
            FROM funnel_events
            WHERE stage IN ('replied', 'email.replied')
              AND created_at >= ?
            ORDER BY created_at ASC
            """,
            [cutoff],
        )
        for pid, stage, meta, ts in cur.fetchall():
            try:
                md = json.loads(meta or "{}")
            except json.JSONDecodeError:
                md = {}
            blob = json.dumps(md, ensure_ascii=False)
            cat = _categorize(blob)
            rows.append(
                {
                    "timestamp_utc": str(ts),
                    "prospect_id": str(pid or ""),
                    "stage": str(stage or ""),
                    "reply_signal": blob[:2000],
                    "pain_category": cat,
                    "booked_calendly": "yes" if cat == "BOOKED" else "no",
                    "paid_status": "unknown",
                }
            )
        cur.execute(
            """
            SELECT payload, created_at FROM lifecycle_events
            WHERE event_type = 'replied'
              AND created_at >= ?
            ORDER BY created_at ASC
            """,
            [cutoff],
        )
        for payload, ts in cur.fetchall():
            blob = str(payload or "")
            cat = _categorize(blob)
            rows.append(
                {
                    "timestamp_utc": str(ts),
                    "prospect_id": "",
                    "stage": "lifecycle_replied",
                    "reply_signal": blob[:2000],
                    "pain_category": cat,
                    "booked_calendly": "yes" if cat == "BOOKED" else "no",
                    "paid_status": "unknown",
                }
            )
    finally:
        conn.close()
    return rows


def summarize(rows: list[dict], since_hours: int) -> dict:
    rr_path = _run_report_path()
    snap_sent = 0
    if rr_path.is_file():
        try:
            data = json.loads(rr_path.read_text(encoding="utf-8"))
            snaps = ((data.get("outbound") or {}).get("funnel_health_snapshots")) or []
            if isinstance(snaps, list):
                snap_sent = sum(int(s.get("sent") or 0) for s in snaps if isinstance(s, dict))
        except (OSError, json.JSONDecodeError):
            pass
    cats = Counter(r["pain_category"] for r in rows)
    return {
        "since_hours": since_hours,
        "reply_rows": len(rows),
        "categories": dict(cats.most_common(10)),
        "run_report_snapshots_sent_sum": snap_sent,
        "run_report_path": str(rr_path),
    }


def export_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "timestamp_utc",
        "prospect_id",
        "stage",
        "reply_signal",
        "pain_category",
        "booked_calendly",
        "paid_status",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Reply / conversion snapshot export (SQLite + run_report).")
    p.add_argument("--since-hours", type=int, default=24, help="Rolling window (default 24)")
    p.add_argument(
        "--export-csv",
        type=Path,
        default=None,
        help="Write CSV to this path (default: 07-kpis/replies_export.csv under data root)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    hours = max(1, int(args.since_hours))
    rows = fetch_reply_rows(hours)
    summary = summarize(rows, hours)
    print(json.dumps({"summary": summary}, indent=2, default=str))
    out = args.export_csv
    if out is None:
        from runtime_config import resolve_data_base  # noqa: PLC0415

        out = resolve_data_base(_REPO) / "07-kpis" / "replies_export.csv"
    export_csv(out, rows)
    print(f"wrote_csv={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
