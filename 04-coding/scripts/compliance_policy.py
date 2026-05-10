"""
Live-mode compliance cooldown policy: fail-closed on unreadable config, once-per-run messaging.

Used by venture_pipeline.send_email and follow-up phase. Tests import this module in isolation.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class _ComplianceCooldownRunState:
    evaluated: bool = False
    ok: bool = True
    days: int = 0
    reason: str = ""
    logged_block: bool = False


_state = _ComplianceCooldownRunState()


def reset_compliance_cooldown_policy_for_run() -> None:
    global _state
    _state = _ComplianceCooldownRunState()


def evaluate_compliance_cooldown_for_run(*, dry_run: bool, config_path: Path) -> None:
    """
    Idempotent per process after reset. Live mode requires readable JSON and cooldown_days_after_no_reply.
    Dry-run: permissive (missing key -> 0 days, warning only).
    """
    global _state
    if _state.evaluated:
        return
    _state.evaluated = True
    if dry_run:
        _state.ok = True
        _state.days = _load_cooldown_days_permissive(config_path)
        return
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("compliance config root must be an object")
        if "cooldown_days_after_no_reply" not in data:
            _state.ok = False
            _state.reason = "compliance_policy_block:missing_key:cooldown_days_after_no_reply"
        else:
            _state.days = max(0, int(data.get("cooldown_days_after_no_reply") or 0))
    except Exception as e:
        _state.ok = False
        _state.reason = f"compliance_policy_block:config_unreadable:{e}"
    if not _state.ok and not _state.logged_block:
        logger.error("Outbound compliance policy failed: %s", _state.reason)
        print(
            f"\n[fail] Outbound disabled for this run: {_state.reason}\n"
            "Non-transactional sends will be skipped until the config is fixed.\n"
        )
        _state.logged_block = True


def get_compliance_cooldown_days_for_send(*, dry_run: bool) -> Tuple[int, Optional[str]]:
    """
    Returns (cooldown_days, block_reason). When block_reason is set, non-transactional sends must not proceed.
    """
    if not _state.evaluated:
        raise RuntimeError("evaluate_compliance_cooldown_for_run must run first")
    if dry_run:
        return _state.days, None
    if not _state.ok:
        return 0, _state.reason
    return _state.days, None


def describe_compliance_policy_line(*, dry_run: bool, config_path: Path) -> str:
    """One-line summary for operator status (re-evaluates from disk for --status)."""
    reset_compliance_cooldown_policy_for_run()
    evaluate_compliance_cooldown_for_run(dry_run=dry_run, config_path=config_path)
    if dry_run:
        return f"cooldown (dry-run permissive): {_state.days}d  config={config_path}"
    if not _state.ok:
        return f"cooldown: BLOCKED  reason={_state.reason}  config={config_path}"
    return f"cooldown: OK  {_state.days}d after no reply  config={config_path}"


def _load_cooldown_days_permissive(config_path: Path) -> int:
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
        if "cooldown_days_after_no_reply" not in data:
            logger.warning(
                "compliance.config.json has no cooldown_days_after_no_reply; using 0 days (dry-run)"
            )
        raw = data.get("cooldown_days_after_no_reply", 0) if isinstance(data, dict) else 0
        return max(0, int(raw or 0))
    except Exception as e:
        logger.warning("Could not read compliance cooldown config (%s); using 0 days (dry-run)", e)
        return 0
