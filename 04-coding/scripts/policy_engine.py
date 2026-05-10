#!/usr/bin/env python3
"""
policy_engine.py

Deterministic policy decision engine.

Consumes system_state_snapshot, evaluates against decision rules,
and persists policy decision to policy.json.

Decision outputs:
  NORMAL           - routine operation
  CONSERVATIVE     - elevated caution, slower cadence
  RESTRICTED       - severe risk, minimal sends
  SAFE_MODE        - critical issue, sends blocked

This is your "Day 9 auto-decision maker" + "system mode controller".
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypedDict

from system_state_snapshot import take_snapshot


class PolicyDecision(TypedDict):
    """Persistent policy decision persisted to policy.json."""

    decided_at: str
    mode: Literal["NORMAL", "CONSERVATIVE", "RESTRICTED", "SAFE_MODE"]
    reason: str
    followup_depth: int
    cooldown_multiplier: float
    send_velocity: Literal["normal", "slow", "paused"]
    replay_enabled: bool
    manual_reset_required: bool


def get_config_path(filename: str) -> Path:
    """Resolve config file."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent.parent
    return repo_root / "04-coding" / "venture-engine" / "config" / filename


def load_persisted_policy() -> PolicyDecision | None:
    """Load current persisted policy from policy.json."""
    path = get_config_path("policy.json")
    try:
        if path.exists():
            with open(path) as f:
                return json.load(f)
    except Exception:
        pass
    return None


def decide_policy(snapshot: dict) -> PolicyDecision:
    """
    Deterministic policy decision engine.

    Rules (evaluated in order):

    1. SAFE_MODE if:
       - DLQ count >= 10 (critical backlog)
       - OR orphan events > 0 (data integrity)
       - OR duplicate initial sends > 0 (idempotency failure)

    2. RESTRICTED if:
       - DLQ >= 5 (elevated backlog)
       - OR failure_rate_24h >= 15% (systemic failures)
       - OR cooldown_violations > 5 in 24h (policy enforcement issue)

    3. CONSERVATIVE if:
       - DLQ >= 3 (minor backlog)
       - OR failure_rate_24h >= 5% (minor failures)
       - OR reply_rate_7d < 2% (poor engagement)

    4. NORMAL otherwise
    """

    # Extract metrics
    dlq_count = snapshot.get("dlq_count", 0)
    orphans = snapshot.get("orphan_outbound_events", 0)
    duplicates = snapshot.get("duplicate_initial_sends", 0)
    failure_rate = snapshot.get("failure_rate_24h", 0.0)
    cooldown_violations = snapshot.get("cooldown_violations_24h", 0)
    reply_rate = snapshot.get("reply_rate_7d", 0.0)

    # SAFE_MODE: integrity critical
    if dlq_count >= 10 or orphans > 0 or duplicates > 0:
        return {
            "decided_at": datetime.now(timezone.utc).isoformat() + "Z",
            "mode": "SAFE_MODE",
            "reason": f"CRITICAL: dlq={dlq_count}, orphans={orphans}, duplicates={duplicates}",
            "followup_depth": 0,
            "cooldown_multiplier": 2.0,
            "send_velocity": "paused",
            "replay_enabled": False,
            "manual_reset_required": True,
        }

    # RESTRICTED: elevated risk
    if dlq_count >= 5 or failure_rate >= 15.0 or cooldown_violations > 5:
        return {
            "decided_at": datetime.now(timezone.utc).isoformat() + "Z",
            "mode": "RESTRICTED",
            "reason": f"RISK: dlq={dlq_count}, failure_rate={failure_rate}%, violations={cooldown_violations}",
            "followup_depth": 0,
            "cooldown_multiplier": 1.5,
            "send_velocity": "slow",
            "replay_enabled": True,
            "manual_reset_required": False,
        }

    # CONSERVATIVE: elevated caution
    if dlq_count >= 3 or failure_rate >= 5.0 or reply_rate < 2.0:
        return {
            "decided_at": datetime.now(timezone.utc).isoformat() + "Z",
            "mode": "CONSERVATIVE",
            "reason": f"CAUTION: dlq={dlq_count}, failure_rate={failure_rate}%, reply_rate={reply_rate}%",
            "followup_depth": 1,
            "cooldown_multiplier": 1.2,
            "send_velocity": "normal",
            "replay_enabled": True,
            "manual_reset_required": False,
        }

    # NORMAL: routine operation
    return {
        "decided_at": datetime.now(timezone.utc).isoformat() + "Z",
        "mode": "NORMAL",
        "reason": f"HEALTHY: dlq={dlq_count}, failure_rate={failure_rate}%, reply_rate={reply_rate}%",
        "followup_depth": 2,
        "cooldown_multiplier": 1.0,
        "send_velocity": "normal",
        "replay_enabled": True,
        "manual_reset_required": False,
    }


def persist_policy(decision: PolicyDecision) -> Path:
    """Write policy decision to policy.json."""
    path = get_config_path("policy.json")
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(decision, f, indent=2)

    return path


def run_policy_engine(reset_safe_mode: bool = False) -> PolicyDecision:
    """
    Main entry point for policy engine.

    Args:
        reset_safe_mode: If True, ignore persisted SAFE_MODE and re-evaluate

    Returns:
        New policy decision (always persisted)
    """
    # Load current snapshot
    snapshot = take_snapshot()

    # Load persisted policy
    current_policy = load_persisted_policy()

    # If currently in SAFE_MODE and not reset, don't auto-exit without manual intervention
    if current_policy and current_policy["mode"] == "SAFE_MODE" and not reset_safe_mode:
        # Re-evaluate to see if conditions improved
        new_decision = decide_policy(snapshot)

        # If conditions still suggest SAFE_MODE, keep it
        if new_decision["mode"] == "SAFE_MODE":
            return current_policy

        # If conditions improved but SAFE_MODE is set, stay in SAFE_MODE until manual reset
        # (Fail-closed behavior: don't auto-recover from critical)
        current_policy["decided_at"] = datetime.now(timezone.utc).isoformat() + "Z"
        persist_policy(current_policy)
        return current_policy

    # Otherwise, evaluate fresh
    decision = decide_policy(snapshot)
    persist_policy(decision)
    return decision


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Policy engine: evaluate system state and decide mode"
    )
    parser.add_argument(
        "--reset-safe-mode",
        action="store_true",
        help="Force re-evaluation from SAFE_MODE",
    )
    parser.add_argument(
        "--snapshot-only", action="store_true", help="Print snapshot only, don't decide"
    )

    args = parser.parse_args()

    try:
        if args.snapshot_only:
            snapshot = take_snapshot()
            print(json.dumps(snapshot, indent=2))
        else:
            decision = run_policy_engine(reset_safe_mode=args.reset_safe_mode)
            print(f"\nPOLICY DECISION: {decision['mode']}")
            print(f"Reason: {decision['reason']}")
            print(f"Send velocity: {decision['send_velocity']}")
            print(f"Follow-up depth: {decision['followup_depth']}")
            print(f"Manual reset required: {decision['manual_reset_required']}")
            print(f"\nFull decision persisted to policy.json")
            print(json.dumps(decision, indent=2))

        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
