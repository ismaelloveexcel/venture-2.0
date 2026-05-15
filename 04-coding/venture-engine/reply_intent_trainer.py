"""
Weekly reply-intent model refresh (Phase B).

Reads reply_intent_training_data (pending | no_reply | not_sent | replied),
applies small bounded weight nudges, writes config/reply_intent.model.json.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

MAX_WEIGHT_NUDGE = 0.03
MODEL_REL = Path("04-coding") / "venture-engine" / "config" / "reply_intent.model.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def run_weekly_retrain(
    *,
    db_path: Path | None = None,
    model_path: Path | None = None,
) -> dict[str, Any]:
    repo = _repo_root()
    db = db_path or (repo / "venture_jobs.db")
    out = model_path or (repo / MODEL_REL)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not db.is_file():
        return {"ok": False, "error": "database_missing", "path": str(db)}

    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='reply_intent_training_data' LIMIT 1
            """
        ).fetchone()
        if not row:
            return {"ok": False, "error": "training_table_missing"}
        rows = conn.execute(
            """
            SELECT features_json, predicted_prob, actual_outcome
            FROM reply_intent_training_data
            WHERE actual_outcome IN ('replied', 'no_reply', 'not_sent', 'pending')
            """
        ).fetchall()
    finally:
        conn.close()

    replied_feats: list[dict[str, Any]] = []
    neg_feats: list[dict[str, Any]] = []
    for raw, _pred, outcome in rows:
        try:
            feats = json.loads(raw or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(feats, dict):
            continue
        o = str(outcome or "").strip().lower()
        if o == "replied":
            replied_feats.append(feats)
        elif o in {"no_reply", "not_sent", "pending"}:
            neg_feats.append(feats)

    base: dict[str, Any] = {}
    if out.is_file():
        try:
            base = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            base = {}
    if not base:
        base = {
            "schema": 1,
            "intercept": -0.35,
            "min_prob_send_default": 0.12,
            "weights": {},
        }
    weights: dict[str, float] = {str(k): float(v) for k, v in (base.get("weights") or {}).items()}

    def _mean(keys: Iterable[str], bucket: list[dict[str, Any]]) -> dict[str, float]:
        acc = {k: 0.0 for k in keys}
        if not bucket:
            return acc
        for f in bucket:
            for k in keys:
                v = f.get(k)
                try:
                    acc[k] += float(v) if v is not None else 0.0
                except (TypeError, ValueError):
                    pass
        n = float(len(bucket))
        return {k: acc[k] / n for k in keys}

    keys = sorted({k for f in replied_feats + neg_feats for k in f if isinstance(k, str)})
    if not keys or not replied_feats or not neg_feats:
        base["trainer_note"] = "insufficient_contrast_rows"
        out.write_text(json.dumps(base, indent=2) + "\n", encoding="utf-8")
        return {"ok": True, "skipped": True, "rows": len(rows)}

    mr = _mean(keys, replied_feats)
    mn = _mean(keys, neg_feats)
    for k in keys:
        delta = mr.get(k, 0.0) - mn.get(k, 0.0)
        nudge = max(-MAX_WEIGHT_NUDGE, min(MAX_WEIGHT_NUDGE, delta * 0.1))
        prev = float(weights.get(k, 0.0))
        weights[k] = max(-1.0, min(1.5, prev + nudge))

    base["weights"] = weights
    base["trainer_note"] = "weekly_retrain_phase_b"
    out.write_text(json.dumps(base, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "rows": len(rows), "path": str(out)}


def main() -> int:
    r = run_weekly_retrain()
    print(json.dumps(r, indent=2))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
