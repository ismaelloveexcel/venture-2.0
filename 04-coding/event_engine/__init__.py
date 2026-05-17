"""
event_engine — Replayable event-sourced execution state machine.

Architecture:
  Backend  → event-sourced execution state machine
  API      → control plane (stateless)
  UI       → projection layer (no computation)

Import this package; it has zero side effects (INV-1).
"""

from __future__ import annotations

__version__ = "1.0.0"
