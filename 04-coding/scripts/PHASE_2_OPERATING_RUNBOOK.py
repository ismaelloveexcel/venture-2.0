#!/usr/bin/env python3
"""
PHASE 2 OPERATIONAL RUNBOOK

Daily execution checklist + hard interpretation rules for Phase 2 shadow mode.

LOCK THESE RULES IN — no deviation.
"""

# ==================================================================================
# DAILY EXECUTION (in order, no skipping)
# ==================================================================================

DAILY_STEPS = """
1. GENERATE SHADOW DECISIONS
   cd c:\\Users\\isuda\\Dev\\VENTURE 2.0
   .venv\\Scripts\\python 04-coding/scripts/credibility_candidate_generator.py \\
     --input 06-sales/prospects.csv \\
     --shadow-mode \\
     --replace

2. COMPUTE METRICS + DECISION
   .venv\\Scripts\\python 04-coding/scripts/shadow_drift_tracker.py

3. INSPECT RESULTS
   cat 06-sales/experiment_dashboard.json

4. LOG OBSERVATION
   Record decision_status, spearman, collapse_ratio, sample_size
   (this will feed autonomous reviewer agent later)
"""

# ==================================================================================
# HARD INTERPRETATION RULES (Non-negotiable)
# ==================================================================================

INTERPRETATION_RULES = {
    "rank_correlation": {
        "description": "Spearman correlation = primary decision signal",
        "thresholds": {
            "safe_for_routing": (0.7, 1.0),          # ≥ 0.7
            "continue_observation": (0.5, 0.7),      # 0.5–0.7
            "investigate_stop": (0.0, 0.5),          # < 0.5
        },
        "action": {
            "safe_for_routing": "✅ Proceed to Phase 3 consideration",
            "continue_observation": "⏳ Accumulate more data (normal state)",
            "investigate_stop": "🛑 Stop. Model disagreement detected. Root cause analysis required.",
        }
    },
    
    "distribution_collapse": {
        "description": "Distribution health = std_v3 / std_v2",
        "thresholds": {
            "healthy": (0.7, 1.0),                    # ≥ 0.7
            "watch": (0.5, 0.7),                      # 0.5–0.7
            "collapse": (0.0, 0.5),                   # < 0.5
        },
        "action": {
            "healthy": "✅ OK — distributions are structurally similar",
            "watch": "⚠️  Mild compression detected. Rerun with 20+ more records to confirm",
            "collapse": "❌ HARD GATE. Invalidate experiment. CIS model requires reweighting.",
        }
    },
    
    "percentile_drift": {
        "description": "Ranking shift magnitude",
        "thresholds": {
            "excellent": (0, 10),
            "acceptable": (10, 20),
            "concern": (20, 25),
            "failure": (25, 100),
        },
        "action": {
            "excellent": "✅ Excellent alignment (current: ~7.6%)",
            "acceptable": "✅ Acceptable (normal range)",
            "concern": "⚠️  Structural shift detected. Investigate causes.",
            "failure": "❌ Unacceptable drift. Stop Phase 2.",
        }
    },
    
    "top_20_percent_overlap": {
        "description": "Diagnostic only. NOT a decision metric.",
        "rule": "❌ Do NOT use for routing decisions (fragile on small-N + tied scores)",
        "use_case": "Track trends only; expect 0% on low-intent cohorts",
    },
    
    "variant_purity": {
        "description": "Each variant must modify EXACTLY ONE axis",
        "axes": ["spend", "motion", "urgency"],
        "requirement": "≥ 80% (currently 100%)",
        "violation_action": "❌ AUTO-RESET to baseline (0,0,0). Prevents contamination.",
    },
    
    "sample_size": {
        "description": "Statistical power threshold",
        "minimum_for_decision": 50,
        "current": "~5 (insufficient)",
        "timeline": "7-14 days of daily Phase 2 runs",
    }
}

# ==================================================================================
# PHASE 3 DECISION GATE (Final Form)
# ==================================================================================

PHASE_3_CUTOVER_CRITERIA = {
    "all_must_be_true": [
        ("spearman >= 0.7", "Rank correlation strong enough for production"),
        ("collapse_ratio >= 0.7", "Distributions not compressed"),
        ("drift <= 15%", "Percentile movements acceptable"),
        ("variant_purity >= 0.8", "Experimental design maintained"),
        ("sample_size >= 50", "Statistical power achieved"),
        ("no_systematic_bias", "Top-decile alignment stable"),
    ],
    
    "if_any_fail": "❌ NO CUTOVER. Investigate + modify model.",
    
    "override_allowed": False,
}

# ==================================================================================
# RISK: Low-Signal Bias (Current State)
# ==================================================================================

CURRENT_RISK = """
Your dataset is biased toward LOW INTENT prospects.

Evidence:
- All 5 current records are discarded (NO_SPEND or DISCARD band)
- Top 20% overlap = 0% (expected when all candidates are weak)
- Spearman = 1.0 (trivial agreement on weak signals)

Problem:
- System looks "stable" but is NOT stress-tested
- Selection boundary (HOT vs POSSIBLE) never invoked
- Conflicting signals (high motion + low spend) never tested

Solution: MANDATORY STRESS-TEST COHORT (next step)
"""

# ==================================================================================
# NEXT: Inject Adversarial Test Candidates
# ==================================================================================

STRESS_TEST_TEMPLATE = """
Add 10-20 synthetic rows to 06-sales/stress-test-cohort.csv:

| Case                              | v2 Expected | v3 Expected | Why It Matters |
|-----------------------------------|-------------|-------------|----------------|
| High motion + zero spend          | POSSIBLE    | DISCARD     | Tests reweighting (spend_weight up) |
| High spend + low motion           | HOT         | HOT         | Tests spend_axis dominance |
| Strong LinkedIn + weak everything | POSSIBLE    | POSSIBLE    | Tests linkedin_constraint |
| High firmographic + low else      | POSSIBLE    | POSSIBLE    | Tests firmographic_fit |
| ALL zeros (dead prospect)         | NO          | DISCARD     | Sanity check |

Then run:
    python credibility_candidate_generator.py \\
      --input 06-sales/stress-test-cohort.csv \\
      --shadow-mode \\
      --replace --append

    python shadow_drift_tracker.py
    
Expected: Spearman stable (≥ 0.6), collapse_ratio unchanged
Result: Validates CIS reweighting works under pressure
"""

if __name__ == "__main__":
    print("📋 PHASE 2 OPERATIONAL RUNBOOK")
    print("=" * 80)
    print("\n" + DAILY_STEPS)
    print("\n" + "=" * 80)
    print("🔒 HARD RULES:")
    for rule, details in INTERPRETATION_RULES.items():
        print(f"\n{rule.upper()}:")
        if isinstance(details, dict):
            for key, value in details.items():
                print(f"  {key}: {value}")
    print("\n" + "=" * 80)
    print("⚠️  CURRENT RISK:")
    print(CURRENT_RISK)
    print("\n" + "=" * 80)
    print("🚀 NEXT MANDATORY STEP:")
    print(STRESS_TEST_TEMPLATE)
    print("=" * 80)
