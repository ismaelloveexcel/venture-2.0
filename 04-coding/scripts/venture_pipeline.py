"""
Venture OS — Full Automation Pipeline
Chains: Prospect Discovery → Email Lookup → Outreach Generation → Notion Sync → Airtable Sync → KPI Update

Run: python 04-coding/scripts/venture_pipeline.py
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
 10. Detects follow-up opportunities (no reply after FOLLOWUP_DAYS days) + auto-sends
 11. Emails you a KPI digest after every run (if DIGEST_TO_EMAIL set)
"""

import os
import csv
import json
import pathlib
import sys
from datetime import date, datetime
import logging

import httpx
from dotenv import load_dotenv
from runtime_config import RuntimeConfig, collect_config_warnings, collect_live_mode_blockers
from system_integrity_monitor import evaluate_integrity
from outreach_state_machine import proposal_depth_for_state
from cta_router import choose_cta
from qualification_guard import evaluate_qualification
from execution_firewall import final_send_check
from no_response_diagnostics import analyze_no_response_patterns

# Resilience & logging
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "venture-mcp-server"))
from resilience import hunter_api_call, openai_api_call, notion_api_call, airtable_api_call, resend_api_call
from logging_config import setup_logging
from job_queue import get_queue, JobAction, JobStatus
from lifecycle_engine import LifecycleEventType
from reply_intent import build_feature_dict, predict_reply_probability

# ── CLI flags ─────────────────────────────────────────────────────────────────
DRY_RUN = "--dry-run" in sys.argv  # print actions without sending emails or syncing

BASE = pathlib.Path(__file__).parent.parent.parent
load_dotenv(BASE / ".env")

# Setup logging to file + console
logger = setup_logging(log_dir=str(BASE / "logs"), name="venture-pipeline")
job_queue = get_queue(db_path=str(BASE / "venture_jobs.db"))

logger.info("="*80)
logger.info(f"Pipeline started (dry_run={DRY_RUN})")

PROSPECTS_FILE = BASE / "06-sales" / "prospects.csv"
OUTPUT_FILE = BASE / "06-sales" / "generated-outreach.csv"
KPI_FILE = BASE / "07-kpis" / "weekly-kpi-data.csv"
CONFIG_FILE = pathlib.Path(__file__).parent / "outreach_config.json"

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

# Import Notion helper from sibling directory
import sys as _sys
_sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "venture-mcp-server"))
from notion_helper import sync_prospect as _notion_prospect, sync_kpi as _notion_kpi

PROSPECT_FIELDS = ["name", "company", "role", "industry", "pain_point",
                   "linkedin_url", "email", "domain", "status"]


def _is_likely_notion_id(value: str) -> bool:
    """Validate Notion DB ID shape (32 hex chars, optionally hyphenated)."""
    if not value:
        return False
    normalized = value.replace("-", "")
    return len(normalized) == 32 and all(ch in "0123456789abcdefABCDEF" for ch in normalized)


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
            r = client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            )
            if r.status_code >= 400:
                failures.append(f"OpenAI probe failed ({r.status_code})")
        except Exception as exc:
            failures.append(f"OpenAI probe error: {exc}")

        try:
            r = client.get(
                "https://api.hunter.io/v2/account",
                params={"api_key": HUNTER_API_KEY},
            )
            if r.status_code >= 400:
                failures.append(f"Hunter probe failed ({r.status_code})")
        except Exception as exc:
            failures.append(f"Hunter probe error: {exc}")

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
            "system", "outreach_send", reason, "capacity hard stop",
            block_type="CAPACITY_BLOCK", severity="HARD",
        )
        raise SystemExit(4)


# ── 1. Load Config ────────────────────────────────────────────────────────────
def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {
        "service": os.environ.get("YOUR_SERVICE", "AI automation service"),
        "unique_value": os.environ.get("YOUR_UNIQUE_VALUE", "saves time, increases revenue"),
        "social_proof": os.environ.get("YOUR_SOCIAL_PROOF", "helped similar businesses"),
        "format": os.environ.get("OUTREACH_FORMAT", "LinkedIn DM"),
        "max_length": f"{os.environ.get('OUTREACH_MAX_WORDS', '80')} words",
    }


# ── 2. Load Pending Prospects ─────────────────────────────────────────────────
def load_pending_prospects() -> list[dict]:
    if not PROSPECTS_FILE.exists():
        print(f"  [!] No prospects file at {PROSPECTS_FILE}")
        print("  Creating sample file — add real prospects and run again.")
        PROSPECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PROSPECTS_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=PROSPECT_FIELDS)
            writer.writeheader()
            writer.writerow({
                "name": "Jane Smith", "company": "Bright Smiles Dental", "role": "Owner",
                "industry": "Dental", "pain_point": "Losing patients who don't rebook",
                "linkedin_url": "https://linkedin.com/in/janesmith",
                "email": "", "domain": "brightsmilesdental.com", "status": "pending"
            })
        return []
    with open(PROSPECTS_FILE, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("status", "").lower() == "pending"]


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

def generate_message(prospect: dict, config: dict) -> str:
    if not OPENAI_API_KEY:
        return (
            "[OPENAI_API_KEY not set — paste this into ChatGPT]\n"
            f"Write a {config['format']} for {prospect['name']} at {prospect['company']}, "
            f"role: {prospect['role']}, pain: {prospect['pain_point']}. Max {config['max_length']}."
        )
    prompt = f"""Write a personalised {config['format']} for this prospect.

SERVICE: {config['service']}
UNIQUE VALUE: {config['unique_value']}
SOCIAL PROOF: {config['social_proof']}

PROSPECT:
- Name: {prospect.get('name', '')}
- Company: {prospect.get('company', '')}
- Role: {prospect.get('role', '')}
- Industry: {prospect.get('industry', '')}
- Pain point: {prospect.get('pain_point', '')}

RULES: Max {config['max_length']}, conversational, specific to their situation,
soft CTA at end, no "Hope you're well", no mentioning AI unless relevant.
Write the message only."""

    try:
        r = _openai_request(prompt)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"OpenAI request failed: {e}")
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


# ── 6. Send Email via Resend ──────────────────────────────────────────────────
@resend_api_call  # Automatic retry + rate limit
def _resend_request(to_email: str, to_name: str, subject: str, html_body: str) -> httpx.Response:
    """Make raw Resend API request."""
    return httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json={
            "from": f"{RESEND_FROM_NAME} <{RESEND_FROM_EMAIL}>",
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        },
        timeout=15,
    )

def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    prospect_id: str = "",
    campaign_key: str = "outreach_initial",
) -> bool:
    """Send a transactional email via Resend API."""
    if not RESEND_API_KEY or not RESEND_FROM_EMAIL:
        return False
    can_send, reason = job_queue.can_send_outbound(
        prospect_id=prospect_id or to_email,
        campaign_key=campaign_key,
        recipient_email=to_email,
        subject=subject,
        html_body=html_body,
    )
    if not can_send:
        logger.warning(f"Send blocked for {to_email}: {reason}")
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
        r = _resend_request(to_email, to_name, subject, html_body)
        r.raise_for_status()
        job_queue.record_outbound(
            prospect_id=prospect_id or to_email,
            campaign_key=campaign_key,
            recipient_email=to_email,
            subject=subject,
            html_body=html_body,
            status="sent",
        )
        logger.info(f"Email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Resend send failed to {to_email}: {e}")
        return False


def _generate_raw(prompt: str) -> str:
    """Call OpenAI with a raw prompt string."""
    if not OPENAI_API_KEY:
        return prompt
    try:
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 150, "temperature": 0.7},
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
    blocked_markers = ("[openai error:", "[openai_api_key not set", "error calling openai")
    for marker in blocked_markers:
        if marker in text:
            return False, f"message contains failure marker: {marker}"
    if len(text.split()) < 12:
        return False, "message too short to be credible outreach"
    return True, ""


# ── 7. Follow-up Detector ─────────────────────────────────────────────────────
def check_and_send_followups(config: dict):
    """Scan generated-outreach.csv for stale prospects and auto-send follow-ups."""
    if not OUTPUT_FILE.exists():
        return
    with open(OUTPUT_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return
    updated = False
    for row in rows:
        sent_at_str = row.get("sent_at", "")
        already_followed_up = row.get("follow_up_sent", "")
        email = row.get("email_found", "") or row.get("email", "")
        if not sent_at_str or already_followed_up or not email:
            continue
        try:
            sent_at = datetime.fromisoformat(sent_at_str)
        except ValueError:
            continue
        if (datetime.now() - sent_at).days < FOLLOWUP_DAYS:
            continue
        prompt = (
            f"Write a 2-sentence follow-up to someone who hasn't replied to my initial outreach. "
            f"Name: {row.get('name', '')}. Company: {row.get('company', '')}. "
            f"I offer: {config.get('service', '')}. Be friendly, not pushy. One soft CTA."
        )
        followup_msg = _generate_raw(prompt)
        html = "<p>" + followup_msg.replace("\n", "<br>") + "</p>"
        subject = f"Re: Quick idea for {row.get('company', 'you')}"
        if job_queue.is_suppressed(email):
            logger.warning(f"Follow-up blocked (suppressed): {email}")
            continue
        sent = send_email(
            email,
            row.get("name", ""),
            subject,
            html,
            prospect_id=row.get("id", row.get("name", email)),
            campaign_key="outreach_followup",
        )
        if sent:
            row["follow_up_sent"] = "true"
            row["follow_up_sent_at"] = datetime.now().isoformat()
            prospect_id = row.get("id", row.get("name", email))
            job_queue.record_lifecycle_event(
                str(prospect_id),
                LifecycleEventType.FOLLOWUP_SENT,
                payload={"email": email},
                name=row.get("name", ""),
                company=row.get("company", ""),
                email=email,
                pipeline_stage="followup_sent",
                status_reason="automatic_followup_sent",
            )
            updated = True
            print(f"  ↩ Follow-up sent → {row.get('name')} @ {row.get('company')}")
    if updated:
        all_keys = list(rows[0].keys())
        for extra in ("follow_up_sent", "follow_up_sent_at"):
            if extra not in all_keys:
                all_keys.append(extra)
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)


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
    html = f"""
    <h2 style="font-family:sans-serif">Venture OS — Weekly KPI Digest</h2>
    <p style="color:#888">{datetime.now().strftime('%A, %B %-d %Y')}</p>
    <table style="font-family:sans-serif;border-collapse:collapse">
      <tr><td style="padding:6px 16px 6px 0">Current MRR</td><td><strong>${revenue:,.0f}</strong></td></tr>
      <tr><td style="padding:6px 16px 6px 0">Target</td><td>${REVENUE_TARGET:,.0f}</td></tr>
      <tr><td style="padding:6px 16px 6px 0">Gap</td><td>${gap:,.0f} ({pct:.0f}% of target)</td></tr>
      <tr><td style="padding:6px 16px 6px 0">4-wk Reply Rate</td><td>{rate:.1f}% (target ≥5%)</td></tr>
    </table>
    <hr>
    <p style="color:#aaa;font-size:12px">Sent automatically by Venture OS pipeline</p>
    """
    sent = send_email(
        DIGEST_TO_EMAIL, "Founder",
        f"Venture KPI Digest — {datetime.now().strftime('%b %-d')}",
        html,
    )
    if sent:
        print(f"  [ok] KPI digest emailed -> {DIGEST_TO_EMAIL}")


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
                email = lookup_email(ctx.get("first_name", ""), ctx.get("last_name", ""), ctx.get("domain", ""))
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
                    result = _notion_prospect(NOTION_API_KEY, NOTION_PROSPECTS_DB, name=ctx.get("name", ""),
                        company=ctx.get("company", ""), role=ctx.get("role", ""), industry=ctx.get("industry", ""),
                        pain_point=ctx.get("pain_point", ""), email=ctx.get("email", ""),
                        linkedin=ctx.get("linkedin", ""), message=ctx.get("message", ""))
                    job_queue.complete_job(job.id, result=result)
                    logger.info(f"Retried Notion sync: {job.id}")
                else:
                    job_queue.fail_job(job.id, error="NOTION_API_KEY not set", retry=False)
            
            elif job.action == JobAction.AIRTABLE_SYNC:
                if AIRTABLE_API_KEY:
                    ctx = job.context or {}
                    record = {"Name": ctx.get("name"), "Company": ctx.get("company"), "Role": ctx.get("role"),
                        "Industry": ctx.get("industry"), "Pain Point": ctx.get("pain_point"), "Email": ctx.get("email", ""),
                        "LinkedIn": ctx.get("linkedin_url", ""), "Status": "Outreach Ready", "Generated Message": ctx.get("message", "")}
                    synced = sync_to_airtable(AIRTABLE_PROSPECTS_TABLE, record)
                    if synced:
                        job_queue.complete_job(job.id, result="synced")
                        logger.info(f"Retried Airtable sync: {job.id}")
                    else:
                        job_queue.fail_job(job.id, error="Sync failed", retry=True)
                else:
                    job_queue.fail_job(job.id, error="AIRTABLE_API_KEY not set", retry=False)
            
            elif job.action == JobAction.SEND_EMAIL:
                ctx = job.context or {}
                sent = send_email(
                    ctx.get("to_email", ""),
                    ctx.get("to_name", ""),
                    ctx.get("subject", ""),
                    ctx.get("html", ""),
                    prospect_id=job.prospect_id or ctx.get("to_email", ""),
                    campaign_key=ctx.get("campaign_key", "outreach_initial"),
                )
                if sent:
                    job_queue.complete_job(job.id, result="sent")
                    logger.info(f"Retried email send: {job.id}")
                else:
                    job_queue.fail_job(job.id, error="Send failed", retry=True)
        
        except Exception as e:
            logger.error(f"Retry failed for {job.id}: {e}")
            job_queue.fail_job(job.id, error=str(e), retry=True)


# ── Main Pipeline ─────────────────────────────────────────────────────────────
def main():
    print("\n========================================")
    print("  VENTURE OS — AUTOMATION PIPELINE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("========================================\n")

    # Validate integration config early to avoid confusing downstream failures
    validate_integrations()
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

    # Retry failed jobs from previous runs
    retry_failed_jobs()
    
    # Clean up old completed/abandoned jobs (keep 30 days)
    deleted = job_queue.cleanup_old_jobs(days=30)
    if deleted > 0:
        logger.info(f"Cleaned up {deleted} old job records")

    config = load_config()
    prospects = load_pending_prospects()

    run_health = {"generated": 0, "qualified": 0, "sent": 0, "blocked": 0, "reply_rate_estimate": 0.0}
    if not prospects:
        print("No pending prospects. Add rows with status=pending to 06-sales/prospects.csv")
    else:
        print(f"Found {len(prospects)} pending prospects.\n")
        output_rows = []
        all_fields = PROSPECT_FIELDS + ["email_found", "generated_message", "generated_at",
                                        "email_status", "sent_at", "follow_up_sent", "follow_up_sent_at"]

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
                    last  = parts[-1] if len(parts) > 1 else ""
                    
                    # Track email lookup in job queue
                    email_job_id = f"{p['name'].replace(' ', '_')}_{p['company'].replace(' ', '_')}_email_{int(datetime.now().timestamp()*1000)}"
                    email_job = job_queue.add_job(
                        job_id=email_job_id,
                        action=JobAction.EMAIL_LOOKUP,
                        prospect_id=prospect_id,
                        context={"first_name": first, "last_name": last, "domain": domain},
                        max_retries=2
                    )
                    job_queue.start_job(email_job.id)
                    
                    try:
                        email = lookup_email(first, last, domain)
                        job_queue.complete_job(email_job.id, result=email or "not_found")
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
                    print(f"    [warn] No domain set for {p['name']} - add 'domain' column to prospects.csv to enable Hunter lookup")

            # Generate message — tracked in job queue
            message_job_id = f"{p['name'].replace(' ', '_')}_{p['company'].replace(' ', '_')}_message_{int(datetime.now().timestamp()*1000)}"
            message_job = job_queue.add_job(
                job_id=message_job_id,
                action=JobAction.GENERATE_MESSAGE,
                prospect_id=prospect_id,
                context={"prospect": p, "config": config},
                max_retries=2
            )
            job_queue.start_job(message_job.id)
            
            try:
                message = generate_message(p, config)
                job_queue.complete_job(message_job.id, result=message)
                print(f"    [ok] Message generated ({len(message.split())} words)")
                run_health["generated"] += 1
                _evidence = 0.7 if "openai error" not in message.lower() else 0.3
                job_queue.record_lifecycle_event(
                    str(prospect_id),
                    LifecycleEventType.MESSAGE_DRAFTED,
                    payload={"word_count": len(message.split()), "evidence_confidence": _evidence},
                    name=p.get("name", ""),
                    company=p.get("company", ""),
                    email=p.get("email", ""),
                    pipeline_stage="drafted",
                    status_reason="message_generated",
                )
            except Exception as e:
                logger.error(f"Message generation failed for {p['name']}: {e}")
                message = "(message generation failed)"
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

            row = {**p, "email_found": p.get("email", ""), "generated_message": message,
                   "generated_at": datetime.now().isoformat()}
            output_rows.append(row)

            # Notion sync (primary) — tracked in job queue
            if NOTION_API_KEY and not DRY_RUN:
                notion_job_id = f"{p['name'].replace(' ', '_')}_{p['company'].replace(' ', '_')}_notion_{int(datetime.now().timestamp()*1000)}"
                notion_job = job_queue.add_job(
                    job_id=notion_job_id,
                    action=JobAction.NOTION_SYNC,
                    prospect_id=prospect_id,
                    context={
                        "name": p.get("name", ""), "company": p.get("company", ""),
                        "role": p.get("role", ""), "industry": p.get("industry", ""),
                        "pain_point": p.get("pain_point", ""), "email": p.get("email", ""),
                        "linkedin": p.get("linkedin_url", ""), "message": message,
                    },
                    max_retries=2
                )
                job_queue.start_job(notion_job.id)
                
                try:
                    result = _notion_prospect(
                        NOTION_API_KEY, NOTION_PROSPECTS_DB,
                        name=p.get("name", ""), company=p.get("company", ""),
                        role=p.get("role", ""), industry=p.get("industry", ""),
                        pain_point=p.get("pain_point", ""), email=p.get("email", ""),
                        linkedin=p.get("linkedin_url", ""), message=message,
                    )
                    job_queue.complete_job(notion_job.id, result=result)
                    print(f"    {result}")
                except Exception as e:
                    logger.error(f"Notion sync failed for {p['name']}: {e}")
                    job_queue.fail_job(notion_job.id, error=str(e), retry=True)
            elif DRY_RUN:
                print(f"    [dry-run] would sync to Notion: {p.get('name')} @ {p.get('company')}")

            # Airtable sync (secondary) — tracked in job queue
            if AIRTABLE_API_KEY and not DRY_RUN:
                airtable_job_id = f"{p['name'].replace(' ', '_')}_{p['company'].replace(' ', '_')}_airtable_{int(datetime.now().timestamp()*1000)}"
                airtable_job = job_queue.add_job(
                    job_id=airtable_job_id,
                    action=JobAction.AIRTABLE_SYNC,
                    prospect_id=prospect_id,
                    context={
                        "name": p.get("name"), "company": p.get("company"),
                        "role": p.get("role"), "industry": p.get("industry"),
                        "pain_point": p.get("pain_point"), "email": p.get("email", ""),
                        "linkedin_url": p.get("linkedin_url", ""), "message": message,
                    },
                    max_retries=2
                )
                job_queue.start_job(airtable_job.id)
                
                try:
                    airtable_record = {
                        "Name": p.get("name"), "Company": p.get("company"),
                        "Role": p.get("role"), "Industry": p.get("industry"),
                        "Pain Point": p.get("pain_point"), "Email": p.get("email", ""),
                        "LinkedIn": p.get("linkedin_url", ""), "Status": "Outreach Ready",
                        "Generated Message": message,
                    }
                    synced = sync_to_airtable(AIRTABLE_PROSPECTS_TABLE, airtable_record)
                    if synced:
                        job_queue.complete_job(airtable_job.id, result="synced")
                        print("    [ok] Synced to Airtable")
                    else:
                        job_queue.fail_job(airtable_job.id, error="Sync returned False", retry=True)
                except Exception as e:
                    logger.error(f"Airtable sync failed for {p['name']}: {e}")
                    job_queue.fail_job(airtable_job.id, error=str(e), retry=True)

            # Auto-send outreach email — tracked in job queue
            if AUTO_SEND_EMAILS and p.get("email") and not DRY_RUN:
                trust_score = job_queue.get_trust_score(str(prospect_id))
                _opp = job_queue.get_opportunity(str(prospect_id))
                state = str((_opp or {}).get("state") or (_opp or {}).get("outreach_state") or "COLD")
                evidence_confidence = float((_opp or {}).get("evidence_score") or 0.0)
                if evidence_confidence <= 0.0:
                    evidence_confidence = 0.7 if "openai error" not in message.lower() else 0.3
                cta_type = choose_cta(state=state, trust_score=trust_score, evidence_confidence=evidence_confidence)
                proposal_depth = proposal_depth_for_state(state=state, evidence_confidence=evidence_confidence)
                qualification = evaluate_qualification(
                    evidence_confidence=evidence_confidence,
                    has_direct_contact=bool(p.get("email")),
                    estimated_value=1500.0,
                    min_viable_deal=1000.0,
                    implementation_days=14,
                    max_delivery_days=14,
                    has_compliance_risk=False,
                    capacity_available=(max(job_queue.count_active_clients(), ACTIVE_CLIENTS_CURRENT) < ACTIVE_CLIENT_CAPACITY),
                )
                if qualification.qualified:
                    run_health["qualified"] += 1
                ok_to_send, send_reason = is_message_sendable(message)
                if not ok_to_send:
                    logger.error(f"Send blocked for {p.get('email','')}: {send_reason}")
                    row["email_status"] = f"blocked:{send_reason}"
                    job_queue.log_decision(
                        "opportunity",
                        str(prospect_id),
                        "blocked_send",
                        [f"message_quality_failed:{send_reason}"],
                    )
                    job_queue.log_block(
                        "opportunity", str(prospect_id), "message_quality_failed", send_reason,
                        block_type="QUALITY_BLOCK", severity="SOFT",
                    )
                    run_health["blocked"] += 1
                    job_queue.record_lifecycle_event(
                        str(prospect_id),
                        LifecycleEventType.BLOCKED,
                        payload={"reason": "message_quality_failed", "detail": send_reason},
                        name=p.get("name", ""),
                        company=p.get("company", ""),
                        email=p.get("email", ""),
                        pipeline_stage="blocked_quality",
                        status_reason=send_reason,
                        sync_funnel=False,
                    )
                    continue
                allowed_window, window_reason = can_send_now()
                if not allowed_window:
                    logger.warning(f"Send blocked for {p.get('email','')}: {window_reason}")
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
                        payload={"reason": "send_window_or_pacing_failed", "detail": window_reason},
                        name=p.get("name", ""),
                        company=p.get("company", ""),
                        email=p.get("email", ""),
                        pipeline_stage="blocked_pacing",
                        status_reason=window_reason,
                        sync_funnel=False,
                    )
                    continue

                firewall = final_send_check(
                    compliance_pass=not job_queue.is_suppressed(p.get("email", "")),
                    capacity_pass=(max(job_queue.count_active_clients(), ACTIVE_CLIENTS_CURRENT) < ACTIVE_CLIENT_CAPACITY),
                    integrity_pass=not integrity.should_block_outreach,
                    state=state,
                    qualification_pass=qualification.qualified,
                    message_lint_pass=ok_to_send,
                    request_call_cta=(cta_type in {"call_optional", "calendar_allowed"}),
                )
                if not firewall.allowed:
                    row["email_status"] = f"blocked:{','.join(firewall.reasons)}"
                    job_queue.log_decision(
                        "opportunity",
                        str(prospect_id),
                        "blocked_send_firewall",
                        firewall.reasons + [f"proposal_depth:{proposal_depth}", f"cta_type:{cta_type}"],
                    )
                    job_queue.log_block(
                        "opportunity",
                        str(prospect_id),
                        "firewall_block",
                        ",".join(firewall.reasons),
                        block_type=firewall.reasons[0] if firewall.reasons else "GENERAL_BLOCK",
                        severity="SOFT",
                    )
                    run_health["blocked"] += 1
                    job_queue.record_lifecycle_event(
                        str(prospect_id),
                        LifecycleEventType.BLOCKED,
                        payload={"reason": "firewall_block", "reasons": firewall.reasons},
                        name=p.get("name", ""),
                        company=p.get("company", ""),
                        email=p.get("email", ""),
                        pipeline_stage="blocked_firewall",
                        status_reason=",".join(firewall.reasons),
                        sync_funnel=False,
                    )
                    continue

                subject = f"Quick idea for {p.get('company', 'you')}"
                html = "<p>" + message.replace("\n", "<br>") + "</p>"
                msg_hash = job_queue.message_hash(subject, html)
                feat_dict = build_feature_dict(
                    message,
                    cta_type=cta_type,
                    trust_score=trust_score,
                    evidence_confidence=evidence_confidence,
                    vertical=str(p.get("industry", "") or ""),
                    state=state,
                    industry=str(p.get("industry", "") or ""),
                )
                p_reply = predict_reply_probability(
                    message,
                    cta_type=cta_type,
                    trust_score=trust_score,
                    evidence_confidence=evidence_confidence,
                    vertical=str(p.get("industry", "") or ""),
                    state=state,
                    industry=str(p.get("industry", "") or ""),
                )
                weekly_outreach_volume = job_queue.count_weekly_outbound_sends(7)
                bypass_reply_intent = weekly_outreach_volume < REPLY_INTENT_VOLUME_THRESHOLD

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
                        "html": html,
                        "campaign_key": "outreach_initial",
                    },
                    max_retries=2
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
                        html,
                        prospect_id=prospect_id,
                        campaign_key="outreach_initial",
                    )
                    if sent:
                        job_queue.complete_job(send_job.id, result="sent")
                        row["email_status"] = "sent"
                        row["sent_at"] = datetime.now().isoformat()
                        p["status"] = "sent"
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
                            payload={"email": p.get("email", ""), "campaign_key": "outreach_initial"},
                            name=p.get("name", ""),
                            company=p.get("company", ""),
                            email=p.get("email", ""),
                            pipeline_stage="sent",
                            status_reason="initial_email_sent",
                        )
                    else:
                        job_queue.fail_job(send_job.id, error="Send returned False", retry=True)
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
            elif DRY_RUN and p.get("email"):
                print(f"    [dry-run] would email: {p['email']}")

        # Save output
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows([sanitize_csv_row(r) for r in output_rows])

        # Sync KPI
        if NOTION_API_KEY and not DRY_RUN and KPI_FILE.exists():
            print("\n--- KPI Sync ---")
            with open(KPI_FILE, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            if rows:
                last = rows[-1]
                result = _notion_kpi(
                    NOTION_API_KEY, NOTION_KPIS_DB,
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
    print(f"  Pending: {summary['pending']} | Completed: {summary['completed']} | "
          f"Failed: {summary['failed']} | Abandoned: {summary['abandoned']}")

    # Auto follow-up check for stale prospects
    if AUTO_SEND_EMAILS:
        print("\n--- Follow-up Check ---")
        check_and_send_followups(config)

    # Email KPI digest to yourself
    send_digest_email()

    if AUTO_SEND_EMAILS:
        print("\nDone. Emails sent automatically. Check generated-outreach.csv for records.\n")
    else:
        print("\nDone. Open 06-sales/generated-outreach.csv to review and send messages.")
        print("  Tip: Set AUTO_SEND_EMAILS=true in .env to auto-send on next run.\n")


if __name__ == "__main__":
    main()
