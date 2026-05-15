#!/usr/bin/env python3
"""
STRESS COHORT GENERATOR (CORRECTED)

Generates adversarial prospects to stress-test CIS ranking stability.

Key insight: We're testing PROSPECT VARIATION, not MESSAGE VARIATION.
So variant_purity doesn't apply (that's for message design).

Instead, we measure:
- Spearman rank correlation (stays >= 0.6?)
- Distribution collapse (stays >= 0.7?)
- Percentile drift (stays <= 15?)

Success = CIS rankings remain stable despite conflicting signals.
"""

import csv
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
SALES_DIR = BASE / "06-sales"
OUTPUT = SALES_DIR / "stress-test-cohort.csv"

STRESS_CANDIDATES = [
    # BASELINE: all weak signals
    {
        "company": "stress_baseline",
        "first_name": "Founder",
        "role": "Manager",
        "trigger": "",  # no spending pressure
        "employee_count": "20",
        "industry": "Retail",
        "website_quality": "average",
        "linkedin_quality": "average",
        "notes": "Baseline: weak on all axes"
    },
    
    # AXIS 1: HIGH SPEND + LOW MOTION (test reweighting)
    {
        "company": "stress_highspend_lowmotion",
        "first_name": "Finance",
        "role": "CFO",
        "trigger": "revenue_pressure",  # spend signal ✓
        "employee_count": "15",  # small = low motion
        "industry": "Retail",  # stable = low motion
        "website_quality": "average",
        "linkedin_quality": "average",
        "notes": "Axis 1: High spend (revenue_pressure) but low motion (small, stable)"
    },
    
    # AXIS 2: HIGH MOTION + LOW SPEND (test motion dominance)
    {
        "company": "stress_highmotion_lowspend",
        "first_name": "Ops",
        "role": "VP Operations",
        "trigger": "",  # no spending pressure
        "employee_count": "300",  # large = high motion
        "industry": "SaaS",  # growth = high motion
        "website_quality": "strong",
        "linkedin_quality": "strong",
        "notes": "Axis 2: High motion (large, SaaS) but low spend (no pressure)"
    },
    
    # AXIS 3: HIGH FIRMOGRAPHIC (large SaaS) + WEAK SIGNALS
    {
        "company": "stress_highfirmo_weakbuying",
        "first_name": "Analyst",
        "role": "Data Analyst",
        "trigger": "visibility_pressure",  # weak signal
        "employee_count": "500",
        "industry": "SaaS",
        "website_quality": "strong",
        "linkedin_quality": "weak",
        "notes": "Axis 3: High firmographic fit but weak buying intent"
    },
    
    # AXIS 4: CONFLICTING SIGNALS (high motion + low spend + high firmographic)
    {
        "company": "stress_conflict_signals",
        "first_name": "VP",
        "role": "VP Sales",
        "trigger": "visibility_pressure",  # weak spend pressure
        "employee_count": "200",  # high motion
        "industry": "FinTech",  # high motion + growth
        "website_quality": "strong",
        "linkedin_quality": "strong",
        "notes": "Conflict: high motion/firmographic but weak spend"
    },
    
    # AXIS 5: ALL HIGH (test ceiling)
    {
        "company": "stress_all_high",
        "first_name": "CEO",
        "role": "Founder",
        "trigger": "revenue_pressure",  # high spend
        "employee_count": "500",  # high motion
        "industry": "SaaS",  # high motion
        "website_quality": "strong",
        "linkedin_quality": "strong",
        "notes": "Test ceiling: high on all dimensions"
    },
    
    # AXIS 6: ALL LOW (test floor)
    {
        "company": "stress_all_low",
        "first_name": "Admin",
        "role": "Coordinator",
        "trigger": "",  # no spend
        "employee_count": "5",  # low motion
        "industry": "Retail",  # low motion
        "website_quality": "weak",
        "linkedin_quality": "weak",
        "notes": "Test floor: low on all dimensions"
    },
    
    # AXIS 7: STRONG LINKEDIN PENALTY (good LinkedIn, bad company)
    {
        "company": "stress_strong_li_weak_company",
        "first_name": "Influencer",
        "role": "Thought Leader",
        "trigger": "",
        "employee_count": "3",
        "industry": "Retail",
        "website_quality": "weak",
        "linkedin_quality": "strong",
        "notes": "LinkedIn paradox: strong profile, weak company fundamentals"
    },
    
    # AXIS 8: WEAK LINKEDIN STRONG COMPANY (good company, weak profile)
    {
        "company": "stress_weak_li_strong_company",
        "first_name": "Executive",
        "role": "CTO",
        "trigger": "scaling_pressure",
        "employee_count": "400",
        "industry": "SaaS",
        "website_quality": "strong",
        "linkedin_quality": "weak",
        "notes": "Inverse paradox: weak profile, strong company fundamentals"
    },
]


def main() -> int:
    """Generate stress cohort focused on causal axis testing."""
    print("\n" + "=" * 80)
    print("🧪 GENERATING ADVERSARIAL STRESS COHORT (PROSPECT VARIATION)")
    print("=" * 80)
    
    # Add standard fields
    for row in STRESS_CANDIDATES:
        row.setdefault("website", f"https://{row['company']}.example.com")
        row.setdefault("linkedin_url", f"https://linkedin.com/in/{row['company']}")
        row.setdefault("fit_score", "50")
        row.setdefault("message_version", "credibility_v1")
        row.setdefault("service_angle", "general_pressure")
        row.setdefault("status", "TEST")
        row.setdefault("location", "SF")
    
    fieldnames = list(STRESS_CANDIDATES[0].keys())
    
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(STRESS_CANDIDATES)
    
    print(f"\n✅ STRESS COHORT WRITTEN")
    print(f"   Location: {OUTPUT}")
    print(f"   Rows: {len(STRESS_CANDIDATES)}")
    print(f"   Design: Adversarial (tests ranking stability under conflicting signals)")
    print(f"\n📊 Axes tested:")
    print(f"   1. High spend + low motion")
    print(f"   2. High motion + low spend")
    print(f"   3. High firmographic + weak buying")
    print(f"   4. Conflicting signals")
    print(f"   5. All high (ceiling)")
    print(f"   6. All low (floor)")
    print(f"   7. Strong LinkedIn paradox")
    print(f"   8. Weak LinkedIn strong company")
    print(f"\n🎯 Success metrics (NOT variant purity):")
    print(f"   ✓ Spearman >= 0.6 (rank correlation stable)")
    print(f"   ✓ collapse_ratio >= 0.7 (distributions healthy)")
    print(f"   ✓ drift <= 15% (percentile movement small)")
    print(f"\n📋 Next steps:")
    print(f"   1. python credibility_candidate_generator.py --input {OUTPUT} --shadow-mode --replace")
    print(f"   2. python shadow_drift_tracker.py")
    print(f"   3. Verify: spearman >= 0.6, collapse_ratio >= 0.7, drift <= 15%")
    print("=" * 80 + "\n")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
