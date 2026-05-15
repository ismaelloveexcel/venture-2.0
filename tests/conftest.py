"""Pytest bootstrap: scripts on PYTHONPATH for flat imports."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "04-coding" / "scripts"
MCP = ROOT / "venture-mcp-server"
for p in (SCRIPTS, MCP):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
