#!/usr/bin/env python3
"""
Preflight Check for Day 8 Execution

Validates all keys, dependencies, and file paths before Day 8 scripts run.
Usage: python preflight_check_day8.py
"""

import os
import sys
import pathlib
from dotenv import load_dotenv

BASE = pathlib.Path(__file__).resolve().parents[2]
load_dotenv(BASE / ".env")


def check_env_keys() -> bool:
    """Validate API keys in .env"""
    issues = []

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    hunter_key = os.environ.get("HUNTER_API_KEY", "").strip()

    print("\n=== API Keys ===")

    if not openai_key:
        issues.append("OPENAI_API_KEY missing")
        print("[❌] OPENAI_API_KEY not found")
    elif not openai_key.startswith("sk-"):
        issues.append("OPENAI_API_KEY format invalid (should start with 'sk-')")
        print("[❌] OPENAI_API_KEY format invalid (should start with 'sk-')")
    else:
        print(f"[✅] OPENAI_API_KEY found (starts with sk-...)")

    if not hunter_key:
        print("[⚠️]  HUNTER_API_KEY not set (will use template data)")
    elif not hunter_key.startswith(("hunt", "key_")):
        print("[⚠️]  HUNTER_API_KEY format unusual")
    else:
        print(f"[✅] HUNTER_API_KEY found")

    return len(issues) == 0


def check_dependencies() -> bool:
    """Validate Python dependencies"""
    issues = []

    print("\n=== Dependencies ===")

    deps = ["dotenv", "httpx", "csv"]
    for dep in deps:
        try:
            __import__(dep)
            print(f"[✅] {dep}")
        except ImportError:
            issues.append(f"Missing: {dep}")
            print(f"[❌] {dep} not installed")

    # Check for resilience module (venture-mcp-server)
    mcp_path = BASE / "venture-mcp-server"
    if not mcp_path.exists():
        issues.append(f"venture-mcp-server directory missing at {mcp_path}")
        print(f"[❌] venture-mcp-server directory not found")
    else:
        print(f"[✅] venture-mcp-server found")

    return len(issues) == 0


def check_directories() -> bool:
    """Validate necessary directories exist"""
    issues = []

    print("\n=== Directories ===")

    dirs = [
        BASE / "06-sales",
        BASE / "07-kpis",
        BASE / "04-coding" / "scripts",
    ]

    for dir_path in dirs:
        if dir_path.exists():
            print(f"[✅] {dir_path.name}")
        else:
            issues.append(f"Directory missing: {dir_path}")
            print(f"[❌] {dir_path}")

    return len(issues) == 0


def main() -> int:
    """Run all preflight checks"""
    print("\n" + "=" * 60)
    print("DAY 8 PREFLIGHT CHECK")
    print("=" * 60)

    checks = [
        ("API Keys", check_env_keys),
        ("Dependencies", check_dependencies),
        ("Directories", check_directories),
    ]

    results = []
    for name, check_fn in checks:
        try:
            results.append(check_fn())
        except Exception as e:
            print(f"[❌] {name} check failed: {e}")
            results.append(False)

    # Summary
    print("\n" + "=" * 60)
    if all(results):
        print("[✅] ALL CHECKS PASSED - Ready for Day 8 execution!")
        print("\nNext steps:")
        print("  1. python prospect_builder.py")
        print("  2. python message_generator_solo.py")
        print("  3. python review_queue.py")
        print("=" * 60 + "\n")
        return 0
    else:
        print("[❌] SOME CHECKS FAILED - Fix issues above before proceeding")
        print("\nFix required before Day 8:")
        print("  - Add OPENAI_API_KEY to .env")
        print("  - Optionally add HUNTER_API_KEY to .env (or run with --demo)")
        print("=" * 60 + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
