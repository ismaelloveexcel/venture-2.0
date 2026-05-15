"""Ensure fast subset manifest stays non-empty and runnable."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fast_test_subset import FAST_TEST_PATHS

ROOT = Path(__file__).resolve().parents[1]
FAST_SUBSET = ROOT / "04-coding" / "scripts" / "fast_test_subset.py"


def test_fast_test_paths_cover_money_path_and_contract():
    joined = "\n".join(FAST_TEST_PATHS)
    assert len(FAST_TEST_PATHS) >= 3
    assert len(FAST_TEST_PATHS) == len(set(FAST_TEST_PATHS))
    assert all((ROOT / p).is_file() for p in FAST_TEST_PATHS)
    assert "money_path" in joined
    assert "run_report_contract" in joined


def test_fast_test_subset_script_exits_zero():
    proc = subprocess.run(
        [sys.executable, str(FAST_SUBSET)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
