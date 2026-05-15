"""
Single guarded chokepoint for Resend email sends.

Owns: Batch-1 MIME (text + html), preview div, signature + compliance footers,
List-Unsubscribe headers when configured, per-send jitter, mandatory suppression
re-check before live POST, and the only Resend outbound POST URL for /emails.
"""

from __future__ import annotations

import html as html_module
import json
import logging
import os
import random
import re
import time
from pathlib import Path
from typing import Any, Callable

import httpx

from batch_guard import (
    ALLOWED_SENDER_DOMAINS,
    ALLOWED_SEND_TYPES_BATCH1,
    BatchGuardError,
    TRANSACTIONAL_DIGEST_SEND_TYPE,
    hash_payload,
    normalize_sender_email,
    recipient_hashes_for_payload,
    register_initial_prospect_send,
    sender_domain,
    validate_payload,
)

logger = logging.getLogger(__name__)

ALLOWED_SEND_TYPES = ALLOWED_SEND_TYPES_BATCH1 | {
    TRANSACTIONAL_DIGEST_SEND_TYPE,
    "followup",
    "retry",
}

_RESEND_OUTBOUND_URL = "https://api.resend.com/emails"

_DEFAULT_PREVIEW = "Quick question about your client campaigns →"

_DEFAULT_SIG_TEXT = (
    "Ismael Sudally\n"
    "Founder, Auditbound\n"
    "Outbound accountability for agencies\n"
    "auditbound.io | isudally@outlook.com\n\n"
    "See how a client campaign gets reconstructed in 60 seconds:\n"
    "[CALENDLY_BOOKING_URL]"
)

_DEFAULT_SIG_HTML = (
    "<p>Ismael Sudally<br>Founder, Auditbound<br>Outbound accountability for agencies<br>"
    "<a href='https://auditbound.io'>auditbound.io</a> | "
    "<a href='mailto:isudally@outlook.com'>isudally@outlook.com</a><br>"
    "<a href='[CALENDLY_BOOKING_URL]'>See how a client campaign gets reconstructed in 60 seconds</a></p>"
)


def normalize_outbound_email(email: str) -> str:
    return (email or "").strip().lower()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _calendly_url() -> str:
    return (os.environ.get("CALENDLY_BOOKING_URL", "") or "").strip()


def _substitute_calendly(template: str) -> str:
    url = _calendly_url()
    return (template or "").replace("[CALENDLY_BOOKING_URL]", url or "https://calendly.com/YOUR_LINK")


def _email_signature_text() -> str:
    raw = (os.environ.get("EMAIL_SIGNATURE_TEXT", "") or "").strip()
    base = raw if raw else _DEFAULT_SIG_TEXT
    return _substitute_calendly(base.replace("\\n", "\n"))


def _email_signature_html() -> str:
    raw = (os.environ.get("EMAIL_SIGNATURE_HTML", "") or "").strip()
    base = raw if raw else _DEFAULT_SIG_HTML
    return _substitute_calendly(base.replace("\\n", "\n"))


def _list_unsubscribe_url() -> str:
    for key in ("LIST_UNSUBSCRIBE_URL", "UNSUBSCRIBE_HTTPS_URL", "UNSUBSCRIBE_URL"):
        v = (os.environ.get(key, "") or "").strip()
        if v:
            return v
    return ""


def _cold_plain_to_email_content_html(cold: str) -> str:
    esc = html_module.escape((cold or "").strip())
    return "<p>" + esc.replace("\n", "<br>\n") + "</p>"


def build_batch1_resend_payload(
    *,
    from_header: str,
    to: list[str],
    subject: str,
    cold_body_text: str,
) -> dict[str, Any]:
    """
    Build the final Resend JSON body for Batch-1-style sends (cold plain body only).

    Links and mailto appear only in appended signature + compliance blocks.
    """
    cold = (cold_body_text or "").strip()
    email_content_html = _cold_plain_to_email_content_html(cold)
    sig_html = _email_signature_html()
    sig_text = _email_signature_text()
    preview = (os.environ.get("EMAIL_PREVIEW_TEXT", "") or "").strip() or _DEFAULT_PREVIEW
    preview_esc = html_module.escape(preview)

    unsub_url = _list_unsubscribe_url()
    list_unsub_on = _env_bool("ENABLE_LIST_UNSUBSCRIBE", False) and bool(unsub_url)
    compliance_html = ""
    compliance_plain = ""
    headers: dict[str, str] = {}
    if list_unsub_on:
        headers["List-Unsubscribe"] = f"<{unsub_url}>"
        if _env_bool("ENABLE_LIST_UNSUBSCRIBE_POST", False):
            # Resend forwards custom headers on outbound; enable only when operator confirms provider support.
            headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        compliance_html = (
            '<p style="font-size:11px;color:#666;margin-top:16px">'
            f'Unsubscribe: <a href="{html_module.escape(unsub_url, quote=True)}">'
            f"{html_module.escape(unsub_url)}</a><br>"
            "Reply STOP to opt out of these emails."
            "</p>"
        )
        compliance_plain = f"\n\nUnsubscribe:\n{unsub_url}\n\nReply STOP to opt out.\n"
    else:
        compliance_plain = "\n\nReply STOP to opt out of these emails.\n"
        compliance_html = (
            '<p style="font-size:11px;color:#666;margin-top:16px">'
            "Reply STOP to opt out of these emails."
            "</p>"
        )

    html_body = f"""<html>
  <body>
    <div style='display:none;max-height:0;overflow:hidden;'>
      {preview_esc}
    </div>

    {email_content_html}

    <br><br>

    {sig_html}
    {compliance_html}
  </body>
</html>"""

    text_body = f"""{cold}

{sig_text}
{compliance_plain}"""

    payload: dict[str, Any] = {
        "from": from_header,
        "to": [normalize_outbound_email(x) for x in to if str(x).strip()],
        "subject": subject,
        "html": html_body.strip(),
        "text": text_body.strip(),
    }
    if headers:
        payload["headers"] = headers
    return payload


def _html_to_plain_fragment(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html or "", flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def materialize_outbound_payload(
    payload: dict[str, Any], *, send_type: str
) -> dict[str, Any]:
    """Expand cold_body_text into final Resend JSON (for logging / hashes)."""
    return _expand_payload_for_transport(dict(payload), send_type=send_type)


def _expand_payload_for_transport(
    payload: dict[str, Any],
    *,
    send_type: str,
) -> dict[str, Any]:
    """Return a shallow copy suitable for hashing and HTTP (Resend-only keys)."""
    st = (send_type or "").strip().lower()
    out = dict(payload)
    cold = out.pop("cold_body_text", None)
    if cold is not None and str(cold).strip():
        if not out.get("from") or not out.get("to") or not out.get("subject"):
            raise SendGuardBlocked("cold_body_text sends require from, to, and subject")
        merged = build_batch1_resend_payload(
            from_header=str(out["from"]),
            to=list(out["to"]) if isinstance(out["to"], list) else [str(out["to"])],
            subject=str(out["subject"]),
            cold_body_text=str(cold),
        )
        merged.update({k: v for k, v in out.items() if k not in ("html", "text", "headers")})
        return merged
    # Legacy: html-only (digest / retries). Ensure text companion for validators.
    if out.get("html") and not out.get("text"):
        out["text"] = _html_to_plain_fragment(str(out["html"]))
    return out


def _maybe_suppression_block(
    payload: dict[str, Any],
    *,
    is_suppressed: Callable[[str], bool] | None,
) -> None:
    if not _env_bool("ENABLE_SUPPRESSION_CHECKS", False):
        return
    check = is_suppressed
    if check is None:
        try:
            import sys

            repo = Path(__file__).resolve().parents[2]
            mcp = repo / "venture-mcp-server"
            if str(mcp) not in sys.path:
                sys.path.insert(0, str(mcp))
            from runtime_config import resolve_data_base, resolve_venture_db_path  # noqa: PLC0415
            from job_queue import get_queue  # noqa: PLC0415

            base = resolve_data_base()
            repo = Path(__file__).resolve().parents[2]
            db_path = str(resolve_venture_db_path(base, repo))
            jq = get_queue(db_path=db_path)

            def check(email: str) -> bool:  # type: ignore[misc]
                return jq.is_suppressed(email)

        except Exception as exc:  # noqa: BLE001
            raise SendGuardBlocked(f"suppression check unavailable: {exc}") from exc
    raw_to = payload.get("to") or []
    values = raw_to if isinstance(raw_to, list) else [raw_to]
    for value in values:
        em = normalize_outbound_email(str(value))
        if em and check(em):
            raise SendGuardBlocked(f"recipient suppressed (re-check): {em}")


def _maybe_outreach_frozen_block() -> None:
    """Hard block live sends when system_control outreach_frozen is true."""
    try:
        import sys

        repo = Path(__file__).resolve().parents[2]
        mcp = repo / "venture-mcp-server"
        if str(mcp) not in sys.path:
            sys.path.insert(0, str(mcp))
        from runtime_config import resolve_data_base, resolve_venture_db_path  # noqa: PLC0415
        from job_queue import get_queue  # noqa: PLC0415

        base = resolve_data_base()
        db_path = str(resolve_venture_db_path(base, repo))
        jq = get_queue(db_path=db_path)
        if jq.is_outreach_frozen():
            raise SendGuardBlocked("outreach_frozen (delivery health or operator hold)")
    except SendGuardBlocked:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SendGuardBlocked(f"outreach freeze check unavailable: {exc}") from exc


def _maybe_delivery_ratio_gate(*, send_type: str) -> None:
    """Soft log / hard block from rolling bounce + complaint ratios (money-path sends)."""
    st = (send_type or "").strip().lower()
    if st not in {"initial_prospect", "followup", "retry"}:
        return
    if os.environ.get("VENTURE_DELIVERY_HEALTH_GATES", "true").lower() not in (
        "1",
        "true",
        "yes",
    ):
        return
    try:
        import sys

        repo = Path(__file__).resolve().parents[2]
        mcp = repo / "venture-mcp-server"
        if str(mcp) not in sys.path:
            sys.path.insert(0, str(mcp))
        from runtime_config import resolve_data_base, resolve_venture_db_path  # noqa: PLC0415
        from job_queue import get_queue  # noqa: PLC0415

        base = resolve_data_base()
        db_path = str(resolve_venture_db_path(base, repo))
        jq = get_queue(db_path=db_path)
    except Exception as exc:  # noqa: BLE001
        raise SendGuardBlocked(f"delivery health check unavailable: {exc}") from exc

    min_sends = int(os.environ.get("VENTURE_DELIVERY_HEALTH_MIN_SENDS", "20") or 20)
    days = int(os.environ.get("VENTURE_DELIVERY_METRICS_DAYS", "7") or 7)
    m = jq.get_delivery_ratio_metrics(days)
    sent = int(m.get("sent") or 0)
    if sent < min_sends:
        return
    bh = float(os.environ.get("VENTURE_BOUNCE_HARD_RATIO", "0.12") or 0.12)
    ch = float(os.environ.get("VENTURE_COMPLAINT_HARD_RATIO", "0.003") or 0.003)
    bw = float(os.environ.get("VENTURE_BOUNCE_WARN_RATIO", "0.06") or 0.06)
    cw = float(os.environ.get("VENTURE_COMPLAINT_WARN_RATIO", "0.001") or 0.001)
    br = float(m.get("bounce_ratio") or 0.0)
    cr = float(m.get("complaint_ratio") or 0.0)
    detail = json.dumps(m)[:2000]
    if br >= bh:
        jq.log_block(
            "system",
            "send_guard",
            "bounce_ratio_hard_block",
            detail,
            block_type="DELIVERY_BLOCK",
            severity="HARD",
        )
        raise SendGuardBlocked("bounce_ratio_exceeds_hard_threshold")
    if cr >= ch:
        jq.log_block(
            "system",
            "send_guard",
            "complaint_ratio_hard_block",
            detail,
            block_type="DELIVERY_BLOCK",
            severity="HARD",
        )
        raise SendGuardBlocked("complaint_ratio_exceeds_hard_threshold")
    if br >= bw:
        jq.log_block(
            "system",
            "send_guard",
            "bounce_ratio_soft_warn",
            detail,
            block_type="DELIVERY_WARN",
            severity="SOFT",
        )
        logger.warning("send_guard: bounce_ratio soft warn br=%.4f", br)
    elif cr >= cw:
        jq.log_block(
            "system",
            "send_guard",
            "complaint_ratio_soft_warn",
            detail,
            block_type="DELIVERY_WARN",
            severity="SOFT",
        )
        logger.warning("send_guard: complaint_ratio soft warn cr=%.4f", cr)


class SendGuardBlocked(RuntimeError):
    """Raised when a payload is not allowed to leave via Resend."""


def _sender_from_payload(payload: dict[str, Any]) -> str:
    return normalize_sender_email(str(payload.get("from") or ""))


def _validate_sender(payload: dict[str, Any], send_type: str) -> None:
    sender = _sender_from_payload(payload)
    domain = sender_domain(sender)
    if not sender:
        raise SendGuardBlocked("RESEND_FROM_EMAIL missing from payload")
    if domain not in ALLOWED_SENDER_DOMAINS:
        raise SendGuardBlocked(f"sender domain not allowlisted: {domain or '(unset)'}")


def _split_recipients(value: str) -> set[str]:
    recipients: set[str] = set()
    for item in (value or "").replace(";", ",").split(","):
        email = normalize_sender_email(item.strip())
        if email:
            recipients.add(email)
    return recipients


def _internal_test_allowlist() -> set[str]:
    return _split_recipients(os.environ.get("OUTREACH_TEST_TO", "")) | _split_recipients(
        os.environ.get("INTERNAL_TEST_RECIPIENTS", "")
    )


def _payload_recipients(payload: dict[str, Any]) -> set[str]:
    raw_to = payload.get("to") or []
    values = raw_to if isinstance(raw_to, list) else [raw_to]
    return {normalize_outbound_email(str(value)) for value in values if str(value).strip()}


def _validate_canonical_payload(payload: dict[str, Any]) -> None:
    failures = [
        check for check in validate_payload(payload) if not check.passed and check.severity == "FAIL"
    ]
    if failures:
        raise SendGuardBlocked(
            "canonical Batch 1 payload validation failed: "
            + ", ".join(check.name for check in failures[:5])
        )


def send_email_safe(
    *,
    payload: dict[str, Any],
    api_key: str,
    send_type: str,
    run_id: str,
    dry_run: bool = False,
    source: str = "",
    is_suppressed: Callable[[str], bool] | None = None,
) -> httpx.Response:
    """Validate and send one Resend payload.

    Prospect sends must already be bound to a consumed batch.lock run.
    """
    normalized_type = (send_type or "").strip().lower()
    if normalized_type not in ALLOWED_SEND_TYPES:
        raise SendGuardBlocked(f"send_type not allowlisted: {send_type}")
    if not api_key:
        raise SendGuardBlocked("RESEND_API_KEY missing")

    expanded = _expand_payload_for_transport(payload, send_type=normalized_type)
    _validate_sender(expanded, normalized_type)

    payload_hash = hash_payload(expanded)
    if normalized_type == "initial_test":
        _validate_canonical_payload(expanded)
        allowlist = _internal_test_allowlist()
        recipients = _payload_recipients(expanded)
        if not allowlist:
            raise SendGuardBlocked("internal test recipient allowlist is empty")
        if not recipients or not recipients.issubset(allowlist):
            raise SendGuardBlocked("initial_test recipients must be internal allowlisted")
    elif normalized_type == "initial_prospect":
        _validate_canonical_payload(expanded)
        if not run_id:
            raise SendGuardBlocked("run_id is required for prospect sends")
        if not dry_run:
            try:
                register_initial_prospect_send(
                    payload_hash=payload_hash,
                    recipient_hashes=recipient_hashes_for_payload(expanded),
                    run_id=run_id,
                )
            except BatchGuardError as exc:
                raise SendGuardBlocked(str(exc)) from exc
    elif normalized_type == TRANSACTIONAL_DIGEST_SEND_TYPE:
        raise SendGuardBlocked("transactional_digest disabled during Batch 1")
    elif normalized_type in {"followup", "retry"}:
        if not expanded.get("html") and not expanded.get("text"):
            raise SendGuardBlocked("followup/retry requires html or text content")

    if dry_run:
        return httpx.Response(200, json={"id": f"dry-run:{source}:{payload_hash[:12]}"})

    _maybe_suppression_block(expanded, is_suppressed=is_suppressed)
    _maybe_outreach_frozen_block()
    _maybe_delivery_ratio_gate(send_type=normalized_type)

    jitter_lo = int(os.environ.get("SEND_JITTER_SECONDS_MIN", "30") or 30)
    jitter_hi = int(os.environ.get("SEND_JITTER_SECONDS_MAX", "90") or 90)
    if jitter_hi < jitter_lo:
        jitter_lo, jitter_hi = jitter_hi, jitter_lo
    delay_s = float(random.uniform(float(jitter_lo), float(jitter_hi)))
    logger.info(
        "send_guard jitter: sleeping %.1fs before Resend POST (caps: hourly=%s daily=%s)",
        delay_s,
        os.environ.get("SEND_HOURLY_CAP", "?"),
        os.environ.get("SEND_DAILY_CAP", "?"),
    )
    time.sleep(delay_s)

    return httpx.post(
        _RESEND_OUTBOUND_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=expanded,
        timeout=15,
    )
