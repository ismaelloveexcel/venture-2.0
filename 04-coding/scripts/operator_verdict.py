#!/usr/bin/env python3
"""
Operator GO/HOLD verdict engine.

Reads system snapshot + policy + KPI trend and emits one deterministic decision
for the daily operator loop.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import sys
from typing import Any


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent.parent


def _read_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_latest_kpi(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        return rows[-1] if rows else {}
    except Exception:
        return {}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_verdict(*, daily_exit: int, guard_exit: int) -> dict[str, Any]:
    repo = _repo_root()
    cfg = repo / "04-coding" / "venture-engine" / "config"

    state = _read_json(cfg / "system_state.json")
    policy = _read_json(cfg / "policy.json")
    kpi = _read_latest_kpi(repo / "07-kpis" / "weekly-kpi-data.csv")

    mode = str(policy.get("mode", "UNKNOWN"))
    velocity = str(policy.get("send_velocity", "unknown"))

    dlq_count = int(_to_float(state.get("dlq_count"), 0))
    failure_rate = _to_float(state.get("failure_rate_24h"), 0.0)
    send_volume_24h = int(_to_float(state.get("send_volume_24h"), 0))
    reply_rate_7d = _to_float(state.get("reply_rate_7d"), 0.0)

    outreach_sent_week = int(_to_float(kpi.get("outreach_sent"), 0))
    monthly_revenue = _to_float(kpi.get("monthly_revenue"), 0.0)
    revenue_target = _to_float(os.environ.get("REVENUE_TARGET"), 10000.0)
    enforce_activity_hold = str(
        os.environ.get("VENTURE_ENFORCE_ACTIVITY_HOLD", "false")
    ).strip().lower() in {"1", "true", "yes", "on"}

    score = 100
    reasons: list[str] = []

    if daily_exit != 0:
        score -= 40
        reasons.append("ops_daily_failed")
    if guard_exit != 0:
        score -= 20
        reasons.append("health_guard_failed")
    if mode == "SAFE_MODE" or velocity == "paused":
        score -= 50
        reasons.append("policy_blocks_sends")
    if dlq_count > 0:
        score -= min(30, dlq_count * 5)
        reasons.append(f"dlq_nonzero:{dlq_count}")
    if failure_rate >= 5.0:
        score -= 20
        reasons.append(f"failure_rate_high:{failure_rate:.1f}")

    # Revenue execution pressure: no outbound activity means HOLD to force action.
    if send_volume_24h == 0 and outreach_sent_week == 0:
        score -= 25
        reasons.append("no_outbound_activity")

    # Positive signal when momentum exists.
    if send_volume_24h > 0:
        score += 5
    if reply_rate_7d >= 3.0:
        score += 5
    if monthly_revenue >= revenue_target:
        score += 5

    score = max(0, min(100, score))

    no_activity_hold = (
        send_volume_24h == 0
        and outreach_sent_week == 0
        and monthly_revenue < revenue_target
        and enforce_activity_hold
    )

    hard_hold = (
        daily_exit != 0
        or guard_exit != 0
        or mode == "SAFE_MODE"
        or velocity == "paused"
        or no_activity_hold
    )

    verdict = "GO"
    if hard_hold or score < 70:
        verdict = "HOLD"

    if not reasons:
        reasons.append("healthy_controls")

    return {
        "verdict": verdict,
        "score": score,
        "mode": mode,
        "velocity": velocity,
        "daily_exit": int(daily_exit),
        "guard_exit": int(guard_exit),
        "dlq_count": dlq_count,
        "failure_rate_24h": round(failure_rate, 2),
        "send_volume_24h": send_volume_24h,
        "reply_rate_7d": round(reply_rate_7d, 2),
        "monthly_revenue": monthly_revenue,
        "revenue_target": revenue_target,
        "enforce_activity_hold": enforce_activity_hold,
        "reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit daily GO/HOLD operator verdict")
    parser.add_argument("--daily-exit", type=int, default=0)
    parser.add_argument("--guard-exit", type=int, default=0)
    args = parser.parse_args()

    verdict = build_verdict(daily_exit=args.daily_exit, guard_exit=args.guard_exit)
    print(json.dumps(verdict, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
