"""
Batch 1 send gate helpers.

This module owns the evidence used before any live prospect send:
final rendered payload validation, sender-domain checks, preflight artifacts,
and tamper-evident batch.lock reads/writes.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
LOG_DIR = REPO_ROOT / "logs"
DEFAULT_PROSPECTS_FILE = REPO_ROOT / "06-sales" / "prospects.csv"
DEFAULT_OUTPUT_FILE = REPO_ROOT / "06-sales" / "generated-outreach.csv"
DEFAULT_LOCK_FILE = REPO_ROOT / "06-sales" / "batch.lock"
DEFAULT_DB_FILE = REPO_ROOT / "venture_jobs.db"

load_dotenv(ENV_FILE, override=True)

def _csv_env_set(key: str, default: set[str]) -> set[str]:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return set(default)
    values = re.split(r"[,;\s]+", raw)
    return {value.strip().lower() for value in values if value.strip()}


ALLOWED_SENDER_DOMAINS = _csv_env_set("ALLOWED_SENDER_DOMAINS", {"abtmail.co"})
FREE_EMAIL_DOMAINS = {
    "aol.com",
    "gmail.com",
    "hotmail.com",
    "icloud.com",
    "live.com",
    "outlook.com",
    "proton.me",
    "protonmail.com",
    "yahoo.com",
}
ALLOWED_SEND_TYPES_BATCH1 = {"initial_test", "initial_prospect"}
TRANSACTIONAL_DIGEST_SEND_TYPE = "transactional_digest"
CANONICAL_SUBJECT = "outbound fit for your venture"
CTA_STRING = (
    "If this might help, hit Reply, type yes, and send — subject unchanged is fine. "
    "I will follow up with a short walkthrough. Not a fit? No need to reply."
)
MAX_BATCH1_RECIPIENTS = 5
HMAC_CONTEXT = "auditbound-batch-lock-v1"
DEFAULT_SIGNATURE = (
    "Ismael Sudally\n"
    "Founder, Auditbound\n"
    "Outbound accountability for agencies\n"
    "auditbound.io | isudally@outlook.com\n\n"
    "See how a client campaign gets reconstructed in 60 seconds:\n"
    "[CALENDLY_BOOKING_URL]"
)

FORBIDDEN_PATTERNS = (
    r"\b14-day pilot\b",
    r"\$300",
    r"\bopen to a quick\s+15[- ]?20\s+min\s+call\b",
    r"\b15[- ]?20\s+min\s+call\b",
    r"\bquick\s+call\b",
    r"\bbook\s+a\s+call\b",
    r"\bschedule\s+a\s+call\b",
    r"\bcalendly\b",
    r"\bloom\b",
    r"https?://",
    r"\bwww\.",
    r"href\s*=",
    r"mailto:",
    r"\bai-powered\b",
    r"\bai-driven\b",
    r"\bleverag(?:e|ing) ai\b",
    r"\bguarantee(?:d|s)?\b",
    r"\blead gen agency\b",
    r"\bfree audit\b",
    r"\bventure os\b",
)


class BatchGuardError(RuntimeError):
    """Base class for Batch 1 guard failures."""


class LockIntegrityError(BatchGuardError):
    """Raised when batch.lock is present but fails integrity validation."""


@dataclass(frozen=True)
class GuardCheck:
    name: str
    severity: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "severity": self.severity,
            "passed": self.passed,
            "detail": self.detail,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def make_run_id(prefix: str = "batch1") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{stamp}-{secrets.token_hex(4)}"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def hash_payload(payload: dict[str, Any]) -> str:
    return sha256_json(payload)


def hash_email(value: str) -> str:
    return hashlib.sha256((value or "").strip().lower().encode("utf-8")).hexdigest()


def recipient_hashes_for_payload(payload: dict[str, Any]) -> list[str]:
    raw_to = payload.get("to") or []
    recipients = raw_to if isinstance(raw_to, list) else [str(raw_to)]
    return sorted(hash_email(str(email)) for email in recipients if str(email).strip())


def _strip_hmac(lock: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in lock.items() if key != "hmac"}


def _read_env_lines() -> list[str]:
    if not ENV_FILE.exists():
        return []
    return ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()


def _set_env_value(key: str, value: str) -> None:
    lines = _read_env_lines()
    updated = False
    for index, line in enumerate(lines):
        if line.strip().startswith("#") or "=" not in line:
            continue
        current_key = line.split("=", 1)[0].strip()
        if current_key == key:
            lines[index] = f"{key}={value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    os.environ[key] = value


def ensure_batch_lock_secret() -> str:
    secret = os.environ.get("BATCH_LOCK_SECRET", "").strip()
    if secret:
        return secret
    secret = secrets.token_urlsafe(32)
    _set_env_value("BATCH_LOCK_SECRET", secret)
    return secret


def _current_batch_lock_secret() -> str:
    return os.environ.get("BATCH_LOCK_SECRET", "").strip()


def _lock_hmac(lock_without_hmac: dict[str, Any], secret: str) -> str:
    batch_hash = str(lock_without_hmac.get("batch_hash") or "")
    key_material = f"{HMAC_CONTEXT}:{batch_hash}:{secret}".encode("utf-8")
    key = hashlib.sha256(key_material).digest()
    return hmac.new(
        key, _canonical_json(lock_without_hmac).encode("utf-8"), hashlib.sha256
    ).hexdigest()


def sign_lock(lock_without_hmac: dict[str, Any]) -> dict[str, Any]:
    secret = ensure_batch_lock_secret()
    signed = dict(lock_without_hmac)
    signed["hmac"] = _lock_hmac(lock_without_hmac, secret)
    return signed


def verify_lock(lock: dict[str, Any]) -> None:
    provided = str(lock.get("hmac") or "")
    if not provided:
        raise LockIntegrityError("batch.lock has no hmac")
    secret = _current_batch_lock_secret()
    if not secret:
        raise LockIntegrityError("BATCH_LOCK_SECRET missing; cannot verify batch.lock")
    expected = _lock_hmac(_strip_hmac(lock), secret)
    if not hmac.compare_digest(provided, expected):
        raise LockIntegrityError("batch.lock hmac mismatch")


def load_lock(path: Path = DEFAULT_LOCK_FILE, *, allow_missing: bool = True) -> dict[str, Any]:
    if not path.exists():
        if allow_missing:
            return {}
        raise FileNotFoundError(str(path))
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LockIntegrityError(f"batch.lock is not valid JSON: {exc}") from exc
    if not isinstance(lock, dict):
        raise LockIntegrityError("batch.lock root must be an object")
    verify_lock(lock)
    ls = str(lock.get("lock_schema") or "").strip()
    if ls and ls not in ("auditbound-v1", "replypilot-v1"):
        raise LockIntegrityError(f"unsupported lock_schema: {ls}")
    return lock


def write_lock(lock_without_hmac: dict[str, Any], path: Path = DEFAULT_LOCK_FILE) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = dict(lock_without_hmac)
    body["lock_schema"] = "auditbound-v1"
    signed = sign_lock(body)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(signed, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return signed


def get_test_approval_state(path: Path = DEFAULT_LOCK_FILE) -> tuple[bool, str]:
    if not path.exists():
        return False, "batch.lock missing"
    try:
        lock = load_lock(path, allow_missing=False)
    except (FileNotFoundError, LockIntegrityError) as exc:
        return False, str(exc)
    if lock.get("test_approved") is True:
        return True, "test approved in batch.lock"
    return False, "batch.lock test_approved is not true"


def _empty_lock(batch_hash: str = "") -> dict[str, Any]:
    now = utc_now()
    return {
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "batch_hash": batch_hash,
        "batch_size": 0,
        "payload_hashes": [],
        "recipient_hashes": [],
        "sender_email": "",
        "sender_domain": "",
        "test_approved": False,
        "test_approved_at": None,
        "execution_confirmed": False,
        "execution_confirmed_at": None,
        "consumed": False,
        "consumed_at": None,
        "status": "unarmed",
        "consumed_batch_hash": None,
        "consumed_payload_hashes": [],
        "consumed_recipient_hashes": [],
        "planned_recipients": [],
        "sent_count": 0,
        "sent_payload_hashes": [],
        "sent_recipient_hashes": [],
        "completed_at": None,
        "run_id": None,
        "batch_mode": "BATCH_1",
        "mode": "unarmed",
        "lock_schema": "auditbound-v1",
    }


def mark_test_approved(
    path: Path = DEFAULT_LOCK_FILE,
    *,
    manifest: dict[str, Any] | None = None,
    sender_email_value: str = "",
) -> dict[str, Any]:
    if path.exists():
        lock = load_lock(path, allow_missing=False)
        if lock.get("consumed") is True:
            raise BatchGuardError(
                "batch.lock is consumed; regenerate/re-preflight before approving again"
            )
        lock = _strip_hmac(lock)
    else:
        lock = _empty_lock()
    if manifest:
        lock["batch_hash"] = manifest.get("batch_hash", "")
        lock["batch_size"] = int(manifest.get("batch_size") or 0)
        lock["payload_hashes"] = list(manifest.get("payload_hashes") or [])
        lock["recipient_hashes"] = list(manifest.get("recipient_hashes") or [])
    if sender_email_value:
        lock["sender_email"] = sender_email_value
        lock["sender_domain"] = sender_domain(sender_email_value)
    lock["test_approved"] = True
    lock["test_approved_at"] = utc_now()
    lock["execution_confirmed"] = False
    lock["execution_confirmed_at"] = None
    lock["consumed"] = False
    lock["consumed_at"] = None
    lock["status"] = "approved"
    lock["consumed_batch_hash"] = None
    lock["consumed_payload_hashes"] = []
    lock["consumed_recipient_hashes"] = []
    lock["planned_recipients"] = list(lock.get("recipient_hashes") or [])
    lock["sent_count"] = 0
    lock["sent_payload_hashes"] = []
    lock["sent_recipient_hashes"] = []
    lock["completed_at"] = None
    lock["run_id"] = None
    lock["batch_mode"] = "BATCH_1"
    lock["updated_at"] = utc_now()
    return write_lock(lock, path)


def mark_execution_confirmed(path: Path = DEFAULT_LOCK_FILE) -> dict[str, Any]:
    lock = load_lock(path, allow_missing=False)
    if lock.get("consumed") is True:
        raise BatchGuardError("batch.lock is already consumed; regenerate before confirming")
    if lock.get("test_approved") is not True:
        raise BatchGuardError("batch.lock test approval is not true")
    if not lock.get("batch_hash") or int(lock.get("batch_size") or 0) <= 0:
        raise BatchGuardError("batch.lock has no approved Batch 1 manifest")
    clean = _strip_hmac(lock)
    clean["execution_confirmed"] = True
    clean["execution_confirmed_at"] = utc_now()
    clean["status"] = "confirmed"
    clean["updated_at"] = utc_now()
    return write_lock(clean, path)


def normalize_sender_email(value: str) -> str:
    raw = (value or "").strip()
    if "<" in raw and ">" in raw:
        raw = raw.split("<", 1)[1].split(">", 1)[0].strip()
    return raw.lower()


def sender_domain(sender_email: str) -> str:
    email = normalize_sender_email(sender_email)
    return email.split("@", 1)[1].lower() if "@" in email else ""


def _domain_verification_proof_enabled() -> bool:
    return os.environ.get("RESEND_DOMAIN_VERIFIED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _html_to_text(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html or "", flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def _signature_anchor_line() -> str:
    raw = (os.environ.get("EMAIL_SIGNATURE_TEXT", "") or "").strip().replace("\\n", "\n")
    if raw:
        return raw.split("\n")[0].strip().lower()
    return "ismael sudally"


def _forbidden_scan_text(combined_text: str) -> str:
    """Apply link/forbidden scans only to cold copy (before signature block)."""
    raw = combined_text or ""
    anchor = _signature_anchor_line()
    idx = raw.lower().find(anchor)
    if idx == -1:
        return raw
    return raw[:idx]


def render_email_html(message: str, *, require_footer: bool, from_email: str) -> str:
    html = "<p>" + (message or "").replace("\n", "<br>") + "</p>"
    if require_footer and from_email and "unsubscribe" not in html.lower():
        html += (
            '<p style="font-size:11px;color:#666;margin-top:16px">'
            'Reply "unsubscribe" to opt out of these emails.'
            "</p>"
        )
    return html


def _load_require_unsubscribe(path: Path | None = None) -> bool:
    path = path or REPO_ROOT / "04-coding" / "venture-engine" / "config" / "compliance.config.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool((data.get("channels") or {}).get("email", {}).get("require_unsubscribe"))
    except Exception:
        return False


def _approved_message_map(output_file: Path) -> dict[str, str]:
    if not output_file.exists():
        return {}
    with output_file.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    approved: dict[str, str] = {}
    for row in rows:
        if (row.get("status") or "").strip().upper() != "PASS":
            continue
        if (row.get("approved") or "").strip().lower() != "yes":
            continue
        key = f"{(row.get('company_name') or '').strip().lower()}|{(row.get('role') or '').strip().lower()}"
        approved[key] = row.get("message") or ""
    return approved


def build_final_payloads(
    *,
    prospects_file: Path = DEFAULT_PROSPECTS_FILE,
    output_file: Path = DEFAULT_OUTPUT_FILE,
    from_email: str,
    from_name: str,
    require_footer: bool | None = None,
) -> list[dict[str, Any]]:
    if require_footer is None:
        require_footer = _load_require_unsubscribe()
    approved = _approved_message_map(output_file)
    if not prospects_file.exists():
        return []
    with prospects_file.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = set(reader.fieldnames or [])
    if not {"readiness_status", "company_name"}.issubset(fieldnames):
        return []
    payloads: list[dict[str, Any]] = []
    sender = f"{from_name} <{from_email}>" if from_name else from_email
    for row in rows:
        if (row.get("readiness_status") or "").strip().upper() != "READY":
            continue
        key = f"{(row.get('company_name') or '').strip().lower()}|{(row.get('role') or '').strip().lower()}"
        message = approved.get(key, "")
        if not message:
            continue
        email = (row.get("email") or "").strip()
        if not email:
            continue
        from send_guard import build_batch1_resend_payload  # noqa: PLC0415

        payload = build_batch1_resend_payload(
            from_header=sender,
            to=[email.strip().lower()],
            subject=CANONICAL_SUBJECT,
            cold_body_text=str(message).strip(),
        )
        payloads.append(
            {
                "payload": payload,
                "payload_hash": hash_payload(payload),
                "recipient_hash": hashlib.sha256(email.lower().encode("utf-8")).hexdigest(),
                "company_hash": hashlib.sha256(key.encode("utf-8")).hexdigest(),
                "send_type": "initial_prospect",
            }
        )
    return payloads


def manifest_for_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    payload_hashes = sorted(item["payload_hash"] for item in payloads)
    recipient_hashes = sorted(item["recipient_hash"] for item in payloads)
    return {
        "batch_hash": sha256_json(payload_hashes),
        "batch_size": len(payloads),
        "payload_hashes": payload_hashes,
        "recipient_hashes": recipient_hashes,
        "send_types": sorted({str(item.get("send_type") or "") for item in payloads}),
        "duplicate_recipient_count": len(recipient_hashes) - len(set(recipient_hashes)),
    }


def validate_payload(payload: dict[str, Any]) -> list[GuardCheck]:
    checks: list[GuardCheck] = []
    html = str(payload.get("html") or "")
    explicit_plain = str(payload.get("text") or "").strip()
    text = explicit_plain if explicit_plain else _html_to_text(html)
    lower = text.lower()
    subject = str(payload.get("subject") or "").strip()
    checks.append(
        GuardCheck(
            "subject_is_canonical",
            "FAIL",
            subject == CANONICAL_SUBJECT,
            f"subject={subject!r}",
        )
    )
    checks.append(
        GuardCheck(
            "canonical_cta_present",
            "FAIL",
            CTA_STRING.lower() in lower,
            "fixed Batch 1 CTA required",
        )
    )
    checks.append(
        GuardCheck(
            "opening_noticed_present_once",
            "FAIL",
            text.count("Noticed ") == 1,
            "exactly one Batch 1 observation line required",
        )
    )
    checks.append(
        GuardCheck(
            "audience_anchor_present",
            "FAIL",
            "a lot of b2b service firms have a strong service" in lower,
            "fixed audience anchor required",
        )
    )
    checks.append(
        GuardCheck(
            "signature_present",
            "FAIL",
            ("ismael sudally" in lower and "auditbound" in lower),
            "signature block (Auditbound) required in final body",
        )
    )
    checks.append(
        GuardCheck(
            "no_template_variables",
            "FAIL",
            re.search(r"{{.*?}}", html, flags=re.S) is None,
            "no unresolved template variables allowed",
        )
    )
    cold_scan = _forbidden_scan_text(text)
    cold_html = _forbidden_scan_text(_html_to_text(html))
    for pattern in FORBIDDEN_PATTERNS:
        hit = re.search(pattern, cold_html, flags=re.I) or re.search(pattern, cold_scan, flags=re.I)
        checks.append(
            GuardCheck(
                f"forbidden:{pattern}",
                "FAIL",
                not bool(hit),
                "forbidden Batch 1 token absent" if not hit else "forbidden token found",
            )
        )
    return checks


def _severity(mode: str, *, live_fail: bool = True) -> str:
    return "FAIL" if live_fail and mode == "live" else "WARN"


def _sender_checks(sender_email: str, mode: str) -> list[GuardCheck]:
    domain = sender_domain(sender_email)
    checks = [
        GuardCheck("sender_email_present", "FAIL", bool(sender_email), "RESEND_FROM_EMAIL required"),
        GuardCheck(
            "sender_domain_allowlisted",
            "FAIL" if mode in {"live", "test"} else "WARN",
            domain in ALLOWED_SENDER_DOMAINS,
            f"sender_domain={domain or '(unset)'}",
        ),
        GuardCheck(
            "sender_not_free_mail",
            "FAIL" if mode in {"live", "test"} else "WARN",
            domain not in FREE_EMAIL_DOMAINS,
            f"sender_domain={domain or '(unset)'}",
        ),
    ]
    return checks


def verify_resend_domain(api_key: str, sender_email: str) -> tuple[bool, str]:
    domain = sender_domain(sender_email)
    if not domain:
        return False, "sender domain missing"
    if _domain_verification_proof_enabled():
        return True, "RESEND_DOMAIN_VERIFIED=true"
    if not api_key:
        return False, "RESEND_API_KEY missing"
    try:
        response = httpx.get(
            "https://api.resend.com/domains",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if response.status_code >= 400:
            return False, f"Resend domains probe failed ({response.status_code})"
        data = response.json()
        domains = data.get("data") if isinstance(data, dict) else data
        if not isinstance(domains, list):
            return False, "Resend domains response shape unknown"
        for item in domains:
            name = str((item or {}).get("name") or "").lower()
            status = str((item or {}).get("status") or "").lower()
            if name == domain and status == "verified":
                return True, "verified"
        return False, f"{domain} not verified in Resend"
    except Exception as exc:
        return False, f"Resend domains probe error: {exc}"


def inspect_queue_state(db_path: Path = DEFAULT_DB_FILE) -> dict[str, int | bool]:
    state: dict[str, int | bool] = {
        "db_found": db_path.exists(),
        "eligible_failed_send_email_jobs": 0,
        "pending_or_in_progress_send_email_jobs": 0,
        "basic_followup_candidates_older_4d": 0,
    }
    if not db_path.exists():
        return state
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        has = lambda name: cur.execute(
            "select 1 from sqlite_master where type='table' and name=?", (name,)
        ).fetchone() is not None
        if has("jobs"):
            state["eligible_failed_send_email_jobs"] = cur.execute(
                "select count(*) from jobs where action='send_email' and status='failed' and retry_count < max_retries"
            ).fetchone()[0]
            state["pending_or_in_progress_send_email_jobs"] = cur.execute(
                "select count(*) from jobs where action='send_email' and status in ('pending','in_progress')"
            ).fetchone()[0]
        if has("outbound_events"):
            state["basic_followup_candidates_older_4d"] = cur.execute(
                "select count(*) from outbound_events o where o.send_type in ('initial','initial_prospect') and o.status='sent' "
                "and o.created_at < datetime('now','-4 days') and not exists "
                "(select 1 from outbound_events f where f.prospect_id=o.prospect_id "
                "and f.campaign_key=o.campaign_key and f.send_type='followup' and f.status='sent')"
            ).fetchone()[0]
    finally:
        con.close()
    return state


def run_batch_preflight(
    *,
    mode: str,
    run_id: str,
    sender_email: str,
    sender_name: str,
    resend_api_key: str,
    prospects_file: Path = DEFAULT_PROSPECTS_FILE,
    output_file: Path = DEFAULT_OUTPUT_FILE,
    db_path: Path = DEFAULT_DB_FILE,
    lock_path: Path = DEFAULT_LOCK_FILE,
    write_lock_on_success: bool = False,
) -> dict[str, Any]:
    mode = mode if mode in {"dry-run", "test", "live"} else "dry-run"
    checks: list[GuardCheck] = []
    checks.extend(_sender_checks(sender_email, mode))

    lock = load_lock(lock_path, allow_missing=True)

    domain_ok, domain_detail = verify_resend_domain(resend_api_key, sender_email)
    checks.append(
        GuardCheck(
            "resend_domain_verified",
            _severity(mode),
            domain_ok,
            domain_detail,
        )
    )

    payloads = build_final_payloads(
        prospects_file=prospects_file,
        output_file=output_file,
        from_email=sender_email,
        from_name=sender_name,
    )
    manifest = manifest_for_payloads(payloads)
    checks.append(
        GuardCheck("batch_has_recipients", "FAIL", manifest["batch_size"] > 0, "approved READY recipients required")
    )
    checks.append(
        GuardCheck(
            "batch_size_cap",
            "FAIL",
            manifest["batch_size"] <= MAX_BATCH1_RECIPIENTS,
            f"batch_size={manifest['batch_size']} max={MAX_BATCH1_RECIPIENTS}",
        )
    )
    checks.append(
        GuardCheck(
            "no_duplicate_recipients",
            "FAIL",
            int(manifest["duplicate_recipient_count"]) == 0,
            f"duplicate_count={manifest['duplicate_recipient_count']}",
        )
    )
    checks.append(
        GuardCheck(
            "batch1_send_types_locked",
            "FAIL",
            set(manifest.get("send_types") or []) in [set(), {"initial_prospect"}],
            f"send_types={','.join(manifest.get('send_types') or [])}",
        )
    )
    for item in payloads:
        for check in validate_payload(item["payload"]):
            checks.append(
                GuardCheck(
                    f"payload:{item['payload_hash'][:12]}:{check.name}",
                    check.severity,
                    check.passed,
                    check.detail,
                )
            )

    test_ok, test_reason = get_test_approval_state(lock_path)
    checks.append(
        GuardCheck(
            "test_approved_in_batch_lock",
            "FAIL" if mode == "live" else "WARN",
            test_ok,
            test_reason,
        )
    )
    checks.append(
        GuardCheck(
            "execution_confirmed_in_batch_lock",
            "FAIL" if mode == "live" else "WARN",
            bool(lock.get("execution_confirmed")),
            "execution_confirmed must be true before live Batch 1 sends",
        )
    )
    checks.append(
        GuardCheck(
            "lock_batch_hash_matches_payloads",
            "FAIL" if mode == "live" else "WARN",
            not lock or lock.get("batch_hash") == manifest.get("batch_hash"),
            "batch.lock manifest must match final rendered payloads",
        )
    )
    checks.append(
        GuardCheck(
            "lock_recipient_hashes_match_payloads",
            "FAIL" if mode == "live" else "WARN",
            not lock
            or sorted(lock.get("recipient_hashes") or [])
            == sorted(manifest.get("recipient_hashes") or []),
            "batch.lock recipient hashes must match final rendered payloads",
        )
    )
    checks.append(
        GuardCheck(
            "lock_sender_domain_matches_runtime",
            "FAIL" if mode == "live" else "WARN",
            not lock or lock.get("sender_domain") == sender_domain(sender_email),
            "sender domain must match the approval-phase lock",
        )
    )

    queue_state = inspect_queue_state(db_path)
    checks.append(GuardCheck("queue_db_found", "FAIL", bool(queue_state["db_found"]), "venture_jobs.db required"))
    checks.append(
        GuardCheck(
            "no_retryable_send_jobs",
            "FAIL",
            int(queue_state["eligible_failed_send_email_jobs"]) == 0,
            f"count={queue_state['eligible_failed_send_email_jobs']}",
        )
    )
    checks.append(
        GuardCheck(
            "no_pending_send_jobs",
            "FAIL",
            int(queue_state["pending_or_in_progress_send_email_jobs"]) == 0,
            f"count={queue_state['pending_or_in_progress_send_email_jobs']}",
        )
    )
    checks.append(
        GuardCheck(
            "no_followup_candidates",
            "FAIL",
            int(queue_state["basic_followup_candidates_older_4d"]) == 0,
            f"count={queue_state['basic_followup_candidates_older_4d']}",
        )
    )

    failures = [check for check in checks if not check.passed and check.severity == "FAIL"]
    ok = not failures

    lock_written = False
    if ok and write_lock_on_success and mode == "live":
        existing = lock
        if existing and existing.get("consumed") is True:
            raise BatchGuardError("batch.lock is already consumed; manual re-arm required")
        existing_clean = _strip_hmac(existing) if existing else _empty_lock(str(manifest["batch_hash"]))
        lock = {
            **existing_clean,
            "version": 1,
            "updated_at": utc_now(),
            "mode": "live",
            "batch_hash": manifest["batch_hash"],
            "batch_size": manifest["batch_size"],
            "payload_hashes": manifest["payload_hashes"],
            "recipient_hashes": manifest["recipient_hashes"],
            "sender_email": sender_email,
            "sender_domain": sender_domain(sender_email),
            "consumed": False,
            "consumed_at": None,
            "status": "confirmed" if existing_clean.get("execution_confirmed") else "approved",
        }
        write_lock(lock, lock_path)
        lock_written = True

    log_payload = {
        "run_id": run_id,
        "created_at": utc_now(),
        "mode": mode,
        "verdict": "GO" if ok else "NO_GO",
        "ok": ok,
        "lock_written": lock_written,
        "sender_domain": sender_domain(sender_email),
        "batch_hash": manifest["batch_hash"],
        "recipient_count": manifest["batch_size"],
        "failures": [
            {"name": check.name, "detail": check.detail}
            for check in checks
            if not check.passed and check.severity == "FAIL"
        ],
        "checks": [check.as_dict() for check in checks],
        "queue_state": queue_state,
    }
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / f"preflight_{run_id}.json").write_text(
        json.dumps(log_payload, indent=2) + "\n", encoding="utf-8"
    )

    return {
        "ok": ok,
        "run_id": run_id,
        "mode": mode,
        "checks": [check.as_dict() for check in checks],
        "manifest": manifest,
        "lock_written": lock_written,
        "log_file": str(LOG_DIR / f"preflight_{run_id}.json"),
    }


def consume_batch_lock(
    *,
    run_id: str,
    manifest: dict[str, Any],
    lock_path: Path = DEFAULT_LOCK_FILE,
) -> dict[str, Any]:
    lock = load_lock(lock_path, allow_missing=False)
    if lock.get("test_approved") is not True:
        raise BatchGuardError("batch.lock test approval is not true")
    if lock.get("consumed") is True:
        raise BatchGuardError("batch.lock is already consumed")
    if lock.get("execution_confirmed") is not True:
        raise BatchGuardError("batch.lock execution_confirmed is not true")
    if lock.get("batch_hash") != manifest.get("batch_hash"):
        raise BatchGuardError("batch hash changed after approval")
    if sorted(lock.get("payload_hashes") or []) != sorted(manifest.get("payload_hashes") or []):
        raise BatchGuardError("payload hashes changed after approval")
    if sorted(lock.get("recipient_hashes") or []) != sorted(manifest.get("recipient_hashes") or []):
        raise BatchGuardError("recipient hashes changed after approval")
    clean = _strip_hmac(lock)
    clean["execution_confirmed"] = False
    clean["consumed"] = True
    clean["consumed_at"] = utc_now()
    clean["run_id"] = run_id
    clean["status"] = "in_progress"
    clean["consumed_batch_hash"] = manifest.get("batch_hash")
    clean["consumed_payload_hashes"] = list(manifest.get("payload_hashes") or [])
    clean["consumed_recipient_hashes"] = list(manifest.get("recipient_hashes") or [])
    clean["planned_recipients"] = list(manifest.get("recipient_hashes") or [])
    clean["sent_count"] = 0
    clean["sent_payload_hashes"] = []
    clean["sent_recipient_hashes"] = []
    clean["completed_at"] = None
    clean["updated_at"] = utc_now()
    return write_lock(clean, lock_path)


def is_active_batch_run(run_id: str, lock_path: Path = DEFAULT_LOCK_FILE) -> bool:
    lock = load_lock(lock_path, allow_missing=True)
    return bool(lock and lock.get("consumed") is True and lock.get("run_id") == run_id)


def assert_payload_bound_to_consumed_run(
    *,
    payload_hash: str,
    recipient_hashes: list[str],
    run_id: str,
    lock_path: Path = DEFAULT_LOCK_FILE,
) -> None:
    lock = load_lock(lock_path, allow_missing=False)
    if lock.get("consumed") is not True:
        raise BatchGuardError("batch.lock has not been consumed for this run")
    if lock.get("run_id") != run_id:
        raise BatchGuardError("send run_id does not match consumed batch.lock")
    if payload_hash not in set(lock.get("consumed_payload_hashes") or []):
        raise BatchGuardError("payload hash is not bound to the consumed run")
    consumed_recipients = set(lock.get("consumed_recipient_hashes") or [])
    if not set(recipient_hashes).issubset(consumed_recipients):
        raise BatchGuardError("recipient is not bound to the consumed run")


def register_initial_prospect_send(
    *,
    payload_hash: str,
    recipient_hashes: list[str],
    run_id: str,
    lock_path: Path = DEFAULT_LOCK_FILE,
) -> dict[str, Any]:
    assert_payload_bound_to_consumed_run(
        payload_hash=payload_hash,
        recipient_hashes=recipient_hashes,
        run_id=run_id,
        lock_path=lock_path,
    )
    lock = load_lock(lock_path, allow_missing=False)
    sent_payloads = list(lock.get("sent_payload_hashes") or [])
    sent_recipients = set(lock.get("sent_recipient_hashes") or [])
    planned_payloads = list(lock.get("consumed_payload_hashes") or [])
    if len(planned_payloads) > MAX_BATCH1_RECIPIENTS:
        raise BatchGuardError("Batch 1 lock exceeds recipient cap")
    if int(lock.get("sent_count") or 0) >= MAX_BATCH1_RECIPIENTS:
        raise BatchGuardError("Batch 1 cap exceeded")
    if payload_hash in set(sent_payloads):
        raise BatchGuardError("payload already registered for this consumed run")
    if sent_recipients.intersection(recipient_hashes):
        raise BatchGuardError("recipient already registered for this consumed run")

    clean = _strip_hmac(lock)
    clean["sent_payload_hashes"] = sent_payloads + [payload_hash]
    clean["sent_recipient_hashes"] = sorted(sent_recipients.union(recipient_hashes))
    clean["sent_count"] = int(lock.get("sent_count") or 0) + 1
    if clean["sent_count"] >= len(planned_payloads):
        clean["status"] = "completed"
        clean["completed_at"] = utc_now()
    else:
        clean["status"] = "in_progress"
    clean["updated_at"] = utc_now()
    return write_lock(clean, lock_path)