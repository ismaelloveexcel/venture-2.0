#!/usr/bin/env python3
"""Update 04-coding/.venture_phase_state.json after PHASE_PASS (human-invoked)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ORDER = ["P3", "P4", "P5", "P6"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Mark a Venture OS phase complete and advance current_phase")
    parser.add_argument("phase", help="Phase just passed, e.g. P3")
    args = parser.parse_args()
    phase = args.phase.strip().upper()
    if phase not in ORDER:
        print("advance_venture_phase: only P3, P4, P5, or P6 are supported.", flush=True)
        return 2
    repo = Path(__file__).resolve().parents[2]
    path = repo / "04-coding" / ".venture_phase_state.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    done = data.setdefault("completed", [])
    if phase not in done:
        done.append(phase)
    if phase in ORDER:
        i = ORDER.index(phase)
        data["current_phase"] = ORDER[i + 1] if i + 1 < len(ORDER) else "DONE"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"current_phase": data["current_phase"], "completed": done}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
