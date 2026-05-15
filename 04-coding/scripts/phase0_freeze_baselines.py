#!/usr/bin/env python3
"""
PHASE 0: BASELINE FREEZE

Initializes frozen baseline distributions from existing shadow logs.
This MUST be executed before Phase 2 shadow mode begins.

SAFETY: Creates baseline_distributions.json once. Never overwrites.

Usage:
    python phase0_freeze_baselines.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parents[2]
SALES_DIR = BASE / "06-sales"
SHADOW_LOG_PATH = SALES_DIR / "shadow_decisions.jsonl"
BASELINE_PATH = SALES_DIR / "baseline_distributions.json"


def compute_percentile_buckets(scores: list[int]) -> dict:
    """Compute percentile buckets from sorted scores."""
    if not scores:
        return {}

    buckets = {}
    for p in [10, 20, 50, 80, 90, 95, 99]:
        idx = max(0, int((p / 100.0) * (len(scores) - 1)))
        buckets[f"p{p}"] = scores[idx]

    return buckets


def initialize_baseline_distributions(shadow_log_path: Path) -> dict:
    """Extract and freeze v2/v3 score distributions from shadow logs."""
    v2_scores, v3_scores = [], []
    record_count = 0

    if not shadow_log_path.exists():
        print(f"⚠️  Shadow log not found: {shadow_log_path}")
        print("    No prior records to freeze. Starting with empty baselines.")
        v2_scores = list(range(0, 101))
        v3_scores = list(range(0, 101))
    else:
        with shadow_log_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    record_count += 1

                    if "v2_motion_score" in record:
                        v2_scores.append(int(record["v2_motion_score"] * 10))
                    if "v3_cis" in record:
                        v3_scores.append(int(record["v3_cis"]))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue

    v2_scores.sort()
    v3_scores.sort()

    distributions = {
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "v2": {
            "count": len(v2_scores),
            "mean": int(sum(v2_scores) / len(v2_scores)) if v2_scores else 0,
            "min": min(v2_scores) if v2_scores else 0,
            "max": max(v2_scores) if v2_scores else 100,
            "scores": v2_scores,
            "percentiles": compute_percentile_buckets(v2_scores),
        },
        "v3": {
            "count": len(v3_scores),
            "mean": int(sum(v3_scores) / len(v3_scores)) if v3_scores else 0,
            "min": min(v3_scores) if v3_scores else 0,
            "max": max(v3_scores) if v3_scores else 100,
            "scores": v3_scores,
            "percentiles": compute_percentile_buckets(v3_scores),
        },
        "source_record_count": record_count,
    }

    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(distributions, indent=2), encoding="utf-8")

    return distributions


def main() -> int:
    print("\n" + "=" * 80)
    print("🔒 PHASE 0: BASELINE FREEZE")
    print("=" * 80)

    if BASELINE_PATH.exists():
        print(f"\n⚠️  Baseline file already exists: {BASELINE_PATH}")
        print("    Safety: Will not overwrite frozen baselines.")
        print("    To reset, delete the file manually and re-run this script.\n")
        return 0

    print(f"\n📊 Extracting distributions from: {SHADOW_LOG_PATH}")
    distributions = initialize_baseline_distributions(SHADOW_LOG_PATH)

    print(f"\n✅ BASELINE DISTRIBUTIONS FROZEN")
    print(f"   Location: {BASELINE_PATH}")
    print(f"\n   V2 Motion Scores:")
    print(f"   - Count: {distributions['v2']['count']}")
    print(f"   - Mean: {distributions['v2']['mean']}")
    print(f"   - Range: [{distributions['v2']['min']}, {distributions['v2']['max']}]")
    print(f"   - p50 (median): {distributions['v2']['percentiles'].get('p50', '?')}")
    print(f"\n   V3 CIS Scores:")
    print(f"   - Count: {distributions['v3']['count']}")
    print(f"   - Mean: {distributions['v3']['mean']}")
    print(f"   - Range: [{distributions['v3']['min']}, {distributions['v3']['max']}]")
    print(f"   - p50 (median): {distributions['v3']['percentiles'].get('p50', '?')}")
    print(f"\n   Source records: {distributions['source_record_count']}")
    print(f"   Frozen at: {distributions['frozen_at']}")

    print(f"\n📋 PHASE 0 COMPLETE")
    print(f"   ✓ Baselines locked (no updates during Phase 2)")
    print(f"   ✓ Ready for shadow mode execution\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
