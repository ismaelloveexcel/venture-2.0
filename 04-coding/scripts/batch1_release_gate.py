#!/usr/bin/env python3
"""
Read-only Batch 1 release gate.

This script turns the outbound safety review into a finite acceptance check.
It does not send email, mutate the real batch.lock, or read/print secrets.
"""

from __future__ import annotations

import py_compile
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from batch_guard import (  # noqa: E402
    CANONICAL_SUBJECT,
    CTA_STRING,
    DEFAULT_SIGNATURE,
    BatchGuardError,
    consume_batch_lock,
    hash_payload,
    hash_email,
    mark_execution_confirmed,
    mark_test_approved,
    register_initial_prospect_send,
    sha256_json,
)
from send_guard import SendGuardBlocked, send_email_safe  # noqa: E402


@dataclass
class GateCheck:
    name: str
    passed: bool
    detail: str = ""


def _canonical_payload(to_email: str = "operator@example.com") -> dict[str, object]:
    body = "\n".join(
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
            "",
            DEFAULT_SIGNATURE,
        ]
    )
    return {
        "from": "Ismael Sudally <sender@replypilot.ai>",
        "to": [to_email],
        "subject": CANONICAL_SUBJECT,
        "html": "<p>" + body.replace("\n", "<br>") + "</p>",
    }


def _pass(name: str, detail: str = "") -> GateCheck:
    return GateCheck(name=name, passed=True, detail=detail)


def _fail(name: str, detail: str) -> GateCheck:
    return GateCheck(name=name, passed=False, detail=detail)


def _expect_block(name: str, func, expected: str) -> GateCheck:
    try:
        func()
    except SendGuardBlocked as exc:
        detail = str(exc)
        if expected in detail:
            return _pass(name, detail)
        return _fail(name, f"blocked for unexpected reason: {detail}")
    except Exception as exc:
        return _fail(name, f"unexpected exception: {exc}")
    return _fail(name, "unexpectedly allowed")


def compile_gate() -> list[GateCheck]:
    files = [
        "batch_guard.py",
        "send_guard.py",
        "pre_send_check.py",
        "send_outreach_test.py",
        "runtime_config.py",
        "venture_pipeline.py",
        "system_state_snapshot.py",
        "batch1_release_gate.py",
    ]
    results: list[GateCheck] = []
    for filename in files:
        path = SCRIPT_DIR / filename
        try:
            py_compile.compile(str(path), doraise=True)
            results.append(_pass(f"compile:{filename}"))
        except Exception as exc:
            results.append(_fail(f"compile:{filename}", str(exc)))
    return results


def static_gate() -> list[GateCheck]:
    endpoint = "api.resend.com" + "/emails"
    matches: list[str] = []
    skip_dirs = {".git", ".venv", "node_modules", "__pycache__"}
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or any(part in skip_dirs for part in path.parts):
            continue
        if path.suffix.lower() not in {".py", ".ps1", ".md", ".json", ".txt"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if endpoint in text:
            matches.append(str(path.relative_to(REPO_ROOT)).replace("\\", "/"))
    expected = ["04-coding/scripts/send_guard.py"]
    if sorted(matches) == expected:
        return [_pass("static:single_resend_email_endpoint", ", ".join(matches))]
    return [_fail("static:single_resend_email_endpoint", f"matches={matches}")]


def send_guard_gate() -> list[GateCheck]:
    import os

    os.environ["INTERNAL_TEST_RECIPIENTS"] = "operator@example.com"
    payload = _canonical_payload()
    external_payload = _canonical_payload("prospect@example.com")

    checks = [
        _expect_block(
            "send_guard:transactional_digest_blocked",
            lambda: send_email_safe(
                payload=payload,
                api_key="fake",
                send_type="transactional_digest",
                run_id="release-gate",
                dry_run=True,
                source="release_gate",
            ),
            "transactional_digest disabled during Batch 1",
        ),
        _expect_block(
            "send_guard:test_recipient_allowlist_enforced",
            lambda: send_email_safe(
                payload=external_payload,
                api_key="fake",
                send_type="initial_test",
                run_id="release-gate",
                dry_run=True,
                source="release_gate",
            ),
            "initial_test recipients must be internal allowlisted",
        ),
        _expect_block(
            "send_guard:prospect_requires_run_id",
            lambda: send_email_safe(
                payload=payload,
                api_key="fake",
                send_type="initial_prospect",
                run_id="",
                dry_run=True,
                source="release_gate",
            ),
            "run_id is required for prospect sends",
        ),
    ]
    for blocked_type in ["initial", "test", "transactional", "followup", "retry"]:
        checks.append(
            _expect_block(
                f"send_guard:old_type_blocked:{blocked_type}",
                lambda blocked_type=blocked_type: send_email_safe(
                    payload=payload,
                    api_key="fake",
                    send_type=blocked_type,
                    run_id="release-gate",
                    dry_run=True,
                    source="release_gate",
                ),
                "send_type not allowlisted",
            )
        )
    try:
        response = send_email_safe(
            payload=payload,
            api_key="fake",
            send_type="initial_test",
            run_id="release-gate",
            dry_run=True,
            source="release_gate",
        )
        checks.append(_pass("send_guard:internal_test_dry_run_allowed", str(response.status_code)))
    except Exception as exc:
        checks.append(_fail("send_guard:internal_test_dry_run_allowed", str(exc)))
    return checks


def _manifest_for_payloads(payloads: list[dict[str, object]]) -> dict[str, object]:
    payload_hashes = sorted(hash_payload(payload) for payload in payloads)
    recipient_hashes = sorted(hash_email(str(payload["to"][0])) for payload in payloads)
    return {
        "batch_hash": sha256_json(payload_hashes),
        "batch_size": len(payloads),
        "payload_hashes": payload_hashes,
        "recipient_hashes": recipient_hashes,
    }


def lock_lifecycle_gate() -> list[GateCheck]:
    import os

    os.environ.setdefault("BATCH_LOCK_SECRET", "release-gate-local-test-secret")
    payload = _canonical_payload("prospect@example.com")
    manifest = _manifest_for_payloads([payload])
    checks: list[GateCheck] = []
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "batch.lock"
        try:
            approved = mark_test_approved(
                path=lock_path,
                manifest=manifest,
                sender_email_value="sender@replypilot.ai",
            )
            checks.append(_pass("lock:test_approval_status", str(approved.get("status"))))
            confirmed = mark_execution_confirmed(path=lock_path)
            checks.append(_pass("lock:execution_confirmed_status", str(confirmed.get("status"))))
            consumed = consume_batch_lock(
                run_id="release-gate-run",
                manifest=manifest,
                lock_path=lock_path,
            )
            if consumed.get("status") == "in_progress" and consumed.get("planned_recipients"):
                checks.append(_pass("lock:consume_records_planned_recipients"))
            else:
                checks.append(_fail("lock:consume_records_planned_recipients", str(consumed)))
            registered = register_initial_prospect_send(
                payload_hash=hash_payload(payload),
                recipient_hashes=[hash_email("prospect@example.com")],
                run_id="release-gate-run",
                lock_path=lock_path,
            )
            if registered.get("status") == "completed" and registered.get("sent_count") == 1:
                checks.append(_pass("lock:register_marks_sent_and_completed"))
            else:
                checks.append(_fail("lock:register_marks_sent_and_completed", str(registered)))
            try:
                register_initial_prospect_send(
                    payload_hash=hash_payload(payload),
                    recipient_hashes=[hash_email("prospect@example.com")],
                    run_id="release-gate-run",
                    lock_path=lock_path,
                )
                checks.append(_fail("lock:duplicate_registration_blocked", "unexpectedly allowed"))
            except BatchGuardError as exc:
                checks.append(_pass("lock:duplicate_registration_blocked", str(exc)))
        except Exception as exc:
            checks.append(_fail("lock:lifecycle", str(exc)))
    return checks


def main() -> int:
    sections = [
        ("Compile", compile_gate),
        ("Static Surface", static_gate),
        ("Send Guard", send_guard_gate),
        ("Lock Lifecycle", lock_lifecycle_gate),
    ]
    all_checks: list[GateCheck] = []
    print("Batch 1 release gate")
    for title, runner in sections:
        print(f"\n{title}")
        checks = runner()
        all_checks.extend(checks)
        for check in checks:
            marker = "PASS" if check.passed else "FAIL"
            detail = f" - {check.detail}" if check.detail else ""
            print(f"  [{marker}] {check.name}{detail}")
    failures = [check for check in all_checks if not check.passed]
    print(f"\nResult: {'PASS' if not failures else 'FAIL'} ({len(all_checks) - len(failures)}/{len(all_checks)} checks passed)")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())