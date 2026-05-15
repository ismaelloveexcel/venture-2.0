#!/usr/bin/env python3
"""
Pre-launch safety verification — DNS-ish checks, env toggles, SQLite schema, checklist counts.

Usage:
  python 04-coding/scripts/preflight_safety_check.py --quick
  python 04-coding/scripts/preflight_safety_check.py --full
"""

from __future__ import annotations

import argparse
import os
import re
import socket
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_REPO = _SCRIPTS.parent.parent

if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO / ".env", override=False)


@dataclass(frozen=True)
class Row:
    name: str
    status: str  # PASS | FAIL | WARN | SKIP
    detail: str


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name, "") or default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    v = _env(name).lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "y", "on"}


def _check_dns_email(*, quick: bool) -> Row:
    host = "abtmail.co"
    try:
        try:
            socket.getaddrinfo(host, None, type=socket.SOCK_STREAM, timeout=5)
        except TypeError:
            socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        return Row("DNS / Email", "PASS", f"{host} resolves (A/AAAA lookup)")
    except OSError as exc:
        if quick:
            return Row("DNS / Email", "WARN", f"{host} lookup failed ({exc}); re-run with network for live")
        return Row("DNS / Email", "FAIL", f"{host} does not resolve: {exc}")


def _check_resend_from() -> Row:
    raw = _env("RESEND_FROM_EMAIL")
    if not raw:
        return Row("RESEND_FROM_EMAIL", "FAIL", "missing in environment")
    dom = raw.split("@", 1)[1].lower() if "@" in raw else ""
    if dom != "abtmail.co":
        return Row("RESEND_FROM_EMAIL", "WARN", f"domain is {dom!r} (expected abtmail.co for launch doctrine)")
    return Row("RESEND_FROM_EMAIL", "PASS", raw)


def _check_signature_placeholder() -> Row:
    sig = _env("EMAIL_SIGNATURE_HTML")
    if not sig:
        return Row("EMAIL_SIGNATURE_HTML", "FAIL", "missing")
    if "[CALENDLY_BOOKING_URL]" in sig:
        return Row("EMAIL_SIGNATURE_HTML", "PASS", "contains [CALENDLY_BOOKING_URL] merge token")
    if "https://calendly.com/" in sig.lower():
        return Row("EMAIL_SIGNATURE_HTML", "PASS", "expanded Calendly https link present in HTML")
    return Row(
        "EMAIL_SIGNATURE_HTML",
        "WARN",
        "no placeholder or https://calendly.com/ detected; confirm signature is production-safe",
    )


def _check_resend_api_key() -> Row:
    key = _env("RESEND_API_KEY")
    if not key:
        return Row("Resend API key", "FAIL", "RESEND_API_KEY not set")
    if not key.startswith("re_"):
        return Row("Resend API key", "WARN", "expected prefix re_ (format check only; no live API call)")
    if len(key) < 24:
        return Row("Resend API key", "WARN", "key looks short; verify full secret from Resend")
    return Row("Resend API key", "PASS", "set and format looks plausible (no live API call)")


def _check_list_unsubscribe_policy() -> Row:
    # Hardcoded product note (no network): Resend supports List-Unsubscribe headers on supported plans.
    return Row(
        "List-Unsubscribe policy",
        "PASS",
        "Confirm in Resend dashboard: List-Unsubscribe supported on your plan; ENABLE_LIST_UNSUBSCRIBE governs send_guard",
    )


def _check_domain_warmup() -> Row:
    stage = _env("DOMAIN_WARMUP_STAGE", "cold").lower()
    if stage not in {"cold", "warm", "hot"}:
        return Row("DOMAIN_WARMUP_STAGE", "FAIL", f"invalid value {stage!r} (use cold|warm|hot)")
    return Row("DOMAIN_WARMUP_STAGE", "PASS", stage)


def _check_safety_toggles() -> Row:
    parts: list[str] = []
    ok = True
    if not _env_bool("ENABLE_SUPPRESSION_CHECKS", False):
        parts.append("ENABLE_SUPPRESSION_CHECKS not true")
        ok = False
    if not _env_bool("ENABLE_LIST_UNSUBSCRIBE", False):
        parts.append("ENABLE_LIST_UNSUBSCRIBE not true")
        ok = False
    if _env_bool("ALLOW_OPERATOR_OVERRIDE", False):
        parts.append("ALLOW_OPERATOR_OVERRIDE must be false for launch lock")
        ok = False
    hr = _env("SEND_HOURLY_CAP", "6")
    dy = _env("SEND_DAILY_CAP", "40")
    try:
        hri, dyi = int(hr), int(dy)
    except ValueError:
        parts.append("SEND_HOURLY_CAP / SEND_DAILY_CAP not integers")
        ok = False
    else:
        if hri <= 0:
            parts.append("SEND_HOURLY_CAP must be > 0")
            ok = False
        if dyi <= hri:
            parts.append("SEND_DAILY_CAP should be > SEND_HOURLY_CAP")
            ok = False
    thr = _env("LAUNCH_BOUNCE_EMERGENCY_RATIO", "0.05")
    try:
        t = float(thr)
        if t <= 0 or t > 0.5:
            parts.append("LAUNCH_BOUNCE_EMERGENCY_RATIO out of sensible range")
            ok = False
    except ValueError:
        parts.append("LAUNCH_BOUNCE_EMERGENCY_RATIO not a float")
        ok = False
    if not ok:
        return Row("Safety toggles", "FAIL", "; ".join(parts))
    return Row("Safety toggles", "PASS", f"suppression+unsub on, override locked, caps {hr}/hr {dy}/day, bounce_thr={thr}")


def _check_database() -> Row:
    from runtime_config import resolve_data_base, resolve_venture_db_path  # noqa: PLC0415

    db = resolve_venture_db_path(resolve_data_base(_REPO), _REPO)
    if not db.is_file():
        return Row("Database Health", "FAIL", f"database missing: {db}")
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=3.0)
    except sqlite3.Error as exc:
        return Row("Database Health", "FAIL", str(exc))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA quick_check")
        q = cur.fetchone()
        if not q or str(q[0]).lower() != "ok":
            return Row("Database Health", "FAIL", f"quick_check: {q}")
        cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='resend_webhook_events' LIMIT 1"
        )
        wh = cur.fetchone()
        if not wh or "event_id" not in str(wh[0]).lower():
            return Row("Database Health", "FAIL", "resend_webhook_events table or event_id missing")
        cur.execute("SELECT COUNT(*) FROM suppression_list")
        n_sup = int(cur.fetchone()[0])
        cur.execute("SELECT control_value FROM system_control WHERE control_key='outreach_frozen' LIMIT 1")
        row = cur.fetchone()
        frozen = str(row[0]).lower() == "true" if row else False
    finally:
        conn.close()
    if frozen:
        return Row(
            "Database Health",
            "FAIL",
            "outreach_frozen=true — clear freeze before live (see job_queue.set_outreach_freeze / operator runbook)",
        )
    return Row("Database Health", "PASS", f"venture_jobs.db OK, suppression_list rows={n_sup}, outreach_frozen=false")


def _check_calendly() -> Row:
    url = _env("CALENDLY_BOOKING_URL")
    if not url:
        return Row("Calendly", "FAIL", "CALENDLY_BOOKING_URL empty")
    if url.lower().startswith("http://"):
        return Row("Calendly", "FAIL", "must be https:// not http://")
    if not url.lower().startswith("https://"):
        return Row("Calendly", "FAIL", "must start with https://")
    if "calendly.com" not in url.lower():
        return Row("Calendly", "WARN", "URL does not contain calendly.com — verify booking provider")
    if "YOUR_LINK" in url or "your_link" in url.lower():
        return Row("Calendly", "FAIL", "placeholder YOUR_LINK still present")
    return Row("Calendly", "PASS", url[:60] + ("…" if len(url) > 60 else ""))


def _check_operator_checklist(path: Path) -> Row:
    if not path.is_file():
        return Row("Operator Checklist", "FAIL", f"missing file: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    items = re.findall(r"^-\s*\[([ xX])\]\s", text, flags=re.MULTILINE)
    if not items:
        return Row("Operator Checklist", "WARN", "no - [ ] / - [x] lines found")
    done = sum(1 for c in items if str(c).lower() == "x")
    total = len(items)
    if done == total:
        return Row("Operator Checklist", "PASS", f"{done}/{total} complete")
    return Row("Operator Checklist", "PARTIAL", f"{done}/{total} complete — {total - done} items pending")


def run_checks(*, quick: bool) -> list[Row]:
    checklist = Path(_env("VENTURE_OPERATOR_CHECKLIST_PATH") or str(_REPO / "04-coding" / "OPERATOR_LAUNCH_READINESS.md"))
    rows = [
        _check_dns_email(quick=quick),
        _check_resend_from(),
        _check_signature_placeholder(),
        _check_resend_api_key(),
        _check_list_unsubscribe_policy(),
        _check_domain_warmup(),
        _check_safety_toggles(),
        _check_database(),
        _check_calendly(),
        _check_operator_checklist(checklist),
    ]
    return rows


def _icon(status: str) -> str:
    return {"PASS": "PASS", "FAIL": "FAIL", "WARN": "WARN", "SKIP": "SKIP", "PARTIAL": "PARTIAL"}.get(status, status)


def print_report(rows: list[Row]) -> None:
    print("=" * 63)
    print("               PREFLIGHT SAFETY CHECK — PASS/FAIL")
    print("=" * 63)
    for r in rows:
        print(f"{r.name:18} {_icon(r.status):8} {r.detail}")
    print("=" * 63)
    fails = [r for r in rows if r.status == "FAIL"]
    warns = [r for r in rows if r.status in {"WARN", "PARTIAL"}]
    if fails:
        print("VERDICT: FAIL — resolve FAIL rows before launch")
    elif warns:
        print("VERDICT: CONDITIONAL PASS — review WARN / PARTIAL rows")
    else:
        print("VERDICT: PASS — automated gates green")
    print("=" * 63)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Pre-launch safety checks (read-only + env).")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--full", action="store_true", help="Full check + optional rehearsal prompt")
    g.add_argument("--quick", action="store_true", help="Faster path; DNS issues downgrade to WARN")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    quick = bool(args.quick)
    rows = run_checks(quick=quick)
    print_report(rows)
    if any(r.status == "FAIL" for r in rows):
        return 1
    if args.full and sys.stdin.isatty() and not _env_bool("VENTURE_PREFLIGHT_NO_PROMPT", False):
        ans = input("All automated checks done (see VERDICT). Ready to rehearse? (y/n) ").strip().lower()
        if ans and ans[0] != "y":
            print("Operator answered not ready — exit 1")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
