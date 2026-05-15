#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import shadow_drift_tracker as tracker


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic paired CIS evaluation runner"
    )
    parser.add_argument("--input", required=True, help="Input JSONL path")
    parser.add_argument("--output", required=True, help="Output dashboard JSON path")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    try:
        dashboard = tracker.generate_experiment_dashboard(
            shadow_log_path=input_path,
            baseline_path=tracker.BASELINE_PATH,
            output_path=output_path,
        )
    except ValueError as exc:
        try:
            payload = json.loads(str(exc))
        except Exception:
            payload = {"error": str(exc)}
        print(json.dumps(payload, sort_keys=True))
        return 2
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 4

    if dashboard.get("final_decision") == "INSUFFICIENT_SAMPLE_SIZE":
        print(json.dumps(dashboard.get("sample_gate", {}), sort_keys=True))
        return 3

    print(f"PIPELINE_STATUS: {dashboard.get('final_decision', 'UNKNOWN')}")
    print(f"RECORDS: {dashboard.get('metadata', {}).get('record_count', 0)}")
    print(f"RISK: {dashboard.get('risk_components', {}).get('risk', 0.0)}")
    return 0


if __name__ == "__main__":
    if os.getenv("VENTURE_DEV_MAIN") != "1":
        print(
            "run_pipeline.py: direct CLI is gated. Use: "
            "python 04-coding/scripts/run_daily.py --cis\n"
            "For local debugging only, set VENTURE_DEV_MAIN=1",
            file=sys.stderr,
        )
        raise SystemExit(2)
    raise SystemExit(main())
