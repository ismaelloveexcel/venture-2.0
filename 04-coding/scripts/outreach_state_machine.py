"""Shim: canonical outreach_state_machine lives in venture-mcp-server."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_pkg = Path(__file__).resolve().parent.parent.parent / "venture-mcp-server" / "outreach_state_machine.py"
_spec = importlib.util.spec_from_file_location("venture_outreach_state_machine", _pkg)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

globals().update({k: v for k, v in _mod.__dict__.items() if not k.startswith("_")})
