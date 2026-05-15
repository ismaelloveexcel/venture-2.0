#!/usr/bin/env python3
"""
Single source of truth for the fast pytest list (bridge validate + pre-push hook).

Full suite: CI runs `pytest tests -q`. Do not duplicate paths in run_daily / .pre-commit-config.yaml.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Paths relative to repository root.
FAST_TEST_PATHS: tuple[str, ...] = (
    "tests/test_money_path_safety.py",
    "tests/test_run_report_contract.py",
    "tests/test_v14_metrics_io.py",
    "tests/test_money_path_gates.py",
    "tests/test_prospect_validation.py",
    "tests/test_record_outbound_upsert.py",
    "tests/test_strict_prospect_mode.py",
    "tests/test_prospect_gate.py",
    "tests/test_outbound_eligibility.py",
    "tests/test_prospect_audit_parity.py",
    "tests/test_operator_ux.py",
    "tests/test_unsubscribe_compliance.py",
    "tests/test_send_states.py",
    "tests/test_webhook_idempotency.py",
    "tests/test_snapshot_immutability.py",
    "tests/test_state_machine.py",
    "tests/test_phase_b_extras.py",
    "tests/test_launch_phase_c.py",
    "tests/test_emergency_pause.py",
)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [sys.executable, "-m", "pytest", *FAST_TEST_PATHS, "-q"],
        cwd=str(root),
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
