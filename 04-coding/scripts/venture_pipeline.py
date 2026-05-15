"""
Venture OS — pipeline module (legacy / diagnostic)

**Production-style runs:** `python 04-coding/scripts/run_daily.py` per `AGENTS.md`
and `docs/SEMANTIC_CONTRACT.md` §8.1 — this file is **not** the default human entrypoint.

**This module's `__main__`:** gated on `VENTURE_DEV_MAIN=1` (local dev only), except
`venture_pipeline.py --status` (read-only, no env). Do not train operators to "just
run venture_pipeline" for live sends.

Chains (when invoked for dev): Prospect Discovery → Email Lookup → Outreach Generation → Notion Sync → Airtable Sync → KPI Update

Requires: pip install openai httpx python-dotenv

What it does automatically:
  1. Reads prospects.csv for pending prospects
  2. Looks up email addresses via Hunter.io (if API key set)
  3. Generates personalised outreach for each prospect via OpenAI
  4. Saves ready-to-send messages to generated-outreach.csv
  5. Syncs prospects + outreach to Notion (primary CRM)
  6. Syncs prospects + outreach to Airtable (if API key set)
  7. Syncs latest KPI week to Notion automatically
  8. Prints a weekly progress summary
  9. Auto-sends emails via Resend (if AUTO_SEND_EMAILS=true + RESEND_FROM_EMAIL set)
 10. Follow-ups from SQLite (outbound_events + funnel); min wait max(FOLLOWUP_DAYS, compliance cooldown)
 11. Emails you a KPI digest after every run (if DIGEST_TO_EMAIL set)
"""

import os
import csv
import json
import pathlib
import sqlite3
import sys
import re
from collections import defaultdict
from functools import lru_cache
from datetime import date, datetime, timezone
import logging

import httpx
from dotenv import load_dotenv
from runtime_config import (
    RuntimeConfig,
    collect_config_warnings,
    collect_live_mode_blockers,
    resolve_data_base,
    resolve_venture_db_path,
)
from batch_guard import (
    BatchGuardError,
    LockIntegrityError,
    consume_batch_lock,
    make_run_id,
    run_batch_preflight,
)
from send_guard import materialize_outbound_payload, send_email_safe
from compliance_policy import (
    describe_compliance_policy_line,
    evaluate_compliance_cooldown_for_run,
    get_compliance_cooldown_days_for_send,
    reset_compliance_cooldown_policy_for_run,
)
from system_integrity_monitor import evaluate_integrity
from outreach_state_machine import proposal_depth_for_state
from cta_router import choose_cta
from qualification_guard import evaluate_qualification
from execution_firewall import final_send_check
from no_response_diagnostics import analyze_no_response_patterns
from outbound_eligibility import (
    OutboundEligibilityAuditError,
    canonical_execution_run_id,
    emit_no_eligible_prospects_event,
    filter_prospects_for_outbound_send,
)
from prospect_gate import normalize_email

# Resilience & logging
sys.path.insert(
    0, str(pathlib.Path(__file__).parent.parent.parent / "venture-mcp-server")
)
from resilience import (
    hunter_api_call,
    openai_api_call,
    notion_api_call,
    airtable_api_call,
)
from logging_config import setup_logging
from message_generator_solo import strip_outreach_signature
from job_queue import get_queue, JobAction, JobStatus
from lifecycle_engine import LifecycleEventType
from reply_intent import build_feature_dict, predict_reply_probability

# ── CLI flags ─────────────────────────────────────────────────────────────────
DRY_RUN = "--dry-run" in sys.argv  # print actions without sending emails or syncing

BASE = pathlib.Path(__file__).parent.parent.parent


def _runtime_path(env_key: str, default: pathlib.Path) -> pathlib.Path:
    value = os.environ.get(env_key, "").strip()
    return pathlib.Path(value).expanduser().resolve() if value else default


CLIENT_WORKSPACE = os.environ.get("VENTURE_CLIENT_WORKSPACE", "").strip()
DATA_BASE = resolve_data_base(BASE)
DOTENV_PATH = _runtime_path("VENTURE_DOTENV_PATH", DATA_BASE / ".env")
load_dotenv(DOTENV_PATH)

# Setup logging to file + console
logger = setup_logging(
    log_dir=str(_runtime_path("VENTURE_LOG_DIR", DATA_BASE / "logs")),
    name="venture-pipeline",
)
DB_PATH = _runtime_path("VENTURE_DB_PATH", resolve_venture_db_path(DATA_BASE, BASE))
job_queue = get_queue(db_path=str(DB_PATH))

logger.info("=" * 80)
logger.info(f"Pipeline started (dry_run={DRY_RUN})")

BATCH_RUN_ID = os.environ.get("BATCH_RUN_ID", "").strip() or make_run_id("pipeline")

_SEND_LOG_HEADER = "timestamp_utc,run_id,send_attempt_id,email,company,cohort_id,message_version,message_hash,send_status"


def _send_log_path() -> pathlib.Path:
    root = DATA_BASE if CLIENT_WORKSPACE else BASE
    return root / "logs" / "send_log.csv"


def _append_send_log_row(
    *,
    email: str,
    company: str,
    subject: str,
    html_body: str,
    send_attempt_id: str,
) -> None:
    """Single writer for logs/send_log.csv (v1.4); no-op if cohort env not set."""
    cohort_id = os.environ.get("VENTURE_COHORT_ID", "").strip()
    if not cohort_id or not send_attempt_id:
        return
    run_key = os.environ.get("VENTURE_RUN_ID", "").strip() or BATCH_RUN_ID
    msg_ver = os.environ.get("VENTURE_MESSAGE_VERSION", "").strip() or "unknown"
    msg_hash = job_queue.message_hash(subject, html_body)
    path = _send_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(_SEND_LOG_HEADER + "\n", encoding="utf-8")
    else:
        first = path.read_text(encoding="utf-8").splitlines()[:1]
        if not first or first[0].strip() != _SEND_LOG_HEADER:
            logger.warning("send_log.csv header mismatch; skipping append")
            return
    needle = f",{run_key},{send_attempt_id},"
    if needle in path.read_text(encoding="utf-8"):
        return
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    send_status = "dry_run" if DRY_RUN else "sent"
    with path.open("a", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow(
            [
                ts,
                run_key,
                send_attempt_id,
                email,
                company or "",
                cohort_id,
                msg_ver,
                msg_hash,
                send_status,
            ]
        )
        fh.flush()


def _safe_messages_log_stem(cohort_id: str) -> str:
    """Filesystem-safe stem for logs/messages/{stem}.txt (Windows-safe)."""
    cid = (cohort_id or "").strip()
    if not cid:
        return ""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)[:200]


def _write_cohort_message_snapshot_once(subject: str, html_body: str) -> None:
    """Write-once cohort message text for audit (first successful send path in a run)."""
    cohort_id = os.environ.get("VENTURE_COHORT_ID", "").strip()
    stem = _safe_messages_log_stem(cohort_id)
    if not stem or not (subject or "").strip():
        return
    root = DATA_BASE if CLIENT_WORKSPACE else BASE
    out_dir = root / "logs" / "messages"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stem}.txt"
    if path.is_file():
        return
    plain = re.sub(r"<[^>]+>", " ", html_body or "")
    plain = " ".join(plain.split())
    path.write_text(
        f"subject: {subject.strip()}\n\nbody_text:\n{plain}\n",
        encoding="utf-8",
    )


PROSPECTS_FILE = _runtime_path(
    "VENTURE_PROSPECTS_FILE",
    (
        DATA_BASE / "prospects.csv"
        if CLIENT_WORKSPACE
        else BASE / "06-sales" / "prospects.csv"
    ),
)
OUTPUT_FILE = _runtime_path(
    "VENTURE_OUTPUT_FILE",
    (
        DATA_BASE / "generated-outreach.csv"
        if CLIENT_WORKSPACE
        else BASE / "06-sales" / "generated-outreach.csv"
    ),
)
KPI_FILE = _runtime_path(
    "VENTURE_KPI_FILE",
    (
        DATA_BASE / "weekly-kpi-data.csv"
        if CLIENT_WORKSPACE
        else BASE / "07-kpis" / "weekly-kpi-data.csv"
    ),
)
CONFIG_FILE = _runtime_path(
    "VENTURE_OUTREACH_CONFIG",
    (
        DATA_BASE / "outreach_config.json"
        if CLIENT_WORKSPACE
        else pathlib.Path(__file__).parent / "outreach_config.json"
    ),
)

CFG = RuntimeConfig.from_env()
OPENAI_API_KEY = CFG.openai_api_key
HUNTER_API_KEY = CFG.hunter_api_key
AIRTABLE_API_KEY = CFG.airtable_api_key
AIRTABLE_BASE_ID = CFG.airtable_base_id
AIRTABLE_PROSPECTS_TABLE = CFG.airtable_prospects_table
AIRTABLE_KPIS_TABLE = CFG.airtable_kpis_table
NOTION_API_KEY = CFG.notion_api_key
NOTION_PROSPECTS_DB = CFG.notion_prospects_db
NOTION_KPIS_DB = CFG.notion_kpis_db
RESEND_API_KEY = CFG.resend_api_key
RESEND_FROM_EMAIL = CFG.resend_from_email
RESEND_FROM_NAME = CFG.resend_from_name
DIGEST_TO_EMAIL = CFG.digest_to_email
AUTO_SEND_EMAILS = CFG.auto_send_emails
FOLLOWUP_DAYS = CFG.followup_days
ENABLE_FOLLOWUPS = os.environ.get("ENABLE_FOLLOWUPS", "false").strip().lower() == "true"
ENABLE_SEND_EMAIL_RETRIES = (
    os.environ.get("ENABLE_SEND_EMAIL_RETRIES", "false").strip().lower() == "true"
)
REVENUE_TARGET = CFG.revenue_target
SEND_DAILY_CAP = int(os.environ.get("SEND_DAILY_CAP", "40"))
SEND_HOURLY_CAP = int(os.environ.get("SEND_HOURLY_CAP", "12"))
SEND_START_HOUR = int(os.environ.get("SEND_START_HOUR", "8"))
SEND_END_HOUR = int(os.environ.get("SEND_END_HOUR", "18"))
ACTIVE_CLIENT_CAPACITY = int(os.environ.get("ACTIVE_CLIENT_CAPACITY", "6"))
ACTIVE_CLIENTS_CURRENT = int(os.environ.get("ACTIVE_CLIENTS_CURRENT", "0"))
REPLY_INTENT_ENABLED = CFG.reply_intent_enabled
REPLY_INTENT_MIN_PROB = CFG.reply_intent_min_prob
REPLY_INTENT_VOLUME_THRESHOLD = CFG.reply_intent_volume_threshold
HARD_FAIL_ON_PROVIDER_AUTH = (
    os.environ.get("VENTURE_HARD_FAIL_PROVIDER_AUTH", "true").strip().lower() == "true"
)
HARD_FAIL_ON_GENERATION_ERROR = (
    os.environ.get("VENTURE_HARD_FAIL_ON_GENERATION_ERROR", "true").strip().lower()
    == "true"
)
MIN_MESSAGE_CHARS = int(os.environ.get("VENTURE_MIN_MESSAGE_CHARS", "80"))

# Import Notion helper from sibling directory
import sys as _sys

_sys.path.insert(
    0, str(pathlib.Path(__file__).parent.parent.parent / "venture-mcp-server")
)
from notion_helper import sync_prospect as _notion_prospect, sync_kpi as _notion_kpi

PROSPECT_FIELDS = [
    "name",
    "company",
    "role",
    "industry",
    "pain_point",
    "linkedin_url",
    "email",
    "domain",
    "status",
]


def _is_likely_notion_id(value: str) -> bool:
    """Validate Notion DB ID shape (32 hex chars, optionally hyphenated)."""
    if not value:
        return False
    normalized = value.replace("-", "")
    return len(normalized) == 32 and all(
        ch in "0123456789abcdefABCDEF" for ch in normalized
    )


def validate_integrations() -> None:
    """Log integration misconfigurations early so failures are easier to diagnose."""
    for warning in collect_config_warnings(CFG):
        logger.warning(warning)
        print(f"[warn] {warning}")


def enforce_live_mode_readiness() -> None:
    """Block live mode when critical configuration is missing or malformed."""
    if DRY_RUN:
        return

    blockers = collect_live_mode_blockers(CFG)
    if blockers:
        print("\n[fail] Live mode blocked due to configuration issues:")
        for issue in blockers:
            print(f"  - {issue}")
        print("\nRun preflight and resolve these blockers before a live run.")
        raise SystemExit(2)


def validate_live_mode_integrations() -> None:
    """Run low-cost integration probes before any live side effects."""
    if DRY_RUN:
        return
    failures: list[str] = []
    with httpx.Client(timeout=10) as client:
        try:
            r = client.post(
                f"https://api.notion.com/v1/databases/{NOTION_PROSPECTS_DB}/query",
                headers={
                    "Authorization": f"Bearer {NOTION_API_KEY}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json",
                },
                json={"page_size": 1},
            )
            if r.status_code >= 400:
                failures.append(f"Notion prospects probe failed ({r.status_code})")
        except Exception as exc:
            failures.append(f"Notion prospects probe error: {exc}")

    if failures:
        print("\n[fail] Live mode blocked by integration probes:")
        for issue in failures:
            print(f"  - {issue}")
        raise SystemExit(3)


def enforce_provider_auth_readiness() -> None:
    """Hard-stop live runs when OpenAI/Hunter credentials are missing or unauthorized."""
    if DRY_RUN:
        return
    if not HARD_FAIL_ON_PROVIDER_AUTH:
        return

    failures: list[str] = []
    with httpx.Client(timeout=10) as client:
        if not OPENAI_API_KEY:
            failures.append("OPENAI_API_KEY missing")
        else:
            try:
                r = client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                )
                if r.status_code >= 400:
                    failures.append(f"OpenAI auth probe failed ({r.status_code})")
            except Exception as exc:
                failures.append(f"OpenAI auth probe error: {exc}")

        if not HUNTER_API_KEY:
            failures.append("HUNTER_API_KEY missing")
        else:
            try:
                r = client.get(
                    "https://api.hunter.io/v2/account",
                    params={"api_key": HUNTER_API_KEY},
                )
                if r.status_code >= 400:
                    failures.append(f"Hunter auth probe failed ({r.status_code})")
            except Exception as exc:
                failures.append(f"Hunter auth probe error: {exc}")

    if failures:
        print("\n[fail] Provider auth hard-stop:")
        for issue in failures:
            print(f"  - {issue}")
        print(
            "\nFix keys in .env before continuing. Set VENTURE_HARD_FAIL_PROVIDER_AUTH=false only for intentional local debugging."
        )
        raise SystemExit(7)


def sanitize_csv_cell(value):
    """Prevent CSV injection in spreadsheet tools by neutralizing formula prefixes."""
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in ("=", "+", "-", "@"):
        return "'" + text
    return text


def sanitize_csv_row(row: dict) -> dict:
    """Return a CSV-safe row copy."""
    return {k: sanitize_csv_cell(v) for k, v in row.items()}


COMPLIANCE_CONFIG_PATH = (
    BASE / "04-coding" / "venture-engine" / "config" / "compliance.config.json"
)
OFFER_CONFIG_PATH = (
    BASE / "04-coding" / "venture-engine" / "config" / "offer.config.json"
)
SCORING_CONFIG_PATH = (
    BASE / "04-coding" / "venture-engine" / "config" / "scoring.config.json"
)


def load_compliance_require_unsubscribe() -> bool:
    try:
        with open(COMPLIANCE_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return bool(
            data.get("channels", {}).get("email", {}).get("require_unsubscribe", False)
        )
    except Exception:
        return False


def _read_json_object(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("Failed to parse config %s: %s", path, e)
        return {}


@lru_cache(maxsize=1)
def _qualification_defaults() -> dict:
    offer_cfg = _read_json_object(OFFER_CONFIG_PATH)
    scoring_cfg = _read_json_object(SCORING_CONFIG_PATH)

    qualification_cfg = offer_cfg.get("qualification", {})
    viability_cfg = scoring_cfg.get("viability", {})

    setup_price = float(offer_cfg.get("setup_price", 0) or 0)
    monthly_price = float(offer_cfg.get("monthly_price", 0) or 0)
    fallback_estimated_value = setup_price + monthly_price

    estimated_value = float(
        qualification_cfg.get("estimated_value") or fallback_estimated_value or 1500.0
    )
    min_viable_deal = float(
        qualification_cfg.get("min_viable_deal")
        or (setup_price * 0.5 if setup_price > 0 else 0)
        or 1000.0
    )
    implementation_days = int(
        qualification_cfg.get("implementation_days")
        or offer_cfg.get("delivery_days")
        or 14
    )
    max_delivery_days = int(
        qualification_cfg.get("max_delivery_days")
        or viability_cfg.get("max_delivery_days")
        or implementation_days
    )
    min_evidence_confidence = float(viability_cfg.get("min_evidence_confidence") or 0.7)

    regulated = qualification_cfg.get("regulated_industries", [])
    if not isinstance(regulated, list):
        regulated = []

    return {
        "min_evidence_confidence": min_evidence_confidence,
        "estimated_value": estimated_value,
        "min_viable_deal": min_viable_deal,
        "implementation_days": implementation_days,
        "max_delivery_days": max_delivery_days,
        "regulated_industries": [
            str(x).strip().lower() for x in regulated if str(x).strip()
        ],
    }


def qualification_inputs_for_prospect(prospect: dict) -> dict:
    defaults = dict(_qualification_defaults())
    industry = str(prospect.get("industry", "")).strip().lower()
    regulated_industries = defaults.pop("regulated_industries", [])
    has_compliance_risk = any(token in industry for token in regulated_industries)
    defaults["has_compliance_risk"] = has_compliance_risk
    return defaults


def load_compliance_cooldown_days() -> int:
    """Effective cooldown days for display/helpers; live mode uses fail-closed policy (see compliance_policy)."""
    evaluate_compliance_cooldown_for_run(
        dry_run=DRY_RUN, config_path=COMPLIANCE_CONFIG_PATH
    )
    days, block = get_compliance_cooldown_days_for_send(dry_run=DRY_RUN)
    return 0 if block else days


def apply_email_compliance_footer(
    html: str, require_footer: bool, from_email: str
) -> str:
    if not require_footer or not from_email:
        return html
    if "unsubscribe" in (html or "").lower():
        return html
    footer = (
        '<p style="font-size:11px;color:#666;margin-top:16px">'
        'Reply "unsubscribe" to opt out of these emails.'
        "</p>"
    )
    return (html or "") + footer


DEFAULT_OUTREACH_SIGNATURE = (
    "Best,\n"
    "Ismael Sudally\n"
    "Venture 2.0\n"
    "Revenue growth systems for early-stage B2B ventures"
)
OUTREACH_SIGNATURE = (
    os.environ.get("OUTREACH_SIGNATURE", DEFAULT_OUTREACH_SIGNATURE)
    .replace("\\n", "\n")
    .strip()
)
_TRUST_REJECT_PATTERNS = (
    r"\bventure os\b",
    r"\bguaranteed pipeline\b",
    r"\bcut costs by\b",
    r"\breduce no-show rates? by\b",
    r"\bhelp(?:ed)? \d+ clients\b",
    r"\bwe help businesses grow\b",
    r"\bleverag(?:e|ing) ai\b",
    r"\bai-powered\b",
    r"\bgame[- ]changing\b",
    r"\brevolutionary\b",
    r"\bfree audit\b",
    r"\b\$300\b",
    r"\b14-day pilot\b",
    r"https?://",
    r"\bwww\.",
    r"\bcalendly\b",
    r"\bloom\b",
)


def ensure_outreach_signature(message: str) -> str:
    body = (message or "").strip()
    if not body:
        return body
    if OUTREACH_SIGNATURE.lower() in body.lower():
        return body
    return f"{body}\n\n{OUTREACH_SIGNATURE}"


def founder_trust_issues(message: str) -> list[str]:
    text = (message or "").strip().lower()
    issues: list[str] = []
    if not text:
        return ["empty message"]
    for pattern in _TRUST_REJECT_PATTERNS:
        if re.search(pattern, text):
            issues.append(f"founder_trust_reject:{pattern}")
    return issues


def prospect_row_key(row: dict) -> str:
    """Stable key for merging outreach rows and syncing prospects.csv."""
    em = (row.get("email_found") or row.get("email") or "").strip().lower()
    nm = (row.get("name") or "").strip().lower()
    co = (row.get("company") or "").strip().lower()
    return f"{nm}|{co}|{em}"


def merge_generated_outreach_csv(
    path: pathlib.Path, fieldnames: list[str], new_rows: list[dict]
) -> None:
    """
    Merge this run's rows into generated-outreach.csv so prior sends are not dropped
    (follow-ups and history depend on the full file).
    """
    existing: list[dict] = []
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
    day8_schema = bool(existing) and {"company_name", "message", "auto_score"}.issubset(
        set(existing[0].keys())
    )
    if day8_schema:
        for r in new_rows:
            company = (r.get("company") or "").strip()
            role = (r.get("role") or "").strip()
            message = (r.get("generated_message") or "").strip()
            if not company or not role or not message:
                continue
            matched = False
            for existing_row in existing:
                if (
                    existing_row.get("company_name") or ""
                ).strip().lower() == company.lower() and (
                    existing_row.get("role") or ""
                ).strip().lower() == role.lower():
                    existing_row["message"] = message
                    existing_row["status"] = existing_row.get("status") or "PASS"
                    existing_row["auto_score"] = existing_row.get("auto_score") or "4"
                    if "approved" in existing_row:
                        existing_row["approved"] = existing_row.get("approved") or "yes"
                    matched = True
                    break
            if not matched:
                existing.append(
                    {
                        "company_name": company,
                        "role": role,
                        "message": message,
                        "status": "PASS",
                        "auto_score": "4",
                        "approved": "yes",
                    }
                )

        all_keys = (
            list(existing[0].keys())
            if existing
            else ["company_name", "role", "message", "status", "auto_score", "approved"]
        )
        for r in existing:
            for k in r:
                if k not in all_keys:
                    all_keys.append(k)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
            w.writeheader()
            for r in existing:
                w.writerow(sanitize_csv_row({k: r.get(k, "") for k in all_keys}))
        return

    merged: dict[str, dict] = {prospect_row_key(r): dict(r) for r in existing}
    for r in new_rows:
        merged[prospect_row_key(r)] = {**merged.get(prospect_row_key(r), {}), **dict(r)}
    out_rows = list(merged.values())
    all_keys = list(fieldnames)
    for r in out_rows:
        for k in r:
            if k not in all_keys:
                all_keys.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        w.writeheader()
        for r in out_rows:
            w.writerow(sanitize_csv_row({k: r.get(k, "") for k in all_keys}))


def sync_prospect_status_to_source_csv(
    prospects_path: pathlib.Path, pending_rows_mutated: list[dict]
) -> None:
    """Write status/email updates from this run back into prospects.csv (avoids duplicate sends)."""
    if not prospects_path.exists() or not pending_rows_mutated:
        return
    with open(prospects_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or PROSPECT_FIELDS)
        all_rows = list(reader)
    updates = {prospect_row_key(p): p for p in pending_rows_mutated}
    for row in all_rows:
        k = prospect_row_key(row)
        if k not in updates:
            continue
        src = updates[k]
        st = (src.get("status") or row.get("status") or "pending").strip()
        if st:
            row["status"] = st
        if src.get("email"):
            row["email"] = normalize_email(src["email"])
    with open(prospects_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)


def format_digest_date_long(when: datetime) -> str:
    """Windows-safe (no %-d)."""
    return f"{when:%A}, {when:%B} {when.day}, {when:%Y}"


def format_digest_date_short(when: datetime) -> str:
    return f"{when:%b} {when.day}"


def can_send_now() -> tuple[bool, str]:
    """Enforce send window and pacing to protect domain reputation."""
    now = datetime.now()
    if now.hour < SEND_START_HOUR or now.hour >= SEND_END_HOUR:
        return False, f"outside send window ({SEND_START_HOUR}:00-{SEND_END_HOUR}:00)"

    hour_cutoff = now.replace(minute=0, second=0, microsecond=0).isoformat()
    day_cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    hourly = job_queue.count_outbound_since(hour_cutoff)
    daily = job_queue.count_outbound_since(day_cutoff)
    if hourly >= SEND_HOURLY_CAP:
        return False, f"hourly send cap reached ({hourly}/{SEND_HOURLY_CAP})"
    if daily >= SEND_DAILY_CAP:
        return False, f"daily send cap reached ({daily}/{SEND_DAILY_CAP})"
    return True, ""


def enforce_capacity_hard_stop() -> None:
    """
    Hard stop outreach when delivery capacity is reached.
    This protects delivery quality and prevents self-sabotage.
    """
    if DRY_RUN:
        return
    active_clients = max(job_queue.count_active_clients(), ACTIVE_CLIENTS_CURRENT)
    if active_clients >= ACTIVE_CLIENT_CAPACITY:
        reason = f"active_clients_capacity_reached ({active_clients}/{ACTIVE_CLIENT_CAPACITY})"
        print(f"\n[fail] Live mode blocked: {reason}")
        job_queue.log_block(
            "system",
            "outreach_send",
            reason,
            "capacity hard stop",
            block_type="CAPACITY_BLOCK",
            severity="HARD",
        )
        raise SystemExit(4)


# ── 1. Load Config ────────────────────────────────────────────────────────────
def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {
        "service": os.environ.get("YOUR_SERVICE", "AI automation service"),
        "unique_value": os.environ.get(
            "YOUR_UNIQUE_VALUE", "saves time, increases revenue"
        ),
        "social_proof": os.environ.get(
            "YOUR_SOCIAL_PROOF", "helped similar businesses"
        ),
        "format": os.environ.get("OUTREACH_FORMAT", "LinkedIn DM"),
        "max_length": f"{os.environ.get('OUTREACH_MAX_WORDS', '80')} words",
    }


def load_approved_generated_messages() -> dict[str, str]:
    """Load approved Day 8 generated messages keyed by company + role."""
    if not OUTPUT_FILE.exists():
        return {}
    approved: dict[str, str] = {}
    with open(OUTPUT_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status") != "PASS":
                continue
            if (row.get("approved") or "").strip().lower() != "yes":
                continue
            message = (row.get("message") or "").strip()
            if not message:
                continue
            key = f"{(row.get('company_name') or '').strip().lower()}|{(row.get('role') or '').strip().lower()}"
            approved[key] = message
    return approved


# ── 2. Load Pending Prospects ─────────────────────────────────────────────────
def load_pending_prospects() -> list[dict]:
    if not PROSPECTS_FILE.exists():
        print(f"  [!] No prospects file at {PROSPECTS_FILE}")
        print("  Creating sample file — add real prospects and run again.")
        PROSPECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PROSPECTS_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=PROSPECT_FIELDS)
            writer.writeheader()
            writer.writerow(
                {
                    "name": "Jane Smith",
                    "company": "Bright Smiles Dental",
                    "role": "Owner",
                    "industry": "Dental",
                    "pain_point": "Losing patients who don't rebook",
                    "linkedin_url": "https://linkedin.com/in/janesmith",
                    "email": "",
                    "domain": "brightsmilesdental.com",
                    "status": "pending",
                }
            )
        return []
    with open(PROSPECTS_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = set(reader.fieldnames or [])

    # Day 8+ prospect_builder schema: company_name, validation_status (or legacy readiness_status), pain_signal.
    # Use only rows whose generated messages were explicitly approved.
    day8_schema = "company_name" in fieldnames and (
        "validation_status" in fieldnames or "readiness_status" in fieldnames
    )
    if day8_schema:
        approved_messages = load_approved_generated_messages()
        pending: list[dict] = []
        for row in rows:
            gate = (
                (row.get("validation_status") or row.get("readiness_status") or "")
                .strip()
                .upper()
            )
            if gate != "READY":
                continue
            key = f"{(row.get('company_name') or '').strip().lower()}|{(row.get('role') or '').strip().lower()}"
            message = approved_messages.get(key, "")
            if not message:
                continue
            pending.append(
                {
                    "name": row.get("name", ""),
                    "company": row.get("company_name", ""),
                    "role": row.get("role", ""),
                    "industry": row.get("industry", ""),
                    "pain_point": (row.get("pain_signal") or "").replace("_", " "),
                    "linkedin_url": row.get("linkedin_url", ""),
                    "email": row.get("email", ""),
                    "domain": row.get("domain", ""),
                    "status": "pending",
                    "generated_message": message,
                    "run_id": (row.get("run_id") or "").strip(),
                    "validation_status": (
                        row.get("validation_status")
                        or row.get("readiness_status")
                        or ""
                    ).strip(),
                }
            )
        return pending

    if AUTO_SEND_EMAILS and not DRY_RUN:
        print(
            "\n[fail] Live mode blocked: prospects.csv must use the prospect_builder "
            "schema (validation_status) and approved generated messages."
        )
        return []

    return [r for r in rows if r.get("status", "").lower() == "pending"]


# ── 3. Enrich Email via Hunter.io ─────────────────────────────────────────────
@hunter_api_call  # Automatic retry + rate limit
def _hunter_request(first_name: str, last_name: str, domain: str) -> httpx.Response:
    """Make raw Hunter.io API request."""
    return httpx.get(
        "https://api.hunter.io/v2/email-finder",
        params={
            "domain": domain,
            "first_name": first_name,
            "last_name": last_name,
            "api_key": HUNTER_API_KEY,
        },
        timeout=10,
    )


def lookup_email(first_name: str, last_name: str, company_domain: str) -> str:
    """Try to find a verified email via Hunter.io — returns empty string if not found."""
    if not HUNTER_API_KEY or not company_domain:
        return ""
    try:
        r = _hunter_request(first_name, last_name, company_domain)
        r.raise_for_status()
        data = r.json().get("data", {})
        email = data.get("email", "")
        score = data.get("score", 0)
        if email and score >= 50:  # only use high-confidence results
            return email
    except Exception as e:
        logger.warning(f"Hunter.io lookup failed for {first_name} {last_name}: {e}")
    return ""


# ── 4. Generate Outreach via OpenAI ──────────────────────────────────────────
@openai_api_call  # Automatic retry + rate limit
def _openai_request(prompt: str) -> httpx.Response:
    """Make raw OpenAI API request."""
    return httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 250,
            "temperature": 0.7,
        },
        timeout=30,
    )


def _extract_max_words(raw: str | int | None, fallback: int = 80) -> int:
    """Parse max words from config values like '80 words' or 80."""
    if isinstance(raw, int):
        return max(20, raw)
    text = str(raw or "").strip().lower()
    m = re.search(r"(\d+)", text)
    if not m:
        return fallback
    try:
        return max(20, int(m.group(1)))
    except Exception:
        return fallback


def _message_quality_issues(message: str, prospect: dict, max_words: int) -> list[str]:
    """Lightweight quality rubric to avoid generic junk outreach."""
    issues: list[str] = []
    text = (message or "").strip()
    low = text.lower()
    words = len(text.split()) if text else 0

    if not text:
        return ["empty_message"]
    if words < 20:
        issues.append("too_short")
    if words > max_words + 10:
        issues.append("too_long")

    generic_markers = (
        "hope you are well",
        "hope you're well",
        "just checking in",
        "i wanted to reach out",
        "circle back",
    )
    if any(m in low for m in generic_markers):
        issues.append("generic_opener")

    if "?" not in text:
        issues.append("missing_soft_cta_question")

    anchors: list[str] = []
    for key in ("company", "role", "industry"):
        val = str(prospect.get(key, "")).strip().lower()
        if val:
            anchors.append(val)
    pain = str(prospect.get("pain_point", "")).strip().lower()
    if pain:
        pain_tokens = [t for t in re.split(r"\W+", pain) if len(t) > 4][:3]
        anchors.extend(pain_tokens)

    if anchors and not any(a in low for a in anchors):
        issues.append("missing_personalization_anchor")

    return issues


def _rewrite_message_with_issues(
    *,
    first_draft: str,
    issues: list[str],
    prospect: dict,
    config: dict,
    max_words: int,
) -> str:
    issue_text = ", ".join(issues)
    prompt = f"""Rewrite this outreach message so it feels premium, specific, and human.

Draft:
{first_draft}

Prospect context:
- Name: {prospect.get('name', '')}
- Company: {prospect.get('company', '')}
- Role: {prospect.get('role', '')}
- Industry: {prospect.get('industry', '')}
- Pain point: {prospect.get('pain_point', '')}

Offer context:
- Service: {config['service']}
- Unique value: {config['unique_value']}
- Social proof: {config['social_proof']}

Fix these issues: {issue_text}

Rules:
- Max {max_words} words
- Conversational, no cliches, no fake familiarity
- Mention one specific personalization anchor from prospect context
- Include one soft CTA question at the end
- No mention of AI unless explicitly relevant
- Output message only
"""
    r = _openai_request(prompt)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def generate_message(prospect: dict, config: dict) -> str:
    max_words = _extract_max_words(config.get("max_length"), 80)
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI key missing - aborting run")
    prompt = f"""Write a premium, personalised {config['format']} for this prospect.

SERVICE: {config['service']}
UNIQUE VALUE: {config['unique_value']}
SOCIAL PROOF: {config['social_proof']}

PROSPECT:
- Name: {prospect.get('name', '')}
- Company: {prospect.get('company', '')}
- Role: {prospect.get('role', '')}
- Industry: {prospect.get('industry', '')}
- Pain point: {prospect.get('pain_point', '')}

RULES:
- Max {max_words} words
- Conversational, specific to their situation, and zero cliches
- Include one concrete personalization anchor from role/company/pain point
- Soft CTA question at end
- No "Hope you're well" and no generic opener
- No mentioning AI unless relevant
- Do not fabricate facts
Write the message only."""

    try:
        r = _openai_request(prompt)
        r.raise_for_status()
        draft = r.json()["choices"][0]["message"]["content"].strip()
        issues = _message_quality_issues(draft, prospect, max_words)
        if not issues:
            return draft

        # One controlled rewrite pass for quality uplift.
        refined = _rewrite_message_with_issues(
            first_draft=draft,
            issues=issues,
            prospect=prospect,
            config=config,
            max_words=max_words,
        )
        refined_issues = _message_quality_issues(refined, prospect, max_words)
        if refined_issues:
            logger.warning(
                "Outreach quality issues remain for %s @ %s: %s",
                prospect.get("name", ""),
                prospect.get("company", ""),
                ",".join(refined_issues),
            )
        return refined
    except Exception as e:
        logger.error(f"OpenAI request failed: {e}")
        if HARD_FAIL_ON_GENERATION_ERROR:
            raise RuntimeError(f"OpenAI generation failed: {e}")
        return f"[OpenAI error: {e}]"


# ── 5. Sync to Airtable ───────────────────────────────────────────────────────
@airtable_api_call  # Automatic retry + rate limit
def _airtable_request(url: str, record: dict, headers: dict) -> httpx.Response:
    """Make raw Airtable API request."""
    return httpx.post(url, headers=headers, json={"fields": record}, timeout=15)


def sync_to_airtable(table: str, record: dict) -> bool:
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        return False
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        r = _airtable_request(url, record, headers)
        r.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"Airtable sync failed for {table}: {e}")
        return False


# ── 5.5 Policy Gatekeeper (autonomous safety control) ─────────────────────────
def load_policy_decision() -> dict | None:
    """Load current policy decision from policy.json or ``VENTURE_POLICY_JSON`` (absolute path)."""
    override = (os.environ.get("VENTURE_POLICY_JSON") or "").strip()
    if override:
        policy_path = pathlib.Path(override)
    else:
        config_dir = pathlib.Path(__file__).parent.parent / "venture-engine" / "config"
        policy_path = config_dir / "policy.json"
    try:
        if policy_path.exists():
            with open(policy_path, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load policy from {policy_path}: {e}")
    return None


def apply_policy_cooldown_multiplier(
    base_days: int,
    *,
    send_type: str,
) -> int:
    """
    Scale cooldown days for ``gate_outbound_send`` using policy.json:
    ``cooldown_multiplier`` and an extra factor when ``send_velocity`` is ``slow``.
    Transactional sends are unchanged. Dry-run and live both use the same scaling.
    """
    st = (send_type or "initial").strip().lower()
    if st == "transactional":
        return int(base_days or 0)
    base = int(base_days or 0)
    p = load_policy_decision() or {}
    try:
        mult = float(p.get("cooldown_multiplier") or 1.0)
    except (TypeError, ValueError):
        mult = 1.0
    vel = str(p.get("send_velocity") or "normal").lower().strip()
    if vel == "slow":
        mult *= 1.25
    return max(0, int(round(float(base) * mult)))


def _policy_followup_depth_cap() -> int | None:
    """
    Max automated follow-ups per prospect per pipeline run from policy.json.
    ``None`` if no policy file (preserve legacy behavior). ``0`` disables follow-ups.
    """
    p = load_policy_decision()
    if p is None:
        return None
    try:
        raw = p.get("followup_depth", 2)
        return max(0, int(raw if raw is not None else 2))
    except (TypeError, ValueError):
        return 2


def check_policy_gatekeeper() -> tuple[bool, str]:
    """
    Policy gatekeeper: checks if sends should be allowed per current policy.

    Returns:
        (allowed: bool, reason: str)

    Blocks sends if:
      - system in SAFE_MODE (critical issue, manual reset required)
      - send_velocity is "paused"

    Otherwise allows. ``followup_depth`` and cooldown scaling are applied in
    ``check_and_send_followups`` and ``apply_policy_cooldown_multiplier`` / ``send_email``.
    """
    policy = load_policy_decision()
    if not policy:
        # No policy file: default to allow (system initializing)
        return True, ""

    mode = policy.get("mode", "NORMAL")
    velocity = policy.get("send_velocity", "normal")

    if mode == "SAFE_MODE":
        return False, f"policy_gatekeeper: SAFE_MODE active (manual reset required)"

    if velocity == "paused":
        return False, f"policy_gatekeeper: send_velocity is paused"

    return True, ""


# ── 6. Send Email via Resend ──────────────────────────────────────────────────
def _resend_request(
    to_email: str,
    to_name: str,
    subject: str,
    body_plain: str,
    send_type: str,
    run_id: str,
    *,
    legacy_html: str | None = None,
) -> httpx.Response:
    """Make guarded Resend API request (MIME assembly + footers live in send_guard)."""
    sender = f"{RESEND_FROM_NAME} <{RESEND_FROM_EMAIL}>"
    if legacy_html is not None:
        payload: dict = {
            "from": sender,
            "to": [normalize_email(to_email)],
            "subject": subject,
            "html": legacy_html,
        }
    else:
        payload = {
            "from": sender,
            "to": [normalize_email(to_email)],
            "subject": subject,
            "cold_body_text": body_plain,
        }
    return send_email_safe(
        payload=payload,
        api_key=RESEND_API_KEY,
        send_type=send_type,
        run_id=run_id,
        dry_run=DRY_RUN,
        source="venture_pipeline",
        is_suppressed=job_queue.is_suppressed,
    )


def _mask_email_for_log(value: str) -> str:
    if "@" not in (value or ""):
        return "(unset)"
    name, domain = value.split("@", 1)
    return f"{name[:1]}***@{domain}" if name else f"***@{domain}"


def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    body_plain: str,
    prospect_id: str = "",
    campaign_key: str = "outreach_initial",
    send_type: str = "initial_prospect",
    cooldown_days: int | None = None,
    run_id: str | None = None,
    *,
    send_attempt_id: str = "",
    company: str = "",
    legacy_html: str | None = None,
) -> bool:
    """Send email via Resend; gating uses behavioral idempotency + universal cooldown (see job_queue.gate_outbound_send)."""
    # Policy gatekeeper first so SAFE_MODE / paused blocks without requiring Resend credentials.
    can_proceed, gate_reason = check_policy_gatekeeper()
    if not can_proceed:
        logger.warning(
            f"Send blocked by policy gatekeeper for {_mask_email_for_log(to_email)}: {gate_reason}"
        )
        job_queue.log_block(
            "opportunity",
            str(prospect_id or to_email),
            "policy_gatekeeper_block",
            gate_reason,
            block_type="POLICY_BLOCK",
            severity="SOFT",
        )
        return False

    if not RESEND_API_KEY or not RESEND_FROM_EMAIL:
        return False

    evaluate_compliance_cooldown_for_run(
        dry_run=DRY_RUN, config_path=COMPLIANCE_CONFIG_PATH
    )
    st = (send_type or "initial_prospect").strip().lower()
    sender = f"{RESEND_FROM_NAME} <{RESEND_FROM_EMAIL}>"
    if legacy_html is not None:
        material = materialize_outbound_payload(
            {
                "from": sender,
                "to": [normalize_email(to_email)],
                "subject": subject,
                "html": legacy_html,
            },
            send_type=st,
        )
    else:
        material = materialize_outbound_payload(
            {
                "from": sender,
                "to": [normalize_email(to_email)],
                "subject": subject,
                "cold_body_text": body_plain,
            },
            send_type=st,
        )
    html_body = str(material.get("html") or "")
    policy_block: str | None = None
    if st == "transactional_digest":
        cd = 0
    elif DRY_RUN:
        d, _ = get_compliance_cooldown_days_for_send(dry_run=True)
        cd = int((cooldown_days if cooldown_days is not None else d) or 0)
    else:
        d, br = get_compliance_cooldown_days_for_send(dry_run=False)
        if br:
            policy_block = br
            cd = 0
        else:
            cd = int((cooldown_days if cooldown_days is not None else d) or 0)
    cd = apply_policy_cooldown_multiplier(int(cd or 0), send_type=st)
    can_send, reason = job_queue.gate_outbound_send(
        prospect_id or to_email,
        campaign_key,
        to_email,
        send_type=st,
        cooldown_days=int(cd or 0),
        policy_block_reason=policy_block,
    )
    if not can_send:
        if policy_block and reason == policy_block:
            return False
        logger.warning(f"Send blocked for {_mask_email_for_log(to_email)}: {reason}")
        if "suppression" in reason:
            _bt, _sev = "COMPLIANCE_BLOCK", "HARD"
        else:
            _bt, _sev = "QUALITY_BLOCK", "SOFT"
        job_queue.log_block(
            "opportunity",
            str(prospect_id or to_email),
            "idempotency_or_suppression_block",
            reason,
            block_type=_bt,
            severity=_sev,
        )
        return False
    try:
        r = _resend_request(
            to_email,
            to_name,
            subject,
            body_plain,
            send_type=st,
            run_id=run_id or BATCH_RUN_ID,
            legacy_html=legacy_html,
        )
        r.raise_for_status()
        out_status = "dry_run" if DRY_RUN else "sent"
        job_queue.record_outbound(
            prospect_id=prospect_id or to_email,
            campaign_key=campaign_key,
            recipient_email=to_email,
            subject=subject,
            html_body=html_body,
            status=out_status,
            send_type=st,
        )
        try:
            _append_send_log_row(
                email=to_email,
                company=company,
                subject=subject,
                html_body=html_body,
                send_attempt_id=send_attempt_id,
            )
        except OSError as exc:
            logger.warning("send_log append failed: %s", exc)
        logger.info(f"Email sent to {_mask_email_for_log(to_email)}")
        return True
    except Exception as e:
        logger.error(f"Resend send failed to {_mask_email_for_log(to_email)}: {e}")
        return False


def _generate_raw(prompt: str) -> str:
    """Call OpenAI with a raw prompt string."""
    if not OPENAI_API_KEY:
        return prompt
    try:
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.7,
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[OpenAI error: {e}]"


def is_message_sendable(message: str) -> tuple[bool, str]:
    """Block obvious failure placeholders from being sent to prospects."""
    text = (message or "").strip().lower()
    if not text:
        return False, "message is empty"
    if len(text) < MIN_MESSAGE_CHARS:
        return (
            False,
            f"generation_failed:low_quality_too_short_chars<{MIN_MESSAGE_CHARS}",
        )
    if "{" in text or "}" in text:
        return False, "generation_failed:low_quality_template_artifact"
    if "lorem" in text:
        return False, "generation_failed:low_quality_placeholder_text"
    if re.search(r"\berror\b", text):
        return False, "generation_failed:error_token_detected"
    blocked_markers = (
        "[openai error:",
        "[openai_api_key not set",
        "error calling openai",
    )
    for marker in blocked_markers:
        if marker in text:
            return False, f"generation_failed:message contains failure marker: {marker}"
    if len(text.split()) < 12:
        return False, "message too short to be credible outreach"
    trust_issues = founder_trust_issues(message)
    if trust_issues:
        return False, "founder_trust_check_failed:" + ";".join(trust_issues)
    return True, ""


# ── 7. Follow-up Detector ─────────────────────────────────────────────────────
def check_and_send_followups(config: dict):
    """SQLite-driven follow-ups: initial send recorded in outbound_events, no CSV eligibility."""
    evaluate_compliance_cooldown_for_run(
        dry_run=DRY_RUN, config_path=COMPLIANCE_CONFIG_PATH
    )
    if not DRY_RUN:
        _, br = get_compliance_cooldown_days_for_send(dry_run=False)
        if br:
            return
    depth_cap = _policy_followup_depth_cap()
    if depth_cap is not None and depth_cap <= 0:
        return
    cd_days, _ = get_compliance_cooldown_days_for_send(dry_run=DRY_RUN)
    min_days = max(FOLLOWUP_DAYS, cd_days)
    rows = job_queue.list_followup_eligible_rows(min_days)
    if not rows:
        return
    followups_sent: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        email = (row.get("recipient_email") or "").strip()
        if not email:
            continue
        if job_queue.is_suppressed(email):
            logger.warning(f"Follow-up blocked (suppressed): {email}")
            continue
        prospect_id = str(row.get("prospect_id") or email)
        if depth_cap is not None and followups_sent[prospect_id] >= depth_cap:
            continue
        campaign_key = row.get("campaign_key") or "outreach_initial"
        name = row.get("name") or ""
        company = row.get("company") or ""
        prompt = (
            f"Write a 2-sentence follow-up to someone who hasn't replied to my initial outreach. "
            f"Name: {name}. Company: {company}. "
            f"I offer: {config.get('service', '')}. Be friendly, not pushy. One soft CTA."
        )
        followup_msg = _generate_raw(prompt)
        ok_to_send, send_reason = is_message_sendable(followup_msg)
        if not ok_to_send:
            logger.warning(f"Follow-up blocked for {email}: {send_reason}")
            continue
        subject = f"Re: outbound fit for {company or 'your venture'}"
        sent = send_email(
            email,
            name,
            subject,
            followup_msg.strip(),
            prospect_id=prospect_id,
            campaign_key=campaign_key,
            send_type="followup",
            run_id=BATCH_RUN_ID,
            send_attempt_id=f"followup_{prospect_id}_{campaign_key}",
            company=company,
        )
        if sent:
            followups_sent[prospect_id] += 1
            job_queue.record_lifecycle_event(
                prospect_id,
                LifecycleEventType.FOLLOWUP_SENT,
                payload={"email": email, "campaign_key": campaign_key},
                name=name,
                company=company,
                email=email,
                pipeline_stage="followup_sent",
                status_reason="automatic_followup_sent",
            )
            print(f"  ↩ Follow-up sent → {name or prospect_id} @ {company or email}")


# ── 8. KPI Summary ────────────────────────────────────────────────────────────
def print_kpi_summary():
    if not KPI_FILE.exists():
        print("\n[KPI] No data yet. Run: python 04-coding/scripts/kpi_tracker.py")
        return
    with open(KPI_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return
    print("\n" + "=" * 55)
    print("  VENTURE KPI SUMMARY")
    print("=" * 55)
    last = rows[-1]
    try:
        revenue = float(last.get("monthly_revenue", 0) or 0)
        gap = REVENUE_TARGET - revenue
        pct = revenue / REVENUE_TARGET * 100
        print(f"  Current MRR:    ${revenue:>8,.0f}")
        print(f"  Target:         ${REVENUE_TARGET:>8,.0f}")
        print(f"  Gap:            ${gap:>8,.0f}  ({pct:.0f}% of target)")
    except ValueError:
        pass

    # 4-week reply rate
    recent4 = rows[-4:]
    try:
        out = sum(int(r.get("outreach_sent", 0) or 0) for r in recent4)
        rep = sum(int(r.get("positive_replies", 0) or 0) for r in recent4)
        rate = rep / out * 100 if out else 0
        print(f"  4-wk reply rate: {rate:.1f}%  (target ≥5%)")
    except ValueError:
        pass
    print("=" * 55)


def send_digest_email():
    """Email yourself a KPI summary after every pipeline run."""
    if AUTO_SEND_EMAILS and not DRY_RUN:
        print("  [skip] KPI digest disabled during Batch 1 live execution")
        return
    if not DIGEST_TO_EMAIL or not KPI_FILE.exists():
        return
    with open(KPI_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return
    last = rows[-1]
    try:
        revenue = float(last.get("monthly_revenue", 0) or 0)
        gap = REVENUE_TARGET - revenue
        pct = revenue / REVENUE_TARGET * 100
        recent4 = rows[-4:]
        out = sum(int(r.get("outreach_sent", 0) or 0) for r in recent4)
        rep = sum(int(r.get("positive_replies", 0) or 0) for r in recent4)
        rate = rep / out * 100 if out else 0
    except (ValueError, ZeroDivisionError):
        return
    now = datetime.now()
    html = f"""
    <h2 style="font-family:sans-serif">Venture OS — Weekly KPI Digest</h2>
    <p style="color:#888">{format_digest_date_long(now)}</p>
    <table style="font-family:sans-serif;border-collapse:collapse">
      <tr><td style="padding:6px 16px 6px 0">Current MRR</td><td><strong>${revenue:,.0f}</strong></td></tr>
      <tr><td style="padding:6px 16px 6px 0">Target</td><td>${REVENUE_TARGET:,.0f}</td></tr>
      <tr><td style="padding:6px 16px 6px 0">Gap</td><td>${gap:,.0f} ({pct:.0f}% of target)</td></tr>
      <tr><td style="padding:6px 16px 6px 0">4-wk Reply Rate</td><td>{rate:.1f}% (target ≥5%)</td></tr>
    </table>
    <hr>
    <p style="color:#aaa;font-size:12px">Sent automatically by Venture OS pipeline</p>
    """
    digest_campaign = f"kpi_digest:{now.strftime('%Y-%m-%d')}"
    sent = send_email(
        DIGEST_TO_EMAIL,
        "Founder",
        f"Venture KPI Digest — {format_digest_date_short(now)}",
        "",
        prospect_id=DIGEST_TO_EMAIL,
        campaign_key=digest_campaign,
        send_type="transactional_digest",
        run_id=BATCH_RUN_ID,
        send_attempt_id=f"digest_{digest_campaign}",
        company="",
        legacy_html=html,
    )
    if sent:
        print(f"  [ok] KPI digest emailed -> {DIGEST_TO_EMAIL}")


def print_operator_status() -> None:
    """Lightweight snapshot for operators (queue, DLQ, last send, cooldown)."""
    print("\nVenture OS — operator status")
    print(
        f"  {describe_compliance_policy_line(dry_run=DRY_RUN, config_path=COMPLIANCE_CONFIG_PATH)}"
    )
    print(f"  job_queue.db_path: {job_queue.db_path}")
    summary = job_queue.get_summary()
    print(
        "  jobs: "
        f"pending={summary.get('pending', 0)} "
        f"in_progress={summary.get('in_progress', 0)} "
        f"completed={summary.get('completed', 0)} "
        f"failed={summary.get('failed', 0)} "
        f"abandoned={summary.get('abandoned', 0)}"
    )
    dlq_n = job_queue.count_webhook_dlq()
    dlq_health = "WARNING (needs replay or triage)" if dlq_n > 0 else "OK"
    print(f"  webhook_dlq: {dlq_n} row(s)  [{dlq_health}]")
    if dlq_n:
        for r in job_queue.list_webhook_dlq(limit=8):
            err = (r.get("error") or "")[:100].replace("\n", " ")
            print(
                f"    id={r.get('id')}  {r.get('created_at')}  {r.get('source')}  {err}"
            )
    last = job_queue.last_outbound_sent_at()
    print(f"  last outbound (sent): {last or '(none)'}")
    print(f"  outreach_frozen: {job_queue.is_outreach_frozen()}")
    print("  (replay DLQ: python 04-coding/scripts/dlq_replay.py --help)\n")


# ── Retry Failed Jobs ─────────────────────────────────────────────────────────
def retry_failed_jobs():
    """Process any failed jobs from previous runs before handling new prospects."""
    failed = job_queue.get_failed_jobs()
    if not failed:
        return

    logger.info(f"Found {len(failed)} failed jobs eligible for retry")
    print(f"\n--- Retrying {len(failed)} Failed Jobs ---")

    for job in failed[:10]:  # Process max 10 per run to avoid timeout
        try:
            if job.action == JobAction.EMAIL_LOOKUP:
                ctx = job.context or {}
                email = lookup_email(
                    ctx.get("first_name", ""),
                    ctx.get("last_name", ""),
                    ctx.get("domain", ""),
                )
                job_queue.complete_job(job.id, result=email or "not_found")
                logger.info(f"Retried email lookup: {job.id}")

            elif job.action == JobAction.GENERATE_MESSAGE:
                config = load_config()
                message = generate_message(job.context.get("prospect", {}), config)
                job_queue.complete_job(job.id, result=message)
                logger.info(f"Retried message generation: {job.id}")

            elif job.action == JobAction.NOTION_SYNC:
                if NOTION_API_KEY:
                    ctx = job.context or {}
                    result = _notion_prospect(
                        NOTION_API_KEY,
                        NOTION_PROSPECTS_DB,
                        name=ctx.get("name", ""),
                        company=ctx.get("company", ""),
                        role=ctx.get("role", ""),
                        industry=ctx.get("industry", ""),
                        pain_point=ctx.get("pain_point", ""),
                        email=ctx.get("email", ""),
                        linkedin=ctx.get("linkedin", ""),
                        message=ctx.get("message", ""),
                    )
                    job_queue.complete_job(job.id, result=result)
                    logger.info(f"Retried Notion sync: {job.id}")
                else:
                    job_queue.fail_job(
                        job.id, error="NOTION_API_KEY not set", retry=False
                    )

            elif job.action == JobAction.AIRTABLE_SYNC:
                if AIRTABLE_API_KEY:
                    ctx = job.context or {}
                    record = {
                        "Name": ctx.get("name"),
                        "Company": ctx.get("company"),
                        "Role": ctx.get("role"),
                        "Industry": ctx.get("industry"),
                        "Pain Point": ctx.get("pain_point"),
                        "Email": ctx.get("email", ""),
                        "LinkedIn": ctx.get("linkedin_url", ""),
                        "Status": "Outreach Ready",
                        "Generated Message": ctx.get("message", ""),
                    }
                    synced = sync_to_airtable(AIRTABLE_PROSPECTS_TABLE, record)
                    if synced:
                        job_queue.complete_job(job.id, result="synced")
                        logger.info(f"Retried Airtable sync: {job.id}")
                    else:
                        job_queue.fail_job(job.id, error="Sync failed", retry=True)
                else:
                    job_queue.fail_job(
                        job.id, error="AIRTABLE_API_KEY not set", retry=False
                    )

            elif job.action == JobAction.SEND_EMAIL:
                if not ENABLE_SEND_EMAIL_RETRIES:
                    logger.warning(
                        "Skipping failed send_email retry because "
                        "ENABLE_SEND_EMAIL_RETRIES is not true"
                    )
                    continue
                ctx = job.context or {}
                cold = (ctx.get("cold_body_text") or "").strip()
                legacy = (ctx.get("html") or "").strip()
                sent = send_email(
                    ctx.get("to_email", ""),
                    ctx.get("to_name", ""),
                    ctx.get("subject", ""),
                    cold if cold else "",
                    prospect_id=job.prospect_id or ctx.get("to_email", ""),
                    campaign_key=ctx.get("campaign_key", "outreach_initial"),
                    send_type="retry",
                    run_id=BATCH_RUN_ID,
                    send_attempt_id=str(job.id),
                    company=str(ctx.get("company") or ""),
                    legacy_html=legacy if not cold and legacy else None,
                )
                if sent:
                    job_queue.complete_job(job.id, result="sent")
                    logger.info(f"Retried email send: {job.id}")
                else:
                    job_queue.fail_job(job.id, error="Send failed", retry=True)

        except Exception as e:
            logger.error(f"Retry failed for {job.id}: {e}")
            job_queue.fail_job(job.id, error=str(e), retry=True)


def _capture_phase1_snapshot() -> dict[str, int | dict[str, int]]:
    """Capture sparse baseline counters for Phase 1 structured telemetry deltas."""
    summary = job_queue.get_summary()
    phase1_snapshot: dict[str, int | dict[str, int]] = {
        "job_summary": {
            "pending": int(summary.get("pending", 0)),
            "in_progress": int(summary.get("in_progress", 0)),
            "completed": int(summary.get("completed", 0)),
            "failed": int(summary.get("failed", 0)),
            "abandoned": int(summary.get("abandoned", 0)),
        },
        "jobs_total": 0,
        "lifecycle_events_total": 0,
        "block_logs_total": 0,
        "block_logs_hard": 0,
        "block_logs_soft": 0,
        "block_logs_info": 0,
        "jobs_retry_sum": 0,
        "operator_pause_blocks_total": 0,
        "operator_lifecycle_events_total": 0,
    }
    try:
        with sqlite3.connect(job_queue.db_path) as conn:
            cur = conn.execute("SELECT COUNT(*) FROM jobs")
            phase1_snapshot["jobs_total"] = int((cur.fetchone() or [0])[0] or 0)
            cur = conn.execute("SELECT COUNT(*) FROM lifecycle_events")
            phase1_snapshot["lifecycle_events_total"] = int(
                (cur.fetchone() or [0])[0] or 0
            )
            cur = conn.execute("SELECT COUNT(*) FROM block_logs")
            phase1_snapshot["block_logs_total"] = int((cur.fetchone() or [0])[0] or 0)
            cur = conn.execute(
                "SELECT COUNT(*) FROM block_logs WHERE UPPER(COALESCE(severity,''))='HARD'"
            )
            phase1_snapshot["block_logs_hard"] = int((cur.fetchone() or [0])[0] or 0)
            cur = conn.execute(
                "SELECT COUNT(*) FROM block_logs WHERE UPPER(COALESCE(severity,''))='SOFT'"
            )
            phase1_snapshot["block_logs_soft"] = int((cur.fetchone() or [0])[0] or 0)
            cur = conn.execute(
                "SELECT COUNT(*) FROM block_logs WHERE UPPER(COALESCE(severity,''))='INFO'"
            )
            phase1_snapshot["block_logs_info"] = int((cur.fetchone() or [0])[0] or 0)
            cur = conn.execute("SELECT COALESCE(SUM(retry_count), 0) FROM jobs")
            phase1_snapshot["jobs_retry_sum"] = int((cur.fetchone() or [0])[0] or 0)
            cur = conn.execute(
                "SELECT COUNT(*) FROM block_logs WHERE block_type='OPERATOR_PAUSE_BLOCK'"
            )
            phase1_snapshot["operator_pause_blocks_total"] = int(
                (cur.fetchone() or [0])[0] or 0
            )
            cur = conn.execute(
                "SELECT COUNT(*) FROM lifecycle_events WHERE source='operator'"
            )
            phase1_snapshot["operator_lifecycle_events_total"] = int(
                (cur.fetchone() or [0])[0] or 0
            )
    except sqlite3.Error as exc:
        logger.warning("Phase 1 snapshot capture failed: %s", exc)
    return phase1_snapshot


# ── Main Pipeline ─────────────────────────────────────────────────────────────
def main():
    print("\n========================================")
    print("  VENTURE OS — AUTOMATION PIPELINE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("========================================\n")

    reset_compliance_cooldown_policy_for_run()
    evaluate_compliance_cooldown_for_run(
        dry_run=DRY_RUN, config_path=COMPLIANCE_CONFIG_PATH
    )

    # Validate integration config early to avoid confusing downstream failures
    validate_integrations()
    enforce_provider_auth_readiness()
    enforce_live_mode_readiness()
    validate_live_mode_integrations()
    enforce_capacity_hard_stop()
    if job_queue.is_outreach_frozen() and not DRY_RUN:
        print("\n[fail] Live mode blocked: outreach is frozen by system control.")
        raise SystemExit(6)

    integrity = evaluate_integrity(job_queue)
    if integrity.should_block_outreach and not DRY_RUN:
        print("\n[fail] Live mode blocked by system integrity monitor:")
        for reason in integrity.reasons:
            print(f"  - {reason}")
        job_queue.set_outreach_freeze(True, reason="integrity_monitor_triggered")
        job_queue.log_block(
            "system",
            "outreach_send",
            "integrity_monitor_block",
            json.dumps(integrity.metrics),
            block_type="INTEGRITY_BLOCK",
            severity="HARD",
        )
        raise SystemExit(5)
    elif not DRY_RUN:
        job_queue.set_outreach_freeze(False, reason="integrity_monitor_healthy")

    no_response = analyze_no_response_patterns(job_queue)
    job_queue.log_decision(
        "diagnostics",
        "no_response_7d",
        "analysis_complete",
        [f"status:{no_response['status']}", f"diagnosis:{no_response['diagnosis']}"],
    )

    config = load_config()
    prospects = load_pending_prospects()

    exec_run_id = canonical_execution_run_id()
    try:
        elig = filter_prospects_for_outbound_send(
            prospects,
            prospects_path=PROSPECTS_FILE,
            data_base=DATA_BASE,
            current_run_id=exec_run_id,
        )
        prospects = elig.prospects
        if elig.all_ineligible_after_filter:
            emit_no_eligible_prospects_event(run_id=exec_run_id)
    except OutboundEligibilityAuditError as exc:
        print(f"\n[fail] Outbound eligibility blocked: {exc}")
        raise SystemExit(9) from exc

    if AUTO_SEND_EMAILS and not DRY_RUN:
        try:
            batch_preflight = run_batch_preflight(
                mode="live",
                run_id=BATCH_RUN_ID,
                sender_email=RESEND_FROM_EMAIL,
                sender_name=RESEND_FROM_NAME,
                resend_api_key=RESEND_API_KEY,
                prospects_file=PROSPECTS_FILE,
                output_file=OUTPUT_FILE,
                db_path=DB_PATH,
                write_lock_on_success=True,
            )
        except (BatchGuardError, LockIntegrityError) as exc:
            print(f"\n[fail] Live mode blocked: Batch 1 guard failure ({exc})")
            raise SystemExit(7) from exc
        if not batch_preflight["ok"]:
            print("\n[fail] Live mode blocked by Batch 1 preflight:")
            for check in batch_preflight["checks"]:
                if not check["passed"] and check["severity"] == "FAIL":
                    print(f"  - {check['name']}: {check['detail']}")
            print(f"\nPreflight log: {batch_preflight['log_file']}")
            raise SystemExit(7)
        print(f"[ok] Batch 1 preflight passed: {batch_preflight['log_file']}")
        try:
            consume_batch_lock(
                run_id=BATCH_RUN_ID, manifest=batch_preflight["manifest"]
            )
        except (BatchGuardError, LockIntegrityError) as exc:
            print(f"\n[fail] Live mode blocked: could not consume Batch 1 lock ({exc})")
            raise SystemExit(7) from exc
        print(
            "[ok] Batch 1 lock consumed; this run is now bound to approved recipients."
        )

    phase1_pipeline_started_at = datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )

    # Retry failed jobs from previous runs
    retry_failed_jobs()

    # Clean up old completed/abandoned jobs (keep 30 days)
    deleted = job_queue.cleanup_old_jobs(days=30)
    if deleted > 0:
        logger.info(f"Cleaned up {deleted} old job records")

    phase1_snapshot_before = _capture_phase1_snapshot()

    run_health = {
        "generated": 0,
        "qualified": 0,
        "sent": 0,
        "blocked": 0,
        "reply_rate_estimate": 0.0,
    }
    if not prospects:
        print(
            "No pending prospects. Add rows with status=pending to 06-sales/prospects.csv"
        )
    else:
        print(f"Found {len(prospects)} pending prospects.\n")
        batch_aborted = False
        batch_abort_reason = ""
        output_rows = []
        all_fields = PROSPECT_FIELDS + [
            "email_found",
            "generated_message",
            "generated_at",
            "email_status",
            "sent_at",
            "follow_up_sent",
            "follow_up_sent_at",
            "message_version",
            "generator_version",
            "guard_version",
            "message_hash",
            "cohort_id",
        ]
        cohort_message_snap_written = False

        for p in prospects:
            print(f"  Processing: {p['name']} @ {p['company']}")
            prospect_id = p.get("id", p.get("name", ""))
            job_queue.record_lifecycle_event(
                str(prospect_id),
                LifecycleEventType.PROSPECT_LOADED,
                payload={"company": p.get("company", "")},
                name=p.get("name", ""),
                company=p.get("company", ""),
                email=p.get("email", ""),
                pipeline_stage="loaded",
                status_reason="ready_for_enrichment",
            )

            # Email enrichment — uses explicit 'domain' field, no guessing
            if not p.get("email") and HUNTER_API_KEY:
                domain = p.get("domain", "").strip()
                if domain:
                    parts = p["name"].split()
                    first = parts[0] if parts else ""
                    last = parts[-1] if len(parts) > 1 else ""

                    # Track email lookup in job queue
                    email_job_id = f"{p['name'].replace(' ', '_')}_{p['company'].replace(' ', '_')}_email_{int(datetime.now().timestamp()*1000)}"
                    email_job = job_queue.add_job(
                        job_id=email_job_id,
                        action=JobAction.EMAIL_LOOKUP,
                        prospect_id=prospect_id,
                        context={
                            "first_name": first,
                            "last_name": last,
                            "domain": domain,
                        },
                        max_retries=2,
                    )
                    job_queue.start_job(email_job.id)

                    try:
                        email = lookup_email(first, last, domain)
                        job_queue.complete_job(
                            email_job.id, result=email or "not_found"
                        )
                        if email:
                            p["email"] = email
                            print(f"    [ok] Email found: {email}")
                            job_queue.record_lifecycle_event(
                                str(prospect_id),
                                LifecycleEventType.EMAIL_ENRICHED,
                                payload={"email": email},
                                name=p.get("name", ""),
                                company=p.get("company", ""),
                                email=email,
                                pipeline_stage="enriched",
                                status_reason="email_verified",
                            )
                    except Exception as e:
                        logger.error(f"Email lookup failed for {p['name']}: {e}")
                        job_queue.fail_job(email_job.id, error=str(e), retry=True)
                else:
                    print(
                        f"    [warn] No domain set for {p['name']} - add 'domain' column to prospects.csv to enable Hunter lookup"
                    )

            # Generate message — tracked in job queue
            message_job_id = f"{p['name'].replace(' ', '_')}_{p['company'].replace(' ', '_')}_message_{int(datetime.now().timestamp()*1000)}"
            message_job = job_queue.add_job(
                job_id=message_job_id,
                action=JobAction.GENERATE_MESSAGE,
                prospect_id=prospect_id,
                context={"prospect": p, "config": config},
                max_retries=2,
            )
            job_queue.start_job(message_job.id)
            generation_failed = False

            try:
                message = (p.get("generated_message") or "").strip()
                if message:
                    print(
                        f"    [ok] Using approved generated message ({len(message.split())} words)"
                    )
                else:
                    message = generate_message(p, config)
                message = ensure_outreach_signature(message)
                job_queue.complete_job(message_job.id, result=message)
                if not p.get("generated_message"):
                    print(f"    [ok] Message generated ({len(message.split())} words)")
                run_health["generated"] += 1
                _evidence = 0.7 if "openai error" not in message.lower() else 0.3
                job_queue.record_lifecycle_event(
                    str(prospect_id),
                    LifecycleEventType.MESSAGE_DRAFTED,
                    payload={
                        "word_count": len(message.split()),
                        "evidence_confidence": _evidence,
                    },
                    name=p.get("name", ""),
                    company=p.get("company", ""),
                    email=p.get("email", ""),
                    pipeline_stage="drafted",
                    status_reason="message_generated",
                )
            except Exception as e:
                logger.error(f"Message generation failed for {p['name']}: {e}")
                message = "(message generation failed)"
                generation_failed = True
                job_queue.fail_job(message_job.id, error=str(e), retry=True)
                job_queue.record_lifecycle_event(
                    str(prospect_id),
                    LifecycleEventType.BLOCKED,
                    payload={"reason": "generation_failed", "detail": str(e)},
                    name=p.get("name", ""),
                    company=p.get("company", ""),
                    email=p.get("email", ""),
                    pipeline_stage="blocked_generation",
                    status_reason=str(e),
                    sync_funnel=False,
                )

            row = {
                **p,
                "email_found": p.get("email", ""),
                "generated_message": message,
                "generated_at": datetime.now().isoformat(),
                "message_version": "",
                "generator_version": "",
                "guard_version": "",
                "message_hash": "",
                "cohort_id": "",
            }
            if generation_failed:
                row["email_status"] = "blocked:generation_failed"
                p["status"] = "blocked"
            output_rows.append(row)

            if generation_failed and HARD_FAIL_ON_GENERATION_ERROR:
                batch_aborted = True
                batch_abort_reason = f"generation_failed for {p.get('name', '')} @ {p.get('company', '')}"
                print(
                    "\n[fail] Generation failure encountered. Stopping further processing."
                )
                logger.error(
                    "Batch aborted after generation failure: %s", batch_abort_reason
                )
                break

            # Notion sync (primary) — tracked in job queue
            if NOTION_API_KEY and not DRY_RUN:
                notion_job_id = f"{p['name'].replace(' ', '_')}_{p['company'].replace(' ', '_')}_notion_{int(datetime.now().timestamp()*1000)}"
                notion_job = job_queue.add_job(
                    job_id=notion_job_id,
                    action=JobAction.NOTION_SYNC,
                    prospect_id=prospect_id,
                    context={
                        "name": p.get("name", ""),
                        "company": p.get("company", ""),
                        "role": p.get("role", ""),
                        "industry": p.get("industry", ""),
                        "pain_point": p.get("pain_point", ""),
                        "email": p.get("email", ""),
                        "linkedin": p.get("linkedin_url", ""),
                        "message": message,
                    },
                    max_retries=2,
                )
                job_queue.start_job(notion_job.id)

                try:
                    result = _notion_prospect(
                        NOTION_API_KEY,
                        NOTION_PROSPECTS_DB,
                        name=p.get("name", ""),
                        company=p.get("company", ""),
                        role=p.get("role", ""),
                        industry=p.get("industry", ""),
                        pain_point=p.get("pain_point", ""),
                        email=p.get("email", ""),
                        linkedin=p.get("linkedin_url", ""),
                        message=message,
                    )
                    job_queue.complete_job(notion_job.id, result=result)
                    print(f"    {result}")
                except Exception as e:
                    logger.error(f"Notion sync failed for {p['name']}: {e}")
                    job_queue.fail_job(notion_job.id, error=str(e), retry=True)
            elif DRY_RUN:
                print(
                    f"    [dry-run] would sync to Notion: {p.get('name')} @ {p.get('company')}"
                )

            # Airtable sync (secondary) — tracked in job queue
            if AIRTABLE_API_KEY and not DRY_RUN:
                airtable_job_id = f"{p['name'].replace(' ', '_')}_{p['company'].replace(' ', '_')}_airtable_{int(datetime.now().timestamp()*1000)}"
                airtable_job = job_queue.add_job(
                    job_id=airtable_job_id,
                    action=JobAction.AIRTABLE_SYNC,
                    prospect_id=prospect_id,
                    context={
                        "name": p.get("name"),
                        "company": p.get("company"),
                        "role": p.get("role"),
                        "industry": p.get("industry"),
                        "pain_point": p.get("pain_point"),
                        "email": p.get("email", ""),
                        "linkedin_url": p.get("linkedin_url", ""),
                        "message": message,
                    },
                    max_retries=2,
                )
                job_queue.start_job(airtable_job.id)

                try:
                    airtable_record = {
                        "Name": p.get("name"),
                        "Company": p.get("company"),
                        "Role": p.get("role"),
                        "Industry": p.get("industry"),
                        "Pain Point": p.get("pain_point"),
                        "Email": p.get("email", ""),
                        "LinkedIn": p.get("linkedin_url", ""),
                        "Status": "Outreach Ready",
                        "Generated Message": message,
                    }
                    synced = sync_to_airtable(AIRTABLE_PROSPECTS_TABLE, airtable_record)
                    if synced:
                        job_queue.complete_job(airtable_job.id, result="synced")
                        print("    [ok] Synced to Airtable")
                    else:
                        job_queue.fail_job(
                            airtable_job.id, error="Sync returned False", retry=True
                        )
                except Exception as e:
                    logger.error(f"Airtable sync failed for {p['name']}: {e}")
                    job_queue.fail_job(airtable_job.id, error=str(e), retry=True)

            # Auto-send outreach email — tracked in job queue
            if (AUTO_SEND_EMAILS or DRY_RUN) and p.get("email"):
                trust_score = job_queue.get_trust_score(str(prospect_id))
                _opp = job_queue.get_opportunity(str(prospect_id))
                state = str(
                    (_opp or {}).get("state")
                    or (_opp or {}).get("outreach_state")
                    or "COLD"
                )
                evidence_confidence = float((_opp or {}).get("evidence_score") or 0.0)
                if evidence_confidence <= 0.0:
                    evidence_confidence = (
                        0.7 if "openai error" not in message.lower() else 0.3
                    )
                cta_type = choose_cta(
                    state=state,
                    trust_score=trust_score,
                    evidence_confidence=evidence_confidence,
                )
                proposal_depth = proposal_depth_for_state(
                    state=state, evidence_confidence=evidence_confidence
                )
                qualification_inputs = qualification_inputs_for_prospect(p)
                qualification = evaluate_qualification(
                    evidence_confidence=evidence_confidence,
                    min_evidence_confidence=qualification_inputs[
                        "min_evidence_confidence"
                    ],
                    has_direct_contact=bool(p.get("email")),
                    estimated_value=qualification_inputs["estimated_value"],
                    min_viable_deal=qualification_inputs["min_viable_deal"],
                    implementation_days=qualification_inputs["implementation_days"],
                    max_delivery_days=qualification_inputs["max_delivery_days"],
                    has_compliance_risk=qualification_inputs["has_compliance_risk"],
                    capacity_available=(
                        max(job_queue.count_active_clients(), ACTIVE_CLIENTS_CURRENT)
                        < ACTIVE_CLIENT_CAPACITY
                    ),
                )
                if qualification.qualified:
                    run_health["qualified"] += 1
                row["generated_message"] = message
                lint_body = strip_outreach_signature(message).strip() or message.strip()
                ok_to_send, send_reason = is_message_sendable(lint_body)
                if not ok_to_send:
                    logger.error(f"Send blocked for {p.get('email','')}: {send_reason}")
                    row["email_status"] = f"blocked:{send_reason}"
                    block_reason = (
                        "generation_failed"
                        if send_reason.startswith("generation_failed")
                        else "message_quality_failed"
                    )
                    job_queue.log_decision(
                        "opportunity",
                        str(prospect_id),
                        "blocked_send",
                        [f"{block_reason}:{send_reason}"],
                    )
                    job_queue.log_block(
                        "opportunity",
                        str(prospect_id),
                        block_reason,
                        send_reason,
                        block_type="QUALITY_BLOCK",
                        severity="SOFT",
                    )
                    run_health["blocked"] += 1
                    job_queue.record_lifecycle_event(
                        str(prospect_id),
                        LifecycleEventType.BLOCKED,
                        payload={
                            "reason": block_reason,
                            "detail": send_reason,
                        },
                        name=p.get("name", ""),
                        company=p.get("company", ""),
                        email=p.get("email", ""),
                        pipeline_stage="blocked_quality",
                        status_reason=send_reason,
                        sync_funnel=False,
                    )
                    p["status"] = "blocked"
                    continue
                allowed_window, window_reason = can_send_now()
                if not allowed_window:
                    logger.warning(
                        f"Send blocked for {p.get('email','')}: {window_reason}"
                    )
                    row["email_status"] = f"blocked:{window_reason}"
                    job_queue.log_decision(
                        "opportunity",
                        str(prospect_id),
                        "blocked_send",
                        [f"send_window_or_pacing_failed:{window_reason}"],
                    )
                    job_queue.log_block(
                        "opportunity",
                        str(prospect_id),
                        "send_window_or_pacing_failed",
                        window_reason,
                        block_type="CAPACITY_BLOCK",
                        severity="SOFT",
                    )
                    run_health["blocked"] += 1
                    job_queue.record_lifecycle_event(
                        str(prospect_id),
                        LifecycleEventType.BLOCKED,
                        payload={
                            "reason": "send_window_or_pacing_failed",
                            "detail": window_reason,
                        },
                        name=p.get("name", ""),
                        company=p.get("company", ""),
                        email=p.get("email", ""),
                        pipeline_stage="blocked_pacing",
                        status_reason=window_reason,
                        sync_funnel=False,
                    )
                    p["status"] = "blocked"
                    continue

                firewall = final_send_check(
                    compliance_pass=not job_queue.is_suppressed(p.get("email", "")),
                    capacity_pass=(
                        max(job_queue.count_active_clients(), ACTIVE_CLIENTS_CURRENT)
                        < ACTIVE_CLIENT_CAPACITY
                    ),
                    integrity_pass=not integrity.should_block_outreach,
                    state=state,
                    qualification_pass=qualification.qualified,
                    message_lint_pass=ok_to_send,
                    request_call_cta=(
                        cta_type in {"call_optional", "calendar_allowed"}
                    ),
                )
                if not firewall.allowed:
                    row["email_status"] = f"blocked:{','.join(firewall.reasons)}"
                    job_queue.log_decision(
                        "opportunity",
                        str(prospect_id),
                        "blocked_send_firewall",
                        firewall.reasons
                        + [f"proposal_depth:{proposal_depth}", f"cta_type:{cta_type}"],
                    )
                    job_queue.log_block(
                        "opportunity",
                        str(prospect_id),
                        "firewall_block",
                        ",".join(firewall.reasons),
                        block_type=(
                            firewall.reasons[0] if firewall.reasons else "GENERAL_BLOCK"
                        ),
                        severity="SOFT",
                    )
                    run_health["blocked"] += 1
                    job_queue.record_lifecycle_event(
                        str(prospect_id),
                        LifecycleEventType.BLOCKED,
                        payload={
                            "reason": "firewall_block",
                            "reasons": firewall.reasons,
                        },
                        name=p.get("name", ""),
                        company=p.get("company", ""),
                        email=p.get("email", ""),
                        pipeline_stage="blocked_firewall",
                        status_reason=",".join(firewall.reasons),
                        sync_funnel=False,
                    )
                    p["status"] = "blocked"
                    continue

                subject = "outbound fit for your venture"
                cold_body = strip_outreach_signature(message).strip()
                mat = materialize_outbound_payload(
                    {
                        "from": f"{RESEND_FROM_NAME} <{RESEND_FROM_EMAIL}>",
                        "to": [normalize_email(p.get("email") or "")],
                        "subject": subject,
                        "cold_body_text": cold_body,
                    },
                    send_type="initial_prospect",
                )
                html = str(mat.get("html") or "")
                msg_hash = job_queue.message_hash(subject, html)
                row["message_version"] = os.environ.get(
                    "VENTURE_MESSAGE_VERSION", ""
                ).strip()
                row["generator_version"] = os.environ.get(
                    "VENTURE_GENERATOR_VERSION", ""
                ).strip()
                row["guard_version"] = os.environ.get(
                    "VENTURE_GUARD_VERSION", ""
                ).strip()
                row["message_hash"] = msg_hash
                row["cohort_id"] = os.environ.get("VENTURE_COHORT_ID", "").strip()
                feat_dict = build_feature_dict(
                    lint_body,
                    cta_type=cta_type,
                    trust_score=trust_score,
                    evidence_confidence=evidence_confidence,
                    vertical=str(p.get("industry", "") or ""),
                    state=state,
                    industry=str(p.get("industry", "") or ""),
                )
                p_reply = predict_reply_probability(
                    lint_body,
                    cta_type=cta_type,
                    trust_score=trust_score,
                    evidence_confidence=evidence_confidence,
                    vertical=str(p.get("industry", "") or ""),
                    state=state,
                    industry=str(p.get("industry", "") or ""),
                )
                weekly_outreach_volume = job_queue.count_weekly_outbound_sends(7)
                bypass_reply_intent = (
                    weekly_outreach_volume < REPLY_INTENT_VOLUME_THRESHOLD
                )

                if REPLY_INTENT_ENABLED:
                    if not bypass_reply_intent and p_reply < REPLY_INTENT_MIN_PROB:
                        row["email_status"] = f"blocked:reply_intent:{p_reply:.3f}"
                        job_queue.log_decision(
                            "opportunity",
                            str(prospect_id),
                            "blocked_reply_intent",
                            [
                                f"reply_probability:{p_reply:.4f}",
                                f"min:{REPLY_INTENT_MIN_PROB}",
                                f"weekly_sends:{weekly_outreach_volume}",
                            ],
                        )
                        job_queue.log_block(
                            "opportunity",
                            str(prospect_id),
                            "low_expected_reply_probability",
                            f"p={p_reply:.4f}",
                            block_type="QUALITY_BLOCK",
                            severity="SOFT",
                        )
                        job_queue.record_reply_intent_training(
                            str(prospect_id),
                            campaign_key="outreach_initial",
                            message_hash=msg_hash,
                            features=feat_dict,
                            predicted_prob=p_reply,
                            actual_outcome="not_sent",
                        )
                        run_health["blocked"] += 1
                        job_queue.record_lifecycle_event(
                            str(prospect_id),
                            LifecycleEventType.BLOCKED,
                            payload={
                                "reason": "low_expected_reply_probability",
                                "reply_probability": p_reply,
                                "min_prob": REPLY_INTENT_MIN_PROB,
                            },
                            name=p.get("name", ""),
                            company=p.get("company", ""),
                            email=p.get("email", ""),
                            pipeline_stage="blocked_reply_intent",
                            status_reason=f"reply_intent:{p_reply:.3f}",
                            sync_funnel=False,
                        )
                        p["status"] = "blocked"
                        continue

                email_job_id = f"{p['name'].replace(' ', '_')}_{p['company'].replace(' ', '_')}_send_{int(datetime.now().timestamp()*1000)}"
                send_job = job_queue.add_job(
                    job_id=email_job_id,
                    action=JobAction.SEND_EMAIL,
                    prospect_id=prospect_id,
                    context={
                        "to_email": p["email"],
                        "to_name": p.get("name", ""),
                        "subject": subject,
                        "cold_body_text": cold_body,
                        "html": html,
                        "campaign_key": "outreach_initial",
                        "send_type": "initial_prospect",
                    },
                    max_retries=2,
                )
                job_queue.start_job(send_job.id)

                try:
                    job_queue.log_decision(
                        "opportunity",
                        str(prospect_id),
                        "qualified_for_send",
                        [
                            "message_quality_passed",
                            "pacing_window_passed",
                            "auto_send_enabled",
                            "email_present",
                            f"state:{state}",
                            f"cta_type:{cta_type}",
                            f"proposal_depth:{proposal_depth}",
                        ],
                    )
                    job_queue.record_lifecycle_event(
                        str(prospect_id),
                        LifecycleEventType.CTA_SELECTED,
                        payload={
                            "cta_type": cta_type,
                            "proposal_depth": proposal_depth,
                            "outreach_state": state,
                        },
                        name=p.get("name", ""),
                        company=p.get("company", ""),
                        email=p.get("email", ""),
                        pipeline_stage="",
                        status_reason="",
                        sync_funnel=False,
                    )
                    sent = send_email(
                        p["email"],
                        p.get("name", ""),
                        subject,
                        cold_body,
                        prospect_id=prospect_id,
                        campaign_key="outreach_initial",
                        send_type="initial_prospect",
                        run_id=BATCH_RUN_ID,
                        send_attempt_id=str(send_job.id),
                        company=str(p.get("company") or ""),
                    )
                    if sent:
                        job_queue.complete_job(send_job.id, result="sent")
                        row["email_status"] = "sent"
                        row["sent_at"] = datetime.now().isoformat()
                        p["status"] = "sent"
                        if not cohort_message_snap_written:
                            _write_cohort_message_snapshot_once(subject, html)
                            cohort_message_snap_written = True
                        if DRY_RUN:
                            print(f"    [dry-run] Email simulated -> {p['email']}")
                        else:
                            print(f"    [ok] Email sent -> {p['email']}")
                        run_health["sent"] += 1
                        if REPLY_INTENT_ENABLED:
                            job_queue.record_reply_intent_training(
                                str(prospect_id),
                                campaign_key="outreach_initial",
                                message_hash=msg_hash,
                                features=feat_dict,
                                predicted_prob=p_reply,
                                actual_outcome="pending",
                            )
                        job_queue.record_trust_event(
                            business_id=str(prospect_id),
                            event_type="sent_initial_message",
                            trust_delta=0.2,
                            metadata={"email": p.get("email", "")},
                        )
                        job_queue.record_lifecycle_event(
                            str(prospect_id),
                            LifecycleEventType.OUTREACH_SENT,
                            payload={
                                "email": p.get("email", ""),
                                "campaign_key": "outreach_initial",
                            },
                            name=p.get("name", ""),
                            company=p.get("company", ""),
                            email=p.get("email", ""),
                            pipeline_stage="sent",
                            status_reason="initial_email_sent",
                        )
                    else:
                        job_queue.fail_job(
                            send_job.id, error="Send returned False", retry=True
                        )
                        row["email_status"] = "send_failed"
                        job_queue.log_block(
                            "opportunity",
                            str(prospect_id),
                            "provider_send_failed",
                            "send_email returned False",
                            block_type="QUALITY_BLOCK",
                            severity="SOFT",
                        )
                        run_health["blocked"] += 1
                        job_queue.record_lifecycle_event(
                            str(prospect_id),
                            LifecycleEventType.BLOCKED,
                            payload={"reason": "provider_send_failed"},
                            name=p.get("name", ""),
                            company=p.get("company", ""),
                            email=p.get("email", ""),
                            pipeline_stage="blocked_send",
                            status_reason="provider_send_failed",
                            sync_funnel=False,
                        )
                        p["status"] = "send_failed"
                except Exception as e:
                    logger.error(f"Email send failed for {p['email']}: {e}")
                    job_queue.fail_job(send_job.id, error=str(e), retry=True)
                    row["email_status"] = "send_failed"
                    job_queue.log_block(
                        "opportunity",
                        str(prospect_id),
                        "provider_send_exception",
                        str(e),
                        block_type="QUALITY_BLOCK",
                        severity="SOFT",
                    )
                    run_health["blocked"] += 1
                    job_queue.record_lifecycle_event(
                        str(prospect_id),
                        LifecycleEventType.BLOCKED,
                        payload={"reason": "provider_send_exception", "detail": str(e)},
                        name=p.get("name", ""),
                        company=p.get("company", ""),
                        email=p.get("email", ""),
                        pipeline_stage="blocked_send",
                        status_reason=str(e),
                        sync_funnel=False,
                    )
                    p["status"] = "send_failed"

        for p, row in zip(prospects, output_rows):
            st = str(p.get("status", "pending")).lower()
            if st in ("sent", "blocked", "send_failed"):
                continue
            es = (row.get("email_status") or "").lower()
            if "blocked" in es or es.startswith("blocked"):
                p["status"] = "blocked"
            elif es == "send_failed" or "send_failed" in es:
                p["status"] = "send_failed"
            elif row.get("sent_at") or es == "sent":
                p["status"] = "sent"
            elif row.get("generated_message"):
                gm = row.get("generated_message") or ""
                if "[openai error" not in gm.lower():
                    p["status"] = "generated"

        # Save output (merge so prior outreach rows are not dropped — follow-ups depend on this file)
        merge_generated_outreach_csv(OUTPUT_FILE, all_fields, output_rows)
        if not DRY_RUN:
            sync_prospect_status_to_source_csv(PROSPECTS_FILE, prospects)

        if batch_aborted:
            job_queue.log_decision(
                "system",
                "generation_batch",
                "aborted",
                [batch_abort_reason],
            )
            print(f"\n[fail] Batch stopped early: {batch_abort_reason}")
            raise SystemExit(8)

        # Sync KPI
        if NOTION_API_KEY and not DRY_RUN and KPI_FILE.exists():
            print("\n--- KPI Sync ---")
            with open(KPI_FILE, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            if rows:
                last = rows[-1]
                result = _notion_kpi(
                    NOTION_API_KEY,
                    NOTION_KPIS_DB,
                    week_ending=last.get("week_ending", ""),
                    outreach=last.get("outreach_sent", "0"),
                    replies=last.get("positive_replies", "0"),
                    calls=last.get("calls_held", "0"),
                    closed=last.get("clients_closed", "0"),
                    revenue=last.get("monthly_revenue", "0"),
                    churn=last.get("churn", "0"),
                    notes=last.get("notes", ""),
                )
                print(f"  KPI sync: {result}")

    fc_7d = job_queue.get_funnel_counts(days=7)
    sent_trailing = int(fc_7d.get("email_sent", 0) or 0)
    rep_trailing = int(fc_7d.get("replied", 0) or 0)
    rr_est = round(rep_trailing / sent_trailing, 4) if sent_trailing else 0.0
    run_health["reply_rate_estimate"] = rr_est
    job_queue.save_funnel_health_snapshot(
        dry_run=DRY_RUN,
        generated=run_health["generated"],
        qualified=run_health["qualified"],
        sent=run_health["sent"],
        blocked=run_health["blocked"],
        reply_rate_estimate=rr_est,
        extra={
            "weekly_email_sent_trailing": sent_trailing,
            "weekly_replied_trailing": rep_trailing,
            "reply_intent_volume_threshold": REPLY_INTENT_VOLUME_THRESHOLD,
        },
    )

    # Log job queue summary
    summary = job_queue.get_summary()
    logger.info(f"Job queue summary: {summary}")
    print(f"\nJob Queue Summary:")
    print(
        f"  Pending: {summary['pending']} | Completed: {summary['completed']} | "
        f"Failed: {summary['failed']} | Abandoned: {summary['abandoned']}"
    )

    # Auto follow-up check for stale prospects
    if AUTO_SEND_EMAILS or DRY_RUN:
        print("\n--- Follow-up Check ---")
        if ENABLE_FOLLOWUPS:
            check_and_send_followups(config)
        else:
            print("  Skipped: ENABLE_FOLLOWUPS is not true.")

    # Email KPI digest to yourself
    send_digest_email()

    phase1_snapshot_after = _capture_phase1_snapshot()
    summary_before = phase1_snapshot_before.get("job_summary", {})
    summary_after = phase1_snapshot_after.get("job_summary", {})
    phase1_structured = {
        "version": 1,
        "window": {
            "pipeline_started_at_utc": phase1_pipeline_started_at,
            "pipeline_finished_at_utc": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        },
        "events": [
            {
                "event": "queue_operations",
                "job_summary_before": summary_before,
                "job_summary_after": summary_after,
                "jobs_total_delta": int(phase1_snapshot_after["jobs_total"])
                - int(phase1_snapshot_before["jobs_total"]),
            },
            {
                "event": "state_transitions",
                "lifecycle_events_delta": int(
                    phase1_snapshot_after["lifecycle_events_total"]
                )
                - int(phase1_snapshot_before["lifecycle_events_total"]),
            },
            {
                "event": "governance_blocks",
                "block_logs_delta": int(phase1_snapshot_after["block_logs_total"])
                - int(phase1_snapshot_before["block_logs_total"]),
                "severity_delta": {
                    "hard": int(phase1_snapshot_after["block_logs_hard"])
                    - int(phase1_snapshot_before["block_logs_hard"]),
                    "soft": int(phase1_snapshot_after["block_logs_soft"])
                    - int(phase1_snapshot_before["block_logs_soft"]),
                    "info": int(phase1_snapshot_after["block_logs_info"])
                    - int(phase1_snapshot_before["block_logs_info"]),
                },
            },
            {
                "event": "retries_failures",
                "jobs_retry_sum_delta": int(phase1_snapshot_after["jobs_retry_sum"])
                - int(phase1_snapshot_before["jobs_retry_sum"]),
                "failed_status_delta": int(summary_after.get("failed", 0))
                - int(summary_before.get("failed", 0)),
                "abandoned_status_delta": int(summary_after.get("abandoned", 0))
                - int(summary_before.get("abandoned", 0)),
            },
            {
                "event": "operator_interventions",
                "operator_pause_blocks_delta": int(
                    phase1_snapshot_after["operator_pause_blocks_total"]
                )
                - int(phase1_snapshot_before["operator_pause_blocks_total"]),
                "operator_lifecycle_events_delta": int(
                    phase1_snapshot_after["operator_lifecycle_events_total"]
                )
                - int(phase1_snapshot_before["operator_lifecycle_events_total"]),
            },
        ],
    }

    telemetry_path = os.environ.get("VENTURE_PIPELINE_TELEMETRY_JSON", "").strip()
    if telemetry_path:
        try:
            tpath = pathlib.Path(telemetry_path).expanduser()
            tpath.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": 1,
                "dry_run": bool(DRY_RUN),
                "auto_send_emails": bool(AUTO_SEND_EMAILS),
                "job_queue_summary": dict(summary),
                "run_health": dict(run_health),
                "funnel_counts_7d": dict(fc_7d),
                "phase1_structured": phase1_structured,
            }
            tpath.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("VENTURE_PIPELINE_TELEMETRY_JSON write failed: %s", exc)

    if AUTO_SEND_EMAILS or DRY_RUN:
        print(
            "\nDone. Emails sent automatically. Check generated-outreach.csv for records.\n"
        )
    else:
        print(
            "\nDone. Open 06-sales/generated-outreach.csv to review and send messages."
        )
        print("  Tip: Set AUTO_SEND_EMAILS=true in .env to auto-send on next run.\n")


if __name__ == "__main__":
    if "--status" in sys.argv:
        print_operator_status()
        raise SystemExit(0)
    # Defense-in-depth: refuse execution unless canonical entry or dev override
    if (
        os.getenv("VENTURE_CANONICAL_ENTRY") != "1"
        and os.getenv("VENTURE_DEV_MAIN") != "1"
    ):
        print(
            "venture_pipeline.py: direct CLI is gated. Use: "
            "python 04-coding/scripts/run_daily.py --execute-outbound [--dry-run]\n"
            "For local debugging only, set VENTURE_DEV_MAIN=1.\n"
            "For production, set VENTURE_CANONICAL_ENTRY=1 via run_daily.py.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    main()
