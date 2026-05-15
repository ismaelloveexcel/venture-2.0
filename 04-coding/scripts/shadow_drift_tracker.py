#!/usr/bin/env python3
"""
Deterministic paired CIS stability evaluation (v8.1).

Paired experimental comparison of v2 vs v3 scoring transforms on an identical
snapshot. Descriptive stability metrics only — no outcome lift or attribution
claims. Aligned with `08-prompts/CIS_PAIRED_EVAL_AGENT_PROMPT_V8_1.md`.

Primary entry: generate_experiment_dashboard(...)
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[2]
SALES_DIR = BASE / "06-sales"
SHADOW_LOG_PATH = SALES_DIR / "shadow_decisions.jsonl"
BASELINE_PATH = SALES_DIR / "baseline_distributions.json"
DASHBOARD_PATH = SALES_DIR / "experiment_dashboard.json"

RANDOM_SEED = 42
MIN_SAMPLE_SIZE = 50
BOOTSTRAP_N = 1000
SPEC_VERSION = "v8.1"

# Fixed risk coefficients (must not be auto-tuned)
RISK_A = 1.0  # rank stability penalty S
RISK_B = 1.0  # collapse penalty C
RISK_C = 1.5  # drift penalty D
RISK_D = 1.2  # flip sensitivity penalty F
RISK_E = 1.0  # delta magnitude penalty M
RISK_I_COEFF = 0.15  # interaction on z-normalized S x C

REQUIRED_FIELDS = frozenset(
    {
        "company",
        "v2_motion_score",
        "v3_cis",
        "motion_class",
        "v3_routing_band",
    }
)


def load_baseline_distributions(baseline_path: Path) -> dict[str, Any]:
    if not baseline_path.exists():
        return {}
    try:
        return json.loads(baseline_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], str]:
    raw = path.read_bytes()
    rows: list[dict[str, Any]] = []
    for idx, line in enumerate(raw.decode("utf-8").splitlines()):
        if not line.strip():
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError(f"INVALID_SCHEMA: line {idx + 1} must be an object")
        rows.append(obj)
    return rows, hashlib.sha256(raw).hexdigest()


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _validate_schema(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {
            "valid": False,
            "error": "INVALID_SCHEMA",
            "error_count": 1,
            "first_error_index": 0,
            "first_error_reason": "No records found",
        }

    first_keys = frozenset(records[0].keys())
    first_error_index: int | None = None
    first_error_reason = ""
    errors = 0

    for i, r in enumerate(records):
        if frozenset(r.keys()) != first_keys:
            errors += 1
            if first_error_index is None:
                first_error_index = i
                first_error_reason = "Schema key set differs from first record"
            continue

        missing = REQUIRED_FIELDS - frozenset(r.keys())
        if missing:
            errors += 1
            if first_error_index is None:
                first_error_index = i
                first_error_reason = f"Missing fields: {sorted(missing)}"
            continue

        if not isinstance(r.get("company"), str) or not str(r.get("company", "")).strip():
            errors += 1
            if first_error_index is None:
                first_error_index = i
                first_error_reason = "company must be non-empty string"

        if not _is_finite_number(r.get("v2_motion_score")):
            errors += 1
            if first_error_index is None:
                first_error_index = i
                first_error_reason = "v2_motion_score must be finite number"

        if not _is_finite_number(r.get("v3_cis")):
            errors += 1
            if first_error_index is None:
                first_error_index = i
                first_error_reason = "v3_cis must be finite number"

        if r.get("motion_class") not in {"HOT", "POSSIBLE", "NO"}:
            errors += 1
            if first_error_index is None:
                first_error_index = i
                first_error_reason = "motion_class must be HOT | POSSIBLE | NO"

        if r.get("v3_routing_band") not in {"HOT", "POSSIBLE", "DISCARD"}:
            errors += 1
            if first_error_index is None:
                first_error_index = i
                first_error_reason = "v3_routing_band must be HOT | POSSIBLE | DISCARD"

        if "v2_percentile" in r and r["v2_percentile"] is not None:
            if not _is_finite_number(r.get("v2_percentile")):
                errors += 1
                if first_error_index is None:
                    first_error_index = i
                    first_error_reason = "v2_percentile must be finite when present"

        if "v3_percentile" in r and r["v3_percentile"] is not None:
            if not _is_finite_number(r.get("v3_percentile")):
                errors += 1
                if first_error_index is None:
                    first_error_index = i
                    first_error_reason = "v3_percentile must be finite when present"

    if errors:
        return {
            "valid": False,
            "error": "INVALID_SCHEMA",
            "error_count": errors,
            "first_error_index": first_error_index,
            "first_error_reason": first_error_reason,
        }

    return {"valid": True, "key_set": sorted(first_keys)}


def _sample_gate(records: list[dict[str, Any]]) -> dict[str, Any]:
    if len(records) < MIN_SAMPLE_SIZE:
        return {
            "valid": False,
            "error": "INSUFFICIENT_SAMPLE_SIZE",
            "observed": len(records),
            "required": MIN_SAMPLE_SIZE,
        }
    return {"valid": True, "observed": len(records), "required": MIN_SAMPLE_SIZE}


def _invariance_sort(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for i, r in enumerate(records):
        row = dict(r)
        row["_original_index"] = i
        enriched.append(row)
    enriched.sort(key=lambda x: (str(x["company"]), int(x["_original_index"])))
    return enriched


def _derive_v2_decision(v2: float) -> str:
    if v2 >= 7:
        return "HOT"
    if v2 >= 5:
        return "POSSIBLE"
    return "DISCARD"


def _derive_v3_decision(v3: float) -> str:
    if v3 >= 80:
        return "HOT"
    if v3 >= 50:
        return "POSSIBLE"
    return "DISCARD"


def _paired_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for r in records:
        pairs.append(
            {
                "id": f"{r['company']}__{r['_original_index']}",
                "v2_score_raw": float(r["v2_motion_score"]),
                "v3_score_raw": float(r["v3_cis"]),
                "v2_decision": _derive_v2_decision(float(r["v2_motion_score"])),
                "v3_decision": _derive_v3_decision(float(r["v3_cis"])),
                "_original_index": int(r["_original_index"]),
                "company": r["company"],
                "v2_percentile": r.get("v2_percentile"),
                "v3_percentile": r.get("v3_percentile"),
            }
        )
    return pairs


def _average_rank_percentiles(
    values: list[float], tie_breaker: list[int]
) -> list[float]:
    """Deterministic average-rank tie handling -> percentiles in [0, 100]."""
    n = len(values)
    if n == 1:
        return [50.0]

    indexed = list(zip(values, tie_breaker, range(n)))
    indexed.sort(key=lambda x: (x[0], x[1], x[2]))

    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and indexed[j + 1][0] == indexed[i][0]:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            _, _, original_pos = indexed[k]
            ranks[original_pos] = avg_rank
        i = j + 1

    return [100.0 * (r - 1.0) / (n - 1.0) for r in ranks]


def _ensure_percentiles(pairs: list[dict[str, Any]]) -> None:
    tie_breaker = [p["_original_index"] for p in pairs]

    if any(p.get("v2_percentile") is None for p in pairs):
        vals = [p["v2_score_raw"] for p in pairs]
        pcts = _average_rank_percentiles(vals, tie_breaker)
        for p, pct in zip(pairs, pcts):
            p["v2_percentile"] = float(pct)
    else:
        for p in pairs:
            if not _is_finite_number(p.get("v2_percentile")):
                raise ValueError("INVALID_SCHEMA: v2_percentile must be finite number")
            p["v2_percentile"] = float(p["v2_percentile"])

    if any(p.get("v3_percentile") is None for p in pairs):
        vals = [p["v3_score_raw"] for p in pairs]
        pcts = _average_rank_percentiles(vals, tie_breaker)
        for p, pct in zip(pairs, pcts):
            p["v3_percentile"] = float(pct)
    else:
        for p in pairs:
            if not _is_finite_number(p.get("v3_percentile")):
                raise ValueError("INVALID_SCHEMA: v3_percentile must be finite number")
            p["v3_percentile"] = float(p["v3_percentile"])


def _rankdata_average_ties(values: list[float], tie_breaker: list[int]) -> list[float]:
    """Average-rank (1..n) for Spearman; tie-break by tie_breaker then index."""
    n = len(values)
    idxs = list(range(n))
    idxs.sort(key=lambda i: (values[i], tie_breaker[i], i))
    ranks = [0.0] * n
    k = 0
    while k < n:
        k2 = k
        while k2 + 1 < n and values[idxs[k2 + 1]] == values[idxs[k]]:
            k2 += 1
        avg_rank = (k + k2 + 2) / 2.0
        for t in range(k, k2 + 1):
            ranks[idxs[t]] = avg_rank
        k = k2 + 1
    return ranks


def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    mx = statistics.mean(x)
    my = statistics.mean(y)
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
    vx = sum((a - mx) ** 2 for a in x)
    vy = sum((b - my) ** 2 for b in y)
    if vx <= 0 or vy <= 0:
        return 0.0
    return cov / math.sqrt(vx * vy)


def _spearman_percentile_space(v2_pct: list[float], v3_pct: list[float]) -> float:
    """
    Spearman rho on percentile-normalized scores only (tie-aware).
    Equivalent to Pearson correlation of separate rank vectors.
    """
    n = len(v2_pct)
    if n < 2:
        return 0.0
    tb = list(range(n))
    r2 = _rankdata_average_ties(v2_pct, tb)
    r3 = _rankdata_average_ties(v3_pct, tb)
    return float(_pearson(r2, r3))


def _metric_point_estimates(pairs: list[dict[str, Any]]) -> dict[str, float]:
    n = len(pairs)
    v2_raw = [p["v2_score_raw"] for p in pairs]
    v3_raw = [p["v3_score_raw"] for p in pairs]
    v2_pct = [p["v2_percentile"] for p in pairs]
    v3_pct = [p["v3_percentile"] for p in pairs]

    spearman = _spearman_percentile_space(v2_pct, v3_pct)

    v2_std = statistics.pstdev(v2_raw) if n > 1 else 0.0
    v3_std = statistics.pstdev(v3_raw) if n > 1 else 0.0
    collapse_ratio = v3_std / (v2_std + 1e-9)

    drifts = [abs(b - a) for a, b in zip(v2_pct, v3_pct)]
    avg_drift = statistics.mean(drifts) if drifts else 0.0

    inversions = 0
    comparisons = 0
    for i in range(n):
        for j in range(i + 1, n):
            a = v2_pct[i] > v2_pct[j]
            b = v3_pct[i] > v3_pct[j]
            if a != b:
                inversions += 1
            comparisons += 1
    inversion_rate = inversions / comparisons if comparisons else 0.0

    flips = sum(1 for p in pairs if p["v2_decision"] != p["v3_decision"])
    flip_rate = flips / n if n else 0.0

    delta = [b - a for a, b in zip(v2_pct, v3_pct)]
    mean_delta = statistics.mean(delta) if delta else 0.0
    std_delta = statistics.pstdev(delta) if len(delta) > 1 else 0.0
    direction_bias = (
        statistics.mean([0.0 if d == 0 else (1.0 if d > 0 else -1.0) for d in delta])
        if delta
        else 0.0
    )

    return {
        "spearman": float(spearman),
        "distribution_collapse_ratio": float(collapse_ratio),
        "avg_percentile_drift": float(avg_drift),
        "inversion_rate": float(inversion_rate),
        "flip_rate": float(flip_rate),
        "mean_delta_pct": float(mean_delta),
        "std_delta_pct": float(std_delta),
        "direction_bias_pct_sign": float(direction_bias),
    }


def _percentile_of_sorted(sorted_values: list[float], p: float) -> float:
    """Linear interpolation percentile (p in 0..100). Percentile-bootstrap only."""
    if not sorted_values:
        return 0.0
    xs = sorted_values
    n = len(xs)
    if n == 1:
        return float(xs[0])
    k = (n - 1) * (p / 100.0)
    f = int(math.floor(k))
    c = int(math.ceil(k))
    if f == c:
        return float(xs[f])
    return float(xs[f] * (c - k) + xs[c] * (k - f))


def _penalty_vector(point: dict[str, float]) -> dict[str, float]:
    """Map point metrics to normalized penalty components S,C,D,F,M in [0,1]."""
    rho = point["spearman"]
    S = max(0.0, min(1.0, (1.0 - rho) / 2.0))

    R = point["distribution_collapse_ratio"]
    C = max(0.0, min(1.0, abs(1.0 - R)))

    D = max(0.0, min(1.0, point["avg_percentile_drift"] / 50.0))

    F = max(0.0, min(1.0, point["flip_rate"]))

    M = max(0.0, min(1.0, abs(point["mean_delta_pct"]) / 50.0))

    return {"S": float(S), "C": float(C), "D": float(D), "F": float(F), "M": float(M)}


def _bootstrap_draws(
    pairs: list[dict[str, Any]], n_boot: int, seed: int
) -> list[dict[str, float]]:
    """One bootstrap resample -> full point metrics; repeated n_boot times."""
    rng = random.Random(seed)
    n = len(pairs)
    out: list[dict[str, float]] = []
    for _ in range(n_boot):
        sample = [pairs[rng.randrange(0, n)] for _ in range(n)]
        out.append(_metric_point_estimates(sample))
    return out


def _bootstrap_summary(
    pairs: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    metric_names = [
        "spearman",
        "distribution_collapse_ratio",
        "avg_percentile_drift",
        "inversion_rate",
        "flip_rate",
        "mean_delta_pct",
        "std_delta_pct",
        "direction_bias_pct_sign",
    ]
    draws = _bootstrap_draws(pairs, BOOTSTRAP_N, RANDOM_SEED)
    summary: dict[str, dict[str, float]] = {}
    for name in metric_names:
        samples = sorted(float(d[name]) for d in draws)
        mu = statistics.mean(samples)
        sigma = statistics.pstdev(samples) if len(samples) > 1 else 0.0
        summary[name] = {
            "mean": float(mu),
            "std": float(sigma),
            "ci95_low": float(_percentile_of_sorted(samples, 2.5)),
            "ci95_high": float(_percentile_of_sorted(samples, 97.5)),
        }
    return summary


def _penalty_bootstrap_vectors(
    pairs: list[dict[str, Any]],
) -> tuple[dict[str, float], list[dict[str, float]]]:
    draws_metrics = _bootstrap_draws(pairs, BOOTSTRAP_N, RANDOM_SEED)
    penalties: list[dict[str, float]] = []
    for d in draws_metrics:
        penalties.append(_penalty_vector(d))
    point = _metric_point_estimates(pairs)
    point_pen = _penalty_vector(point)
    return point_pen, penalties


def _z(x: float, xs: list[float]) -> float:
    mu = statistics.mean(xs)
    sig = statistics.pstdev(xs) if len(xs) > 1 else 0.0
    if sig <= 1e-12:
        return 0.0
    return (x - mu) / sig


def _risk_components(
    point: dict[str, float], pairs: list[dict[str, Any]]
) -> dict[str, float]:
    point_pen, pen_boot = _penalty_bootstrap_vectors(pairs)
    S0, C0, D0, F0, M0 = (
        point_pen["S"],
        point_pen["C"],
        point_pen["D"],
        point_pen["F"],
        point_pen["M"],
    )
    Ss = [p["S"] for p in pen_boot]
    Cs = [p["C"] for p in pen_boot]
    zS = _z(S0, Ss)
    zC = _z(C0, Cs)
    I = RISK_I_COEFF * zS * zC
    I = max(-0.5, min(0.5, I))

    risk = (
        RISK_A * S0
        + RISK_B * C0
        + RISK_C * D0
        + RISK_D * F0
        + RISK_E * M0
        + I
    )

    return {
        "coefficients": {
            "a": RISK_A,
            "b": RISK_B,
            "c": RISK_C,
            "d": RISK_D,
            "e": RISK_E,
            "i_coeff": RISK_I_COEFF,
        },
        "S": float(S0),
        "C": float(C0),
        "D": float(D0),
        "F": float(F0),
        "M": float(M0),
        "I_interaction": float(I),
        "z_S": float(zS),
        "z_C": float(zC),
        "risk": float(risk),
    }


def _decision_from_risk(risk: float) -> str:
    if risk >= 5.0:
        return "FAIL_HIGH_RISK"
    if risk >= 2.0:
        return "CAUTIOUS_PROCEED"
    return "CUTOVER_READY"


def _stress_test_summary() -> dict[str, Any]:
    motion = ("low", "medium", "high")
    spend = ("weak", "medium", "strong")
    urgency = ("none", "moderate", "high")
    combos: list[dict[str, str]] = []
    for m in motion:
        for s in spend:
            for u in urgency:
                combos.append({"motion": m, "spend": s, "urgency": u})
    boundary = [
        {"motion": "low", "spend": "weak", "urgency": "none"},
        {"motion": "high", "spend": "strong", "urgency": "high"},
        {"motion": "low", "spend": "strong", "urgency": "high"},
        {"motion": "high", "spend": "weak", "urgency": "none"},
    ]
    return {
        "factorial_axes": {"motion": list(motion), "spend": list(spend), "urgency": list(urgency)},
        "factorial_count": len(combos),
        "full_factorial_rows": combos,
        "boundary_rows": boundary,
        "note": "Synthetic factorial factors only; no CIS-derived leakage.",
    }


def _metadata_timestamp_utc(
    baseline: dict[str, Any], input_sha256: str, record_count: int
) -> str:
    """Reproducible per snapshot: prefer baseline frozen_at; else hash-derived UTC."""
    fa = baseline.get("frozen_at")
    if isinstance(fa, str) and fa.strip():
        s = fa.strip()
        if s.endswith("+00:00"):
            return s[:-6] + "Z"
        if s.endswith("Z"):
            return s
        return s
    # Same inputs -> same timestamp (contract determinism without wall clock).
    h = int(input_sha256[:15], 16)
    offset = (h + record_count * 17) % (86400 * 365 * 40)
    dt = datetime(2000, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=int(offset))
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_experiment_dashboard(
    shadow_log_path: Path = SHADOW_LOG_PATH,
    baseline_path: Path = BASELINE_PATH,
    output_path: Path = DASHBOARD_PATH,
) -> dict[str, Any]:
    baseline_data = load_baseline_distributions(baseline_path)

    records, input_sha256 = _load_jsonl(shadow_log_path)
    schema = _validate_schema(records)
    sorted_rows = _invariance_sort(records) if schema["valid"] else records
    gate = _sample_gate(sorted_rows)
    ts_utc = _metadata_timestamp_utc(baseline_data, input_sha256, len(sorted_rows))

    dashboard: dict[str, Any] = {
        "metadata": {
            "timestamp_utc": ts_utc,
            "input_path": str(shadow_log_path.resolve()),
            "input_sha256": input_sha256,
            "spec_version": SPEC_VERSION,
            "record_count": len(sorted_rows),
            "random_seed": RANDOM_SEED,
            "bootstrap_n": BOOTSTRAP_N,
        },
        "invariance_checks": {
            "schema_valid": bool(schema["valid"]),
            "ordering": "company_then_original_index",
            "tie_handling": "average_rank_percentile_and_spearman_ranks",
            "reasons": [] if schema["valid"] else [schema.get("first_error_reason", "schema_error")],
        },
        "sample_gate": gate,
        "metrics_point_estimates": {},
        "metrics_bootstrap": {},
        "metrics_bootstrap_summary": {},
        "risk_components": {},
        "final_decision": "",
        "semantic_labels": {
            "spearman": "rank_stability_percentile_space_only",
            "inversion_rate": "ranking_perturbation_magnitude",
            "flip_rate": "decision_sensitivity",
            "mean_delta_pct": "normalized_transformation_effect_mean",
            "std_delta_pct": "normalized_transformation_effect_spread",
            "distribution_collapse_ratio": "distribution_stability_raw_std_ratio",
            "delta_pct": "v3_percentile_minus_v2_percentile_per_record",
        },
        "stress_test_summary": _stress_test_summary(),
    }

    if not schema["valid"]:
        dashboard["final_decision"] = "INVALID_SCHEMA"
        dashboard["decision_status"] = "INVALID_SCHEMA"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")
        raise ValueError(json.dumps(schema, sort_keys=True))

    if not gate["valid"]:
        dashboard["final_decision"] = "INSUFFICIENT_SAMPLE_SIZE"
        dashboard["decision_status"] = "INSUFFICIENT_SAMPLE_SIZE"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")
        return dashboard

    pairs = _paired_records(sorted_rows)
    _ensure_percentiles(pairs)

    point = _metric_point_estimates(pairs)
    boot_summary = _bootstrap_summary(pairs)
    risk = _risk_components(point, pairs)
    decision = _decision_from_risk(risk["risk"])

    dashboard["metrics_point_estimates"] = point
    dashboard["metrics_bootstrap"] = boot_summary
    dashboard["metrics_bootstrap_summary"] = boot_summary
    dashboard["risk_components"] = risk
    dashboard["final_decision"] = decision
    dashboard["decision_status"] = decision

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")
    return dashboard


if __name__ == "__main__":
    import os
    import sys

    if os.getenv("VENTURE_DEV_MAIN") != "1":
        print(
            "shadow_drift_tracker.py: direct CLI is gated. Use: "
            "python 04-coding/scripts/run_daily.py --cis\n"
            "For local debugging only, set VENTURE_DEV_MAIN=1",
            file=sys.stderr,
        )
        raise SystemExit(2)

    try:
        data = generate_experiment_dashboard()
        print(json.dumps({"final_decision": data.get("final_decision")}, sort_keys=True))
        sys.exit(0)
    except ValueError as exc:
        print(str(exc))
        sys.exit(2)
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)
