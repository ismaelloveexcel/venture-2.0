"""
Single guarded chokepoint for Resend email sends.
"""

from __future__ import annotations

from typing import Any

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

ALLOWED_SEND_TYPES = ALLOWED_SEND_TYPES_BATCH1 | {TRANSACTIONAL_DIGEST_SEND_TYPE}


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
    import os

    return _split_recipients(os.environ.get("OUTREACH_TEST_TO", "")) | _split_recipients(
        os.environ.get("INTERNAL_TEST_RECIPIENTS", "")
    )


def _payload_recipients(payload: dict[str, Any]) -> set[str]:
    raw_to = payload.get("to") or []
    values = raw_to if isinstance(raw_to, list) else [raw_to]
    return {normalize_sender_email(str(value)) for value in values if str(value).strip()}


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
) -> httpx.Response:
    """Validate and send one Resend payload.

    Prospect sends must already be bound to a consumed batch.lock run.
    """
    normalized_type = (send_type or "").strip().lower()
    if normalized_type not in ALLOWED_SEND_TYPES:
        raise SendGuardBlocked(f"send_type not allowlisted: {send_type}")
    if not api_key:
        raise SendGuardBlocked("RESEND_API_KEY missing")
    _validate_sender(payload, normalized_type)

    payload_hash = hash_payload(payload)
    if normalized_type == "initial_test":
        _validate_canonical_payload(payload)
        allowlist = _internal_test_allowlist()
        recipients = _payload_recipients(payload)
        if not allowlist:
            raise SendGuardBlocked("internal test recipient allowlist is empty")
        if not recipients or not recipients.issubset(allowlist):
            raise SendGuardBlocked("initial_test recipients must be internal allowlisted")
    elif normalized_type == "initial_prospect":
        _validate_canonical_payload(payload)
        if not run_id:
            raise SendGuardBlocked("run_id is required for prospect sends")
        if not dry_run:
            try:
                register_initial_prospect_send(
                    payload_hash=payload_hash,
                    recipient_hashes=recipient_hashes_for_payload(payload),
                    run_id=run_id,
                )
            except BatchGuardError as exc:
                raise SendGuardBlocked(str(exc)) from exc
    elif normalized_type == TRANSACTIONAL_DIGEST_SEND_TYPE:
        raise SendGuardBlocked("transactional_digest disabled during Batch 1")

    if dry_run:
        return httpx.Response(200, json={"id": f"dry-run:{source}:{payload_hash[:12]}"})

    return httpx.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )