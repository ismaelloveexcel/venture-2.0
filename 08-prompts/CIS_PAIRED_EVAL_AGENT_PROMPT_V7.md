# VS Code Agent Prompt v7 — Deterministic Paired CIS Stability System (Production Locked)

## System Purpose

Refactor CIS shadow evaluation into a deterministic paired experimental system that measures ranking stability, decision sensitivity, and structural perturbation effects between two deterministic scoring transformations (v2 vs v3).

This system is strictly:
- Not predictive
- Not causal
- Not uplift/conversion modeling
- Not performance-optimization driven

It is a statistically coherent transformation comparison engine.

---

## Scope and File Targets

- Primary implementation target: `04-coding/scripts/shadow_drift_tracker.py`
- Optional thin CLI wrapper: `04-coding/scripts/run_pipeline.py`
- Input default: `06-sales/shadow_decisions.jsonl`
- Output target: `06-sales/experiment_dashboard.json`

Do not modify `04-coding/scripts/venture_pipeline.py`.

---

## Absolute Constraints

### Forbidden
- Any causal inference
- Any uplift or conversion outcome modeling
- Any predictive performance interpretation
- Any cross-dataset metric mixing
- Any unseeded stochastic behavior
- Any non-deterministic scoring logic

### Required
- Identical snapshot used for all metrics in a run
- v2 and v3 treated as paired transforms of same records
- Paired bootstrap resampling of full records
- Deterministic ordering and reproducibility guarantees
- Mean and variance-aware output for all key metrics

---

## Input Data Contract (Required)

Input format is JSONL. Each record must include:
- `company`: string
- `v2_motion_score`: numeric, expected range 0..10
- `v3_cis`: numeric, expected range 0..100
- `motion_class`: HOT | POSSIBLE | NO
- `v3_routing_band`: HOT | POSSIBLE | DISCARD

Preferred (if available directly):
- `v2_percentile`: numeric, expected range 0..100
- `v3_percentile`: numeric, expected range 0..100

If percentiles are missing, compute them deterministically from the current snapshot.

---

## Execution Architecture

```python
# 1. EXPERIMENT INVARIANCE LAYER
# 2. SAMPLE VALIDATION (HARD GATE)
# 3. PAIRED SCORING EXTRACTION (v2/v3)
# 4. PERCENTILE NORMALIZATION LAYER
# 5. STABILITY METRICS (PAIRED)
# 6. DELTA TRANSFORMATION ENGINE (NORMALIZED)
# 7. BOOTSTRAP VARIANCE ENGINE (PAIRED, PERCENTILE CI)
# 8. RISK-BASED DECISION ENGINE (FIXED COEFFICIENTS)
# 9. FACTORIAL STRESS TEST GENERATOR (INDEPENDENT)
# 10. DASHBOARD OUTPUT SYSTEM
```

---

## 1) Experiment Invariance Layer

Requirements:
- Verify all records share identical schema keys
- Enforce deterministic ordering by `company` plus deterministic tie-breaker by original index
- Set `RANDOM_SEED = 42`
- All stochastic operations must use seeded RNG only

Tie-handling rule for percentile normalization is mandatory:
- Use deterministic average-rank tie handling
- Use same tie method for v2 and v3

---

## 2) Sample Validation Gate

Hard requirement:
- Minimum sample size is 50 paired records

If insufficient:
- Return status `INSUFFICIENT_SAMPLE_SIZE`
- Include `required` and `observed`
- Stop downstream metric and decision computation

---

## 3) Paired Scoring Extraction

Build paired rows from each record:
- `id`
- `v2_score_raw`
- `v3_score_raw`
- `v2_decision`
- `v3_decision`

Decision derivation:
- v2: HOT if `v2_motion_score >= 7`, POSSIBLE if `>= 5`, else DISCARD
- v3: HOT if `v3_cis >= 80`, POSSIBLE if `>= 50`, else DISCARD

---

## 4) Percentile Normalization Layer

Critical consistency rule:
- All cross-version deltas must be computed in percentile-normalized space

Definitions:
- `delta_pct = v3_percentile - v2_percentile`

No raw-scale cross-metric mixing is allowed.

---

## 5) Stability Metrics (Paired Snapshot Only)

All metrics must use the identical paired snapshot.

### 5.1 Rank Stability
- Spearman MUST be computed on percentile-normalized scores only:
  - `spearman(v2_percentile, v3_percentile)`
- Raw-score Spearman is invalid and must not be implemented.

### 5.2 Distribution Stability
- `distribution_collapse_ratio = std(v3_score_raw) / (std(v2_score_raw) + 1e-9)`

Collapse penalty must be symmetric:
- Penalize both compression below lower bound and expansion above upper bound

### 5.3 Rank Drift
- `avg_percentile_drift = mean(abs(v3_percentile - v2_percentile))`

### 5.4 Inversion Rate
- Pairwise rank-order disagreement rate between v2 and v3

### 5.5 Decision Flip Rate
- Fraction where `v2_decision != v3_decision`

### 5.6 Delta Diagnostics (Normalized)
- `mean_delta_pct`
- `std_delta_pct`
- `direction_bias_pct_sign = mean(sign(delta_pct))`

---

## 6) Bootstrap Variance Engine (Paired Correct)

Bootstrap requirements:
- Resampling unit is full paired record
- Resample with replacement
- Recompute metric fully per resample
- `n_bootstrap = 1000`
- Deterministic seed = 42

Confidence interval rule (mandatory):
- 95% CI MUST be percentile bootstrap only
- `CI_95 = [P2.5, P97.5]` over bootstrap samples
- Normal approximation CI is forbidden

Per metric output:
- mean
- std
- ci95_low
- ci95_high

---

## 7) Risk-Based Decision Engine (Fixed Coefficients)

Use continuous additive risk in normalized penalty components.

Fixed coefficients (must not be auto-tuned):

```python
a = 1.0  # rank stability penalty
b = 1.0  # collapse penalty
c = 1.5  # drift penalty (highest weight)
d = 1.2  # flip sensitivity penalty
e = 1.0  # delta magnitude penalty
```

Risk form:
- `risk = a*S + b*C + c*D + d*F + e*M + I`
- `S`: rank stability penalty
- `C`: collapse penalty
- `D`: drift penalty
- `F`: flip-rate penalty
- `M`: absolute mean delta penalty
- `I`: optional interaction penalty

Interaction safety rule:
- Interaction terms are allowed only after z-normalizing interacting components

Decision states:
- `FAIL_HIGH_RISK`
- `CAUTIOUS_PROCEED`
- `CUTOVER_READY`

---

## 8) Factorial Stress Test Generator

Required factors:
- motion in {low, medium, high}
- spend in {weak, medium, strong}
- urgency in {none, moderate, high}

Rules:
- Independent factor generation only
- No CIS-derived source leakage into synthetic factors
- Full factorial 3x3x3 coverage required
- Include deterministic edge-case boundary rows

---

## 9) Dashboard Output Contract

Write `06-sales/experiment_dashboard.json` with:
- metadata: timestamp_utc, input_path, record_count, random_seed, bootstrap_n
- invariance_checks: pass/fail and reasons
- sample_gate
- metrics_point_estimates
- metrics_bootstrap_summary
- risk_components
- final_decision
- semantic_labels
- stress_test_summary

---

## 10) Semantic Guarantees

Allowed meanings:
- Spearman: rank stability
- inversion_rate: ranking perturbation magnitude
- flip_rate: decision sensitivity
- delta_pct: transformation effect (normalized space)
- collapse_ratio: distribution stability

Prohibited semantics:
- Any claim of business outcome lift
- Any causal interpretation
- Any predictive performance interpretation

---

## CLI Contract

Support:

```bash
python 04-coding/scripts/run_pipeline.py --input 06-sales/shadow_decisions.jsonl --output 06-sales/experiment_dashboard.json
```

Runtime expectations:
- Nonzero exit code on hard validation failure
- Concise terminal status line with decision and key record counts

---

## Strict Acceptance Criteria

System is valid only if all pass:
- Percentile normalization used across cross-version metrics, including Spearman
- Bootstrap CI uses percentile method only
- Risk coefficients are explicitly fixed to the specified constants
- No raw-score cross-metric mixing exists
- All paired metrics are computed on identical snapshot
- Deterministic ordering and seed reproducibility are enforced
- Stress generator remains independent and factorial
- No causal/uplift/performance logic exists
- End-to-end entrypoint writes dashboard successfully

---

## Final System Definition

A deterministic, percentile-normalized, paired experimental evaluation engine with percentile-bootstrap uncertainty estimation and fixed-coefficient continuous risk aggregation for scoring transformation stability analysis.