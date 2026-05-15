#!/usr/bin/env python3
"""
Replay rows from webhook_dlq into the same processor used by the Resend webhook handler.

Default is dry-run (no DB writes except none). Use --execute to apply and remove rows on success.

Examples:
  python 04-coding/scripts/dlq_replay.py
  python 04-coding/scripts/dlq_replay.py --limit 10
  python 04-coding/scripts/dlq_replay.py --id 3 --id 4 --execute
  python 04-coding/scripts/dlq_replay.py --db "C:/path/venture_jobs.db" --execute
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
VENTURE_SERVER = REPO / "venture-mcp-server"
SCRIPTS = REPO / "04-coding" / "scripts"

sys.path.insert(0, str(VENTURE_SERVER))
sys.path.insert(0, str(SCRIPTS))

from job_queue import JobQueue  # noqa: E402


def _parse_payload(raw: str) -> tuple[dict | None, str | None]:
    if not (raw or "").strip():
        return None, "empty payload"
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"invalid json: {e}"
    if not isinstance(obj, dict):
        return None, "payload is not a JSON object"
    return obj, None


def main() -> int:
    default_db = REPO / "venture_jobs.db"
    p = argparse.ArgumentParser(description="Replay webhook_dlq rows (dry-run unless --execute).")
    p.add_argument("--db", type=pathlib.Path, default=default_db, help="Path to venture_jobs.db")
    p.add_argument("--limit", type=int, default=50, help="Max rows when not using --id")
    p.add_argument("--offset", type=int, default=0, help="Skip N oldest rows")
    p.add_argument("--id", type=int, action="append", dest="ids", help="Specific DLQ id (repeatable)")
    p.add_argument(
        "--execute",
        action="store_true",
        help="Call process_resend_event and DELETE row on success (ok=true)",
    )
    args = p.parse_args()

    db_path = args.db.resolve()
    if not db_path.is_file():
        print(f"[error] database not found: {db_path}", file=sys.stderr)
        return 2

    jq = JobQueue(str(db_path))
    from resend_webhook_handler import process_resend_event  # noqa: E402

    ids = args.ids
    rows = jq.list_webhook_dlq(limit=args.limit, offset=args.offset, ids=ids)
    if not rows:
        print("(no DLQ rows)")
        return 0

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"{mode}  db={db_path}  rows={len(rows)}\n")

    dry_count = 0
    ok_count = 0
    skip_count = 0
    fail_count = 0

    for row in rows:
        rid = int(row["id"])
        source = row.get("source", "")
        raw = row.get("payload") or ""
        payload, perr = _parse_payload(raw)
        if payload is None:
            print(f"[skip] id={rid} source={source}  {perr}")
            skip_count += 1
            continue

        if not args.execute:
            ev = str(payload.get("type", ""))
            print(f"[dry-run] id={rid} source={source} type={ev!r}")
            dry_count += 1
            continue

        result = process_resend_event(payload, db_path=str(db_path))
        if result.get("ok") is True:
            if jq.delete_webhook_dlq(rid):
                print(f"[ok] id={rid} replayed and removed from DLQ  {result}")
            else:
                print(f"[warn] id={rid} replayed but DELETE returned 0 rows  {result}")
            ok_count += 1
        else:
            print(f"[fail] id={rid} left in DLQ  {result}")
            fail_count += 1

    if args.execute:
        print(f"\nSummary: replayed_ok={ok_count} skip={skip_count} fail={fail_count}")
    else:
        print(f"\nSummary: dry_run_rows={dry_count} skip={skip_count}  (no writes; pass --execute to apply)")
    if args.execute and fail_count:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
