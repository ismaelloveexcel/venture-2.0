#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = ROOT / "07-kpis" / "operator_execution_log.csv"
CFG_PATH = ROOT / "04-coding" / "config" / "gates.json"
OUT_JSON = ROOT / "07-kpis" / "gate_status.json"
PAUSE_PATH = ROOT / "04-coding" / "state" / "operator_pause_state.json"


def _read_cfg() -> dict:
    if CFG_PATH.is_file():
        return json.loads(CFG_PATH.read_text(encoding="utf-8"))
    return {
        "gate_a": {"weekly_pass_threshold_pct": 90, "daily_stop_loss_threshold_pct": 80},
        "gate_b": {"baseline_positive_reply_rate_pct": 1.5},
    }


def _bool_cell(v: str) -> int:
    return 1 if str(v).strip().upper() == "Y" else 0


def _safe_int(v: str) -> int:
    try:
        return int(float(str(v).strip() or 0))
    except ValueError:
        return 0


def _latest_row() -> dict | None:
    if not LOG_PATH.is_file():
        return None
    with LOG_PATH.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[-1] if rows else None


def main() -> int:
    cfg = _read_cfg()
    row = _latest_row()
    status = {
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gate_a_score_pct": 0.0,
        "gate_a_pass": False,
        "gate_b_positive_reply_rate_pct": 0.0,
        "gate_b_pass": False,
        "stop_loss_triggered": False,
        "reasons": [],
    }
    if row is None:
        status["reasons"].append("operator_log_missing_or_empty")
    else:
        checks = [
            _bool_cell(row.get("pivot_compliant", "")),
            _bool_cell(row.get("sla_client_compliant", "")),
            _bool_cell(row.get("sla_operator_compliant", "")),
            _bool_cell(row.get("stop_loss_compliant", "")),
            _bool_cell(row.get("deliverability_compliant", "")),
        ]
        schema_pct = max(0.0, min(100.0, float(row.get("schema_completeness_pct", "0") or 0)))
        gate_a = ((sum(checks) / len(checks)) * 0.8 + (schema_pct / 100.0) * 0.2) * 100.0
        status["gate_a_score_pct"] = round(gate_a, 2)
        status["gate_a_pass"] = gate_a >= float(cfg["gate_a"]["weekly_pass_threshold_pct"])

        delivered = max(0, _safe_int(row.get("delivered_count", "0")))
        positive = max(0, _safe_int(row.get("positive_replies", "0")))
        prr = (positive / delivered * 100.0) if delivered > 0 else 0.0
        status["gate_b_positive_reply_rate_pct"] = round(prr, 3)
        status["gate_b_pass"] = (
            _safe_int(row.get("qualified_conversations", "0")) > 0
            or prr >= float(cfg["gate_b"]["baseline_positive_reply_rate_pct"])
        )

        stop_loss_y = str(row.get("stop_loss_triggered", "")).strip().upper() == "Y"
        if stop_loss_y:
            status["reasons"].append("stop_loss_flagged_in_log")
        if gate_a < float(cfg["gate_a"]["daily_stop_loss_threshold_pct"]):
            status["reasons"].append("gate_a_below_daily_stop_loss_threshold")
        status["stop_loss_triggered"] = bool(status["reasons"])

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")

    PAUSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    pause = {
        "paused": bool(status["stop_loss_triggered"]),
        "updated_at_utc": status["timestamp_utc"],
        "reasons": status["reasons"],
    }
    PAUSE_PATH.write_text(json.dumps(pause, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
