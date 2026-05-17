"""
conftest.py — pytest configuration for event_engine tests.

Adds event_engine and scripts to sys.path so all modules can be imported.
"""

import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).parent.parent
SCRIPTS_DIR = ENGINE_DIR.parent / "scripts"

for p in (str(ENGINE_DIR), str(SCRIPTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)
