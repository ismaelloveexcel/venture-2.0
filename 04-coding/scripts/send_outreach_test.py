#!/usr/bin/env python3
"""
Send one premium outbound test email to the operator before live prospect sending.

Usage:
    python 04-coding/scripts/send_outreach_test.py
    python 04-coding/scripts/send_outreach_test.py --status
    python 04-coding/scripts/send_outreach_test.py --approve
    python 04-coding/scripts/send_outreach_test.py --confirm-execution

This script never approves automatically after sending. Review the email in your
inbox first, then run --approve only when the first impression is acceptable.
Confirm execution only after the exact approved Batch 1 is ready to send.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from batch_guard import (
    BatchGuardError,
    CANONICAL_SUBJECT,
    CTA_STRING,
    build_final_payloads,
    get_test_approval_state,
    load_lock,
    make_run_id,
    manifest_for_payloads,
    mark_execution_confirmed,
    mark_test_approved,
    validate_payload,
)
from send_guard import SendGuardBlocked, build_batch1_resend_payload, send_email_safe

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
load_dotenv(ENV_FILE, override=True)
SUBJECT = CANONICAL_SUBJECT
BODY = "\n".join(
    [
        "Hi Alex,",
        "",
        "Noticed BrightOps Studio works with founder-led B2B teams on growth and acquisition.",
        "",
        "A lot of B2B service firms have a strong service, but outbound tends to break once it moves beyond referrals: unclear target accounts, inconsistent first-touch messaging, and no clear way to see what is actually working.",
        "",
        "I build client-owned outbound systems focused on one market with structured targeting, message review, sending controls, and reply tracking.",
        "",
        CTA_STRING,
    ]
)


def _mask_email(value: str) -> str:
    if "@" not in value:
        return "(unset)"
    name, domain = value.split("@", 1)
    if not name:
        return f"***@{domain}"
    return f"{name[:1]}***@{domain}"


def _env_values() -> dict[str, str]:
    return {key: os.environ.get(key, "").strip() for key in os.environ}


def _test_recipient(env: dict[str, str]) -> str:
    direct = env.get("OUTREACH_TEST_TO", "").strip()
    if direct:
        return direct.split(",", 1)[0].strip()
    internal = env.get("INTERNAL_TEST_RECIPIENTS", "").replace(";", ",").strip()
    return internal.split(",", 1)[0].strip() if internal else ""


def status() -> int:
    env = _env_values()
    recipient = _test_recipient(env)
    approved, approval_reason = get_test_approval_state()
    try:
        lock = load_lock()
    except Exception:
        lock = {}
    ready = all(
        [
            env.get("RESEND_API_KEY"),
            env.get("RESEND_FROM_EMAIL"),
            env.get("RESEND_FROM_NAME"),
            recipient,
        ]
    )
    print("Outreach test status")
    print(f"  ready_to_send_test: {ready}")
    print(f"  test_recipient: {_mask_email(recipient)}")
    print(f"  resend_api_key_set: {bool(env.get('RESEND_API_KEY'))}")
    print(f"  resend_from_email_set: {bool(env.get('RESEND_FROM_EMAIL'))}")
    print(f"  sender_name_ok: {env.get('RESEND_FROM_NAME') == 'Ismael Sudally'}")
    print(f"  approved_for_live_outreach: {approved}")
    print(f"  execution_confirmed: {bool(lock.get('execution_confirmed'))}")
    print(f"  approval_source: batch.lock ({approval_reason})")
    return 0 if ready else 1


def send_test() -> int:
    env = _env_values()
    recipient = _test_recipient(env)
    missing = [
        key
        for key in ("RESEND_API_KEY", "RESEND_FROM_EMAIL", "RESEND_FROM_NAME")
        if not env.get(key)
    ]
    if not recipient:
        missing.append("OUTREACH_TEST_TO or INTERNAL_TEST_RECIPIENTS")
    if missing:
        print("[fail] Cannot send test email; missing:")
        for key in missing:
            print(f"  - {key}")
        return 2

    payload = build_batch1_resend_payload(
        from_header=f"{env['RESEND_FROM_NAME']} <{env['RESEND_FROM_EMAIL']}>",
        to=[recipient],
        subject=SUBJECT,
        cold_body_text=BODY.strip(),
    )
    payload_failures = [
        check
        for check in validate_payload(payload)
        if not check.passed and check.severity == "FAIL"
    ]
    if payload_failures:
        print("[fail] Test payload does not match the Batch 1 canonical email:")
        for check in payload_failures:
            print(f"  - {check.name}: {check.detail}")
        return 4

    try:
        response = send_email_safe(
            payload=payload,
            api_key=env["RESEND_API_KEY"],
            send_type="initial_test",
            run_id=make_run_id("test"),
            dry_run=False,
            source="send_outreach_test",
        )
    except SendGuardBlocked as exc:
        print(f"[fail] Send guard blocked the test email: {exc}")
        return 4
    if response.status_code >= 400:
        print(f"[fail] Resend rejected the test email ({response.status_code})")
        return 3
    print(f"[ok] Test email sent to {_mask_email(recipient)}")
    print("[next] Review the inbox copy. If approved, run:")
    print("  python 04-coding/scripts/send_outreach_test.py --approve")
    return 0


def approve() -> int:
    env = _env_values()
    payloads = build_final_payloads(
        from_email=env.get("RESEND_FROM_EMAIL", ""),
        from_name=env.get("RESEND_FROM_NAME", ""),
    )
    manifest = manifest_for_payloads(payloads)
    if manifest["batch_size"] <= 0:
        print("[fail] Cannot approve: no current approved READY Batch 1 payloads found.")
        print("[hint] Generate/review the batch first, then re-run the internal test and approve.")
        return 2
    try:
        mark_test_approved(
            manifest=manifest,
            sender_email_value=env.get("RESEND_FROM_EMAIL", ""),
        )
    except BatchGuardError as exc:
        print(f"[fail] Cannot approve batch.lock: {exc}")
        return 3
    print("[ok] batch.lock test_approved=true")
    print("[gate] Run --confirm-execution only when this exact Batch 1 is ready to send.")
    return 0


def confirm_execution() -> int:
    try:
        mark_execution_confirmed()
    except (BatchGuardError, FileNotFoundError) as exc:
        print(f"[fail] Cannot confirm execution: {exc}")
        return 3
    print("[ok] batch.lock execution_confirmed=true")
    print("[gate] The next live preflight will consume this lock before sending.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Send and approve outbound test email")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--confirm-execution", action="store_true")
    args = parser.parse_args()

    if args.status:
        return status()
    if args.approve:
        return approve()
    if args.confirm_execution:
        return confirm_execution()
    return send_test()


if __name__ == "__main__":
    raise SystemExit(main())
