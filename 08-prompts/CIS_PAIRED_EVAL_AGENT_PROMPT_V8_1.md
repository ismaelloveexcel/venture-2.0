# VS CODE AGENT PROMPT v8.1 - DETERMINISTIC PAIRED CIS EXPERIMENTAL SYSTEM (PRODUCTION LOCKED)

## System Purpose

Build a deterministic paired experimental evaluation system that measures structural differences between two scoring transformations:
- v2 (baseline CIS motion scoring)
- v3 (CIS enhanced scoring system)

This system evaluates:
- ranking stability
- decision sensitivity
- distributional perturbation
- transformation drift
- structural divergence

---

## Non-Goals (Absolute Constraints)

The system MUST NOT perform:
- causal inference
- uplift modeling
- conversion prediction
- business performance estimation
- optimization of scoring functions
- cross-dataset comparisons
- stochastic or non-reproducible computation

---

## Implementation Targets

Primary file (mandatory):
- 04-coding/scripts/shadow_drift_tracker.py

Optional CLI wrapper:
- 04-coding/scripts/run_pipeline.py

Input:
- 06-sales/shadow_decisions.jsonl

Output:
- 06-sales/experiment_dashboard.json

Do not modify 04-coding/scripts/venture_pipeline.py.

---

## Global Execution Constraints

### Determinism
- RANDOM_SEED = 42
- all randomness must be seeded
- identical input MUST produce identical output (byte-stable JSON except optional pretty-print whitespace)

### Snapshot rule
- Base metrics and risk in one run MUST use the same immutable in-memory paired snapshot
- Bootstrap is the only allowed recomputation context (per resample)
- No metric may read from a different file pass or refreshed dataset during one run

### Pairing rule
- every record MUST contain v2 and v3 paired values
- no independent evaluation streams allowed

### Ordering rule
- sort by:
1. company ASC
2. original_index ASC (tie-breaker)

### Numeric hygiene rule
- NaN, +Inf, -Inf are invalid and MUST hard-fail validation
- no silent coercion, no silent clamping
- numeric parsing must be explicit and deterministic

### Version lock
- include `spec_version = "v8.1"` in dashboard metadata
- include `input_sha256` (hash of raw input file bytes) in dashboard metadata
- deterministic equality checks should compare full payload including metadata

---

## Input Schema (Required)

Each JSONL record MUST include:

{
  "company": "string",
  "v2_motion_score": "float",
  "v3_cis": "float",
  "motion_class": "HOT | POSSIBLE | NO",
  "v3_routing_band": "HOT | POSSIBLE | DISCARD"
}

Optional:
- v2_percentile
- v3_percentile
- record_id

Type constraints:
- company must be non-empty string
- v2_motion_score and v3_cis must be finite numeric values
- motion_class and v3_routing_band must be valid enumerations

If percentiles are missing, compute deterministically using rank-based percentile normalization.

Pair key requirement:
- paired_id = record_id if present else company + "__" + original_index
- paired_id uniqueness is mandatory

---

## Execution Pipeline (Strict Order)

The system MUST execute in this exact sequence:
1. Invariance Layer
2. Sample Gate
3. Paired Construction
4. Percentile Normalization Layer
5. Metric Computation Layer
6. Bootstrap Variance Layer
7. Risk Engine
8. Stress Test Generator
9. Dashboard Output

No reordering allowed.

---

## 1) Invariance Layer

Enforce:
- schema validation
- deterministic sorting
- seed initialization

```python
SEED = 42
```

Tie-breaking must be deterministic.

---

## 2) Sample Gate (Hard Stop)

```python
if len(records) < 50:
    return {
        "status": "INSUFFICIENT_SAMPLE_SIZE",
        "observed": len(records),
        "required": 50
    }
```

Stop execution immediately if failed.

Validation behavior:
- if any required field is missing or invalid, return `INVALID_SCHEMA`
- include deterministic error summary: `error_count`, `first_error_index`, `first_error_reason`
- do not continue to metric computation when schema validation fails

---

## 3) Paired Construction

Each record becomes:

```python
{
  "id": paired_id,
  "v2_score_raw": v2_motion_score,
  "v3_score_raw": v3_cis,
  "v2_decision": v2_decision,
  "v3_decision": v3_decision
}
```

Decision rules (fixed):

v2:
- HOT: >= 7
- POSSIBLE: >= 5
- else: DISCARD

v3:
- HOT: >= 80
- POSSIBLE: >= 50
- else: DISCARD

---

## 4) Percentile Normalization (Mandatory)

Cross-version comparison metrics must use percentile-normalized space.

Definitions:
- v2_percentile
- v3_percentile
- delta_pct = v3_percentile - v2_percentile

Allowed raw-scale exception:
- distribution_collapse_ratio in Section 5.2 is explicitly allowed as a raw dispersion diagnostic.

Percentile method lock:
- tie handling: average-rank (stable, deterministic)
- rank assignment sort: (score ASC, original_index ASC)
- percentile formula: pct = 100 * (rank - 1) / (n - 1)
- for n = 1, set percentile = 50

---

## 5) Metric System (Paired Snapshot Only)

### 5.1 Rank Stability (Spearman Only)

```python
spearman(v2_percentile, v3_percentile)
```

Meaning: rank stability only.

Spearman implementation lock:
1. scipy.stats.spearmanr on percentile vectors
2. deterministic fallback implementation if scipy unavailable

Silent zero/NaN substitution is forbidden.

### 5.2 Distribution Collapse

```python
collapse_ratio = std(v3_score_raw) / (std(v2_score_raw) + 1e-9)
```

### 5.3 Percentile Drift

```python
avg_drift = mean(abs(v3_percentile - v2_percentile))
```

### 5.4 Inversion Rate

Pairwise rank disagreement rate.

### 5.5 Decision Flip Rate

```python
flip_rate = count(v2_decision != v3_decision) / n
```

No weighting allowed.

### 5.6 Delta Statistics (Normalized Only)

```python
mean_delta_pct
std_delta_pct
direction_bias = mean(sign(delta_pct))
```

---

## 6) Bootstrap Engine (Paired Only)

Rules:
- resample full paired records
- replacement allowed
- seed fixed (42)
- n = 1000

Output per metric:
- mean
- std
- ci95_low (p2.5)
- ci95_high (p97.5)

Confidence interval rule:
- percentile bootstrap only
- Gaussian/normal approximation CI is forbidden

Bootstrap determinism rule:
- initialize one seeded RNG from SEED=42 at run start
- all bootstrap draws must come from that RNG stream only
- no use of global implicit random state

---

## 7) Risk Engine (Continuous Model)

Penalty definitions (locked):

```python
stability_penalty = max(0.0, (0.70 - spearman) / 0.10)

collapse_penalty = (
    max(0.0, (0.70 - collapse_ratio) / 0.10) +
    max(0.0, (collapse_ratio - 1.30) / 0.10)
)

drift_penalty = max(0.0, (avg_drift - 15.0) / 5.0)
flip_penalty = max(0.0, (flip_rate - 0.10) / 0.05)
delta_penalty = abs(mean_delta_pct) / 10.0
```

Fixed coefficients:

```python
a = 1.0  # rank stability penalty
b = 1.0  # collapse penalty
c = 1.5  # drift penalty (highest weight)
d = 1.2  # flip sensitivity penalty
e = 1.0  # delta magnitude penalty
```

Risk formula:

```python
risk = (
  a * stability_penalty +
  b * collapse_penalty +
  c * drift_penalty +
  d * flip_penalty +
  e * delta_penalty
)
```

Optional interaction term:
- allowed only if interaction inputs are z-normalized first

Decision bands:
- risk >= 5 -> FAIL_HIGH_RISK
- 2 <= risk < 5 -> CAUTIOUS_PROCEED
- risk < 2 -> CUTOVER_READY

---

## 8) Stress Test Generator (Full Factorial)

Generate:
- motion: low / medium / high
- spend: weak / medium / strong
- urgency: none / moderate / high

Requirements:
- full 27 combinations
- add deterministic boundary extremes:
  - all-min
  - all-max
  - mixed extreme permutations
- no CIS logic reuse
- no correlated sampling
- deterministic ordering required

---

## 9) Dashboard Output (Strict Contract)

Must include:

{
  "metadata": {
    "timestamp_utc": "...",
    "input_path": "...",
    "input_sha256": "...",
    "spec_version": "v8.1",
    "record_count": 0,
    "random_seed": 42,
    "bootstrap_n": 1000
  },
  "invariance_checks": {},
  "sample_gate": {},
  "metrics_point_estimates": {},
  "metrics_bootstrap": {},
  "risk_components": {},
  "final_decision": "CUTOVER_READY | CAUTIOUS_PROCEED | FAIL_HIGH_RISK",
  "stress_test_summary": {},
  "semantic_labels": {
    "spearman": "rank stability",
    "flip_rate": "decision sensitivity",
    "inversion_rate": "ranking perturbation",
    "delta_pct": "structural transformation",
    "collapse_ratio": "distribution stability"
  }
}

---

## 10) CLI Contract

```bash
python 04-coding/scripts/run_pipeline.py --input 06-sales/shadow_decisions.jsonl --output 06-sales/experiment_dashboard.json
```

Runtime rules:
- exit non-zero on failure
- print:
  - PIPELINE_STATUS: <decision>
  - RECORDS: <n>
  - RISK: <score>

Exit code contract:
- 0: success (decision emitted)
- 2: invalid schema
- 3: insufficient sample size
- 4: runtime computation failure

---

## Final System Definition

A deterministic paired experimental evaluation engine that measures structural divergence, ranking stability, and decision sensitivity between two scoring transformations using percentile normalization and bootstrap uncertainty estimation.

---

## Acceptance Criteria (Hard Pass)

System is valid only if all are true:
- deterministic execution guaranteed
- paired structure preserved end-to-end
- sample gate enforces n >= 50
- percentile normalization used everywhere required
- bootstrap uses paired resampling only
- CI computed via percentile bootstrap only
- no causal or uplift logic exists
- no raw-score cross-metric leakage exists (except explicitly allowed collapse ratio)
- risk engine is continuous and coefficient-locked
- full factorial stress test implemented
- dashboard is self-contained and reproducible
- CLI executes full pipeline end-to-end
- invalid numeric inputs fail fast with deterministic error payload
- input hash and spec version are present in metadata

---

## End State

After implementation, system becomes:

a fully deterministic, variance-aware, paired experimental evaluation framework for measuring structural divergence between scoring systems under controlled statistical conditions.