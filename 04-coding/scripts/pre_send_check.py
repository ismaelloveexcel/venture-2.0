#!/usr/bin/env python3
"""
Pre-send safety check for Batch 1 and execution signal rules.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from batch_guard import BatchGuardError, LockIntegrityError, make_run_id, run_batch_preflight
from signal_rules_engine import RuleSeverity, check_system_health

BASE_PATH = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_PATH / ".env"
load_dotenv(ENV_FILE, override=True)


def _mode(args: argparse.Namespace) -> str:
    if args.mode:
        return args.mode
    return "live" if os.environ.get("AUTO_SEND_EMAILS", "false").lower() == "true" else "dry-run"


def _print_batch_result(result: dict) -> None:
    print(f"\nBatch 1 preflight: {'PASS' if result['ok'] else 'FAIL'}")
    print(f"  run_id: {result['run_id']}")
    print(f"  mode: {result['mode']}")
    print(f"  batch_size: {result['manifest']['batch_size']}")
    print(f"  batch_hash: {result['manifest']['batch_hash']}")
    print(f"  log_file: {result['log_file']}")
    failures = [c for c in result["checks"] if not c["passed"] and c["severity"] == "FAIL"]
    warnings = [c for c in result["checks"] if not c["passed"] and c["severity"] == "WARN"]
    if failures:
        print("\nBlocking checks:")
        for check in failures[:12]:
            print(f"  - {check['name']}: {check['detail']}")
        if len(failures) > 12:
            print(f"  - ... {len(failures) - 12} more in the preflight log")
    if warnings:
        print("\nWarnings:")
        for check in warnings[:8]:
            print(f"  - {check['name']}: {check['detail']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch 1 pre-send safety check")
    parser.add_argument("--force", action="store_true", help="allow signal-rule warnings only")
    parser.add_argument("--mode", choices=("dry-run", "test", "live"))
    parser.add_argument("--run-id")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("PRE-SEND SAFETY CHECK")
    print("=" * 60)

    severity, diagnosis, rules = check_system_health(BASE_PATH / "execution_state.json")
    print(f"\nSystem Health: {severity.value}")
    print(f"Primary Diagnosis: {diagnosis}")
    if rules:
        print(f"Triggered signal rules ({len(rules)}):")
        for rule in rules:
            print(f"  - {rule['severity']} {rule['rule_id']}: {rule['diagnosis']}")
    else:
        print("Signal rules: no issues detected")

    run_id = args.run_id or make_run_id("preflight")
    mode = _mode(args)
    try:
        batch_result = run_batch_preflight(
            mode=mode,
            run_id=run_id,
            sender_email=os.environ.get("RESEND_FROM_EMAIL", "").strip(),
            sender_name=os.environ.get("RESEND_FROM_NAME", "Ismael Sudally").strip(),
            resend_api_key=os.environ.get("RESEND_API_KEY", "").strip(),
            write_lock_on_success=(mode == "live"),
        )
    except (BatchGuardError, LockIntegrityError) as exc:
        print(f"\n[fail] batch.lock integrity failure: {exc}")
        return 2
    _print_batch_result(batch_result)

    if not batch_result["ok"]:
        print("\nEXECUTION PAUSED: Batch 1 gate failed.")
        return 1

    if severity == RuleSeverity.HARD_STOP:
        print("\nEXECUTION PAUSED: signal rules reported HARD_STOP.")
        return 1
    if severity == RuleSeverity.WARNING and not args.force:
        print("\nEXECUTION PAUSED: signal-rule warning requires --force.")
        return 1

    print("\nREADY TO SEND")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
