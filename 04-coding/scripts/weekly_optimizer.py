#!/usr/bin/env python3
"""
Weekly optimizer v1 — consumes trust deltas, block reasons, CTA outcomes, and
lifecycle transitions; emits bounded suggestions (scoring weights, CTA policy,
discovery targeting). Does not auto-apply changes (operator reviews JSON).
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List

BASE = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE / "venture-mcp-server"))

from job_queue import JobQueue  # noqa: E402
DB_PATH = BASE / "venture_jobs.db"
SCORING_CONFIG = BASE / "04-coding" / "venture-engine" / "config" / "scoring.config.json"
OUTPUT_PATH = BASE / "04-coding" / "venture-engine" / "config" / "optimizer_output.json"
REPLY_INTENT_RETRAIN_PATH = BASE / "04-coding" / "venture-engine" / "config" / "reply_intent_retrain_hint.json"

MAX_WEIGHT_NUDGE = 0.03


def _cutoff_iso(days: int = 7) -> str:
    return (datetime.now() - timedelta(days=days)).isoformat()


def _load_json(path: pathlib.Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _aggregate_trust(conn: sqlite3.Connection, since: str) -> Dict[str, Any]:
    rows = conn.execute(
        """
        SELECT event_type, SUM(trust_delta), COUNT(*)
        FROM trust_events WHERE created_at >= ?
        GROUP BY event_type
        """,
        [since],
    ).fetchall()
    by_type: Dict[str, Dict[str, float]] = {}
    for et, s, c in rows:
        by_type[str(et)] = {"sum_delta": float(s or 0), "count": int(c or 0)}
    return by_type


def _aggregate_blocks(conn: sqlite3.Connection, since: str) -> Dict[str, int]:
    rows = conn.execute(
        """
        SELECT reason, COUNT(*) FROM block_logs
        WHERE created_at >= ?
        GROUP BY reason
        """,
        [since],
    ).fetchall()
    return {str(r): int(n) for r, n in rows}


def _aggregate_lifecycle(conn: sqlite3.Connection, since: str) -> Dict[str, Any]:
    rows = conn.execute(
        """
        SELECT event_type, COUNT(*) FROM lifecycle_events
        WHERE created_at >= ?
        GROUP BY event_type
        """,
        [since],
    ).fetchall()
    counts = {str(et): int(n) for et, n in rows}

    cta_rows = conn.execute(
        """
        SELECT payload FROM lifecycle_events
        WHERE created_at >= ? AND event_type = 'cta_selected'
        """,
        [since],
    ).fetchall()
    cta_usage: Counter[str] = Counter()
    for (raw,) in cta_rows:
        try:
            p = json.loads(raw or "{}")
            ct = str(p.get("cta_type", "") or "")
            if ct:
                cta_usage[ct] += 1
        except json.JSONDecodeError:
            continue

    trans_rows = conn.execute(
        """
        SELECT id FROM lifecycle_events
        WHERE created_at >= ? AND event_type IN ('replied', 'clicked', 'qualified')
        """,
        [since],
    ).fetchall()
    return {
        "event_counts": counts,
        "cta_selected": dict(cta_usage),
        "positive_signal_rows": len(trans_rows),
    }


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        [name],
    ).fetchone()
    return row is not None


def _build_suggestions(
    trust: Dict[str, Any],
    blocks: Dict[str, int],
    lifecycle: Dict[str, Any],
    current_weights: Dict[str, float],
) -> Dict[str, Any]:
    weight_nudge: Dict[str, float] = {k: 0.0 for k in current_weights}
    notes: List[str] = []

    total_blocks = sum(blocks.values()) or 1
    firewall_share = sum(
        blocks.get(k, 0) for k in blocks if "firewall" in k.lower() or "capacity" in k.lower()
    ) / total_blocks
    quality_share = sum(blocks.get(k, 0) for k in blocks if "quality" in k.lower()) / total_blocks

    if firewall_share > 0.35:
        weight_nudge["reachability"] += MAX_WEIGHT_NUDGE * 0.5
        weight_nudge["urgency"] -= MAX_WEIGHT_NUDGE * 0.4
        notes.append("high_firewall_block_share: nudge reachability up, urgency down")

    if quality_share > 0.25:
        weight_nudge["pain"] += MAX_WEIGHT_NUDGE * 0.4
        weight_nudge["ai_fit"] -= MAX_WEIGHT_NUDGE * 0.2
        notes.append("high_message_quality_blocks: nudge pain signal weight up")

    opened = trust.get("opened", {}).get("count", 0)
    replied = trust.get("replied", {}).get("count", 0)
    if opened >= 10 and replied == 0:
        weight_nudge["reachability"] += MAX_WEIGHT_NUDGE * 0.6
        notes.append("opens_without_replies: prioritize reachability / list hygiene")

    lc = lifecycle.get("event_counts", {})
    if lc.get("replied", 0) >= 3:
        weight_nudge["budget"] += MAX_WEIGHT_NUDGE * 0.3
        notes.append("healthy_reply_volume: slight budget-weight increase")

    for k in weight_nudge:
        weight_nudge[k] = max(-MAX_WEIGHT_NUDGE, min(MAX_WEIGHT_NUDGE, weight_nudge[k]))

    suggested_weights = {k: round(float(current_weights.get(k, 0)) + weight_nudge.get(k, 0), 4) for k in current_weights}
    ssum = sum(max(0.01, v) for v in suggested_weights.values())
    if ssum > 0:
        suggested_weights = {k: round(v / ssum, 4) for k, v in suggested_weights.items()}

    cta_counts = lifecycle.get("cta_selected") or {}
    cta_policy: Dict[str, Any] = {"notes": [], "bias": {}}
    if cta_counts:
        top = max(cta_counts, key=lambda x: cta_counts[x])
        cta_policy["notes"].append(f"dominant_cta_last_period:{top}")
        if top == "show_example" and replied == 0 and opened >= 5:
            cta_policy["bias"]["prefer_choice_breakdown"] = True
            cta_policy["notes"].append("suggest_more_choice_breakdown_vs_show_example")

    discovery: Dict[str, Any] = {"notes": []}
    if quality_share > 0.2:
        discovery["notes"].append("tighten_vertical_or_evidence_thresholds")
    if firewall_share > 0.4:
        discovery["notes"].append("reduce_aggressive_cta_verticals_until_integrity_improves")

    return {
        "weight_nudges": weight_nudge,
        "suggested_weights": suggested_weights,
        "cta_policy": cta_policy,
        "discovery_targeting": discovery,
        "notes": notes,
    }


def _build_reply_intent_retrain_hint(conn: sqlite3.Connection) -> Dict[str, Any]:
    rows = conn.execute("""
        SELECT predicted_prob, actual_outcome FROM reply_intent_training_data
        WHERE actual_outcome IN ('replied', 'no_reply', 'not_sent')
    """).fetchall()
    replied = [float(r[0]) for r in rows if r[1] == "replied"]
    no_reply = [float(r[0]) for r in rows if r[1] == "no_reply"]
    not_sent = [float(r[0]) for r in rows if r[1] == "not_sent"]

    def _mean(xs: List[float]) -> Any:
        return round(sum(xs) / len(xs), 4) if xs else None

    mr, mn = _mean(replied), _mean(no_reply)
    hint = ""
    suggested_intercept_nudge = 0.0
    if mr is not None and mn is not None:
        if mr > mn + 0.05:
            hint = "model_rank_order_sane_replies_higher"
        elif mn > mr + 0.05:
            hint = "consider_lowering_intercept_or_review_features"
            suggested_intercept_nudge = -0.05
        else:
            hint = "insufficient_separation_collect_more_labeled_rows"

    return {
        "n_replied": len(replied),
        "n_no_reply": len(no_reply),
        "n_not_sent": len(not_sent),
        "mean_predicted_replied": mr,
        "mean_predicted_no_reply": mn,
        "mean_predicted_not_sent": _mean(not_sent),
        "hint": hint,
        "suggested_intercept_nudge": suggested_intercept_nudge,
        "manual_step": "Merge suggested_intercept_nudge into reply_intent.model.json intercept after review",
    }


def main() -> int:
    if not DB_PATH.exists():
        print(f"[weekly_optimizer] No database at {DB_PATH}; nothing to analyze.")
        return 0

    since = _cutoff_iso(7)
    scoring = _load_json(SCORING_CONFIG)
    weights = scoring.get("weights") or {}

    conn = sqlite3.connect(DB_PATH)
    try:
        trust = _aggregate_trust(conn, since) if _table_exists(conn, "trust_events") else {}
        blocks = _aggregate_blocks(conn, since) if _table_exists(conn, "block_logs") else {}
        if _table_exists(conn, "lifecycle_events"):
            lifecycle = _aggregate_lifecycle(conn, since)
        else:
            lifecycle = {"event_counts": {}, "cta_selected": {}, "positive_signal_rows": 0}
    finally:
        conn.close()

    suggestions = _build_suggestions(trust, blocks, lifecycle, weights)

    settled = 0
    retrain_hint: Dict[str, Any] = {}
    if DB_PATH.exists():
        jq = JobQueue(db_path=str(DB_PATH))
        settled = jq.settle_reply_intent_stale_pending(10.0)
        conn_r = sqlite3.connect(DB_PATH)
        try:
            if _table_exists(conn_r, "reply_intent_training_data"):
                retrain_hint = _build_reply_intent_retrain_hint(conn_r)
        finally:
            conn_r.close()

    out: Dict[str, Any] = {
        "generated_at": datetime.now().isoformat(),
        "period_days": 7,
        "since": since,
        "inputs": {
            "trust_by_type": trust,
            "block_reasons": blocks,
            "lifecycle": lifecycle,
        },
        "outputs": suggestions,
        "reply_intent": {
            "stale_pending_settled_to_no_reply": settled,
            "retrain_hint": retrain_hint,
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
        f.write("\n")

    if retrain_hint:
        with open(REPLY_INTENT_RETRAIN_PATH, "w", encoding="utf-8") as f:
            json.dump(retrain_hint, f, indent=2)
            f.write("\n")
        print(f"[weekly_optimizer] Wrote {REPLY_INTENT_RETRAIN_PATH}")

    print(f"[weekly_optimizer] Wrote {OUTPUT_PATH}")

    eng = BASE / "04-coding" / "venture-engine"
    if str(eng) not in sys.path:
        sys.path.insert(0, str(eng))
    try:
        from reply_intent_trainer import run_weekly_retrain  # noqa: E402

        tr = run_weekly_retrain(
            db_path=DB_PATH,
            model_path=BASE / "04-coding" / "venture-engine" / "config" / "reply_intent.model.json",
        )
        print(f"[weekly_optimizer] reply_intent_trainer: {tr}")
    except Exception as exc:  # noqa: BLE001
        print(f"[weekly_optimizer] reply_intent_trainer skipped: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
