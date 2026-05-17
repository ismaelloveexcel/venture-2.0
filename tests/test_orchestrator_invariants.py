"""
Repository Orchestrator Invariant Test Suite
Strictly enforces orchestration, artifact, and execution invariants.
Fails on any architectural drift, bypass, or artifact identity regression.
"""

import os
import re
import sys
import importlib
import subprocess
import glob
import pytest

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(REPO_ROOT, ".."))

# 1. Forbidden direct venture_pipeline.py invocation patterns
FORBIDDEN_PATTERNS = [
    r"os\.system\(.*venture_pipeline\.py",
    r"subprocess\.(Popen|call|run)\(.*venture_pipeline\.py",
    r"PowerShell.*venture_pipeline\.py",
    r"VS ?Code.*task.*venture_pipeline\.py",
    r"import +venture_pipeline",
    r"from +venture_pipeline",
]

# 2. Whitelist exceptions
WHITELIST = [
    # Internal self-reference
    ("04-coding/scripts/venture_pipeline.py", r"(import|from) \+venture_pipeline"),
    # Test-only imports
    ("tests/", r"(import|from) \+venture_pipeline"),
    # Contract validator (subprocess import-purity check)
    (
        "04-coding/event_engine/validate_contract.py",
        r"(import|from) \+venture_pipeline",
    ),
    # Explicit dev-only override
    (
        "04-coding/scripts/venture_pipeline.py",
        r"if +os\.environ\.get\([\'\"]VENTURE_DEV_MAIN[\'\"]",
    ),
]


def file_matches_any_pattern(filepath, patterns):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    matches = [p for p in patterns if re.search(p, content)]
    if filepath.endswith(".md"):
        matches = [
            p
            for p in matches
            if p not in {r"import +venture_pipeline", r"from +venture_pipeline"}
        ]
    return matches


def is_whitelisted(filepath, pattern):
    normalized_path = filepath.replace("\\", "/")
    for allowed_path, allowed_pattern in WHITELIST:
        if allowed_path in normalized_path and re.search(allowed_pattern, pattern):
            return True
    return False


def test_forbidden_venture_pipeline_invocations():
    failures = []
    for root, dirs, files in os.walk(REPO_ROOT):
        for fname in files:
            if not fname.endswith(
                (
                    ".py",
                    ".md",
                    ".json",
                    ".yml",
                    ".yaml",
                    ".sh",
                    ".ps1",
                    ".bat",
                    ".ts",
                    ".js",
                )
            ):
                continue
            fpath = os.path.join(root, fname)
            relpath = os.path.relpath(fpath, REPO_ROOT)
            matches = file_matches_any_pattern(fpath, FORBIDDEN_PATTERNS)
            for pattern in matches:
                if not is_whitelisted(relpath, pattern):
                    failures.append(f"{relpath}: forbidden pattern '{pattern}' found")
    assert (
        not failures
    ), f"Forbidden venture_pipeline.py invocations found:\n" + "\n".join(failures)


def test_canonical_entry_enforcement():
    # Check that all execution wrappers enforce VENTURE_CANONICAL_ENTRY
    wrappers = glob.glob(os.path.join(REPO_ROOT, "04-coding/scripts/*.py"))
    failures = []
    for wrapper in wrappers:
        with open(wrapper, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if "run_daily.py" in wrapper or "venture_pipeline.py" in wrapper:
            if "VENTURE_CANONICAL_ENTRY" not in content:
                failures.append(os.path.relpath(wrapper, REPO_ROOT))
    assert not failures, f"Missing VENTURE_CANONICAL_ENTRY enforcement in: {failures}"


def test_artifact_integrity():
    # Check manifest, projection, and run_report for run_id parity
    import json

    manifest_path = os.path.join(REPO_ROOT, "run_report.json")
    if not os.path.exists(manifest_path):
        pytest.skip("run_report.json not present")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    run_id = manifest.get("run_id")
    assert run_id, "manifest missing run_id"
    # Check for projection/run_id parity if projection exists
    projection_path = os.path.join(REPO_ROOT, "04-coding/reports/projection.json")
    if os.path.exists(projection_path):
        with open(projection_path, "r", encoding="utf-8") as f:
            projection = json.load(f)
        assert projection.get("run_id") == run_id, "projection.run_id mismatch"
    # Renderer fails hard on mismatch (simulate)
    if os.path.exists(projection_path):
        try:
            assert projection["run_id"] == manifest["run_id"]
        except Exception:
            raise AssertionError("Renderer must fail on run_id mismatch")


def test_run_daily_canonical_execution(monkeypatch):
    # run_daily.py must refuse execution without VENTURE_CANONICAL_ENTRY=1
    run_daily = os.path.join(REPO_ROOT, "04-coding/scripts/run_daily.py")
    if not os.path.exists(run_daily):
        pytest.skip("run_daily.py not present")
    # Should fail without env
    result = subprocess.run(
        [sys.executable, run_daily, "--execute"],
        capture_output=True,
        text=True,
        env={**os.environ, "VENTURE_CANONICAL_ENTRY": ""},
    )
    assert (
        result.returncode != 0
    ), "run_daily.py should refuse execution without VENTURE_CANONICAL_ENTRY=1"
    # Should succeed with env
    result2 = subprocess.run(
        [sys.executable, run_daily, "--execute"],
        capture_output=True,
        text=True,
        env={**os.environ, "VENTURE_CANONICAL_ENTRY": "1"},
    )
    assert (
        result2.returncode == 0
    ), "run_daily.py should succeed with VENTURE_CANONICAL_ENTRY=1"
    # Bridge status allowed
    result3 = subprocess.run(
        [sys.executable, run_daily, "bridge", "validate"],
        capture_output=True,
        text=True,
        env={**os.environ, "VENTURE_CANONICAL_ENTRY": "1"},
    )
    assert (
        result3.returncode == 0
    ), "run_daily.py bridge validate should succeed with VENTURE_CANONICAL_ENTRY=1"
