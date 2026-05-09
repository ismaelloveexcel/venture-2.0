#!/usr/bin/env python3
"""
Venture OS preflight checks.
Validates environment and local setup before running the pipeline.
"""

from __future__ import annotations

import pathlib
import sys
from typing import List, Tuple

from dotenv import load_dotenv
from runtime_config import RuntimeConfig, preflight_messages

BASE = pathlib.Path(__file__).resolve().parents[2]
load_dotenv(BASE / ".env")


def _check_file(path: pathlib.Path, label: str) -> Tuple[bool, str]:
    if path.exists():
        return True, f"[ok] {label}: {path}"
    return False, f"[fail] {label}: missing ({path})"


def run() -> int:
    print("\n=== Venture OS Preflight ===\n")

    results: List[Tuple[bool, str]] = []

    results.append(_check_file(BASE / ".env", ".env"))
    results.append(_check_file(BASE / "04-coding" / "scripts" / "venture_pipeline.py", "Pipeline script"))
    results.append(_check_file(BASE / "04-coding" / "scripts" / "dashboard.py", "Dashboard script"))
    results.append(_check_file(BASE / "06-sales" / "prospects.csv", "Prospects CSV"))

    cfg = RuntimeConfig.from_env()
    results.extend(preflight_messages(cfg))

    ok = True
    for passed, line in results:
        print(line)
        ok = ok and passed

    print("\n=== Preflight Result ===")
    if ok:
        print("[ok] Ready to run pipeline")
        return 0

    print("[fail] Setup incomplete. Fix the [fail] items above and re-run.")
    return 1


if __name__ == "__main__":
    sys.exit(run())
