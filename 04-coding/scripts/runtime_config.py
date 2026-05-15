"""
Shared runtime configuration and validation for Venture OS scripts.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Tuple


def resolve_data_base(repo_root: Path | None = None) -> Path:
    """
    Canonical data root for prospect + pipeline artifacts (Option B).

    Same rule as ``venture_pipeline``: ``VENTURE_CLIENT_WORKSPACE`` if set,
    else ``repo_root`` (repository root).
    """
    root = repo_root or Path(__file__).resolve().parents[2]
    ws = os.environ.get("VENTURE_CLIENT_WORKSPACE", "").strip()
    if ws:
        return Path(ws).expanduser().resolve()
    return root


def resolve_venture_db_path(data_base: Path, repo_root: Path) -> Path:
    """SQLite path for job_queue / suppression (matches venture_pipeline defaults)."""
    env = os.environ.get("VENTURE_DB_PATH", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    if os.environ.get("VENTURE_CLIENT_WORKSPACE", "").strip():
        return data_base / "database.sqlite"
    return repo_root / "venture_jobs.db"

_PLACEHOLDER_HINTS = ("...", "your", "example", "secret_")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _is_effective_secret(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    lowered = v.lower()
    if any(hint in lowered for hint in _PLACEHOLDER_HINTS):
        return False
    return True


def _valid_notion_id(value: str) -> bool:
    normalized = (value or "").replace("-", "")
    return bool(re.fullmatch(r"[0-9a-fA-F]{32}", normalized))


@dataclass(frozen=True)
class RuntimeConfig:
    openai_api_key: str
    apollo_api_key: str
    hunter_api_key: str
    airtable_api_key: str
    airtable_base_id: str
    airtable_prospects_table: str
    airtable_kpis_table: str
    notion_api_key: str
    notion_prospects_db: str
    notion_kpis_db: str
    resend_api_key: str
    resend_from_email: str
    resend_from_name: str
    digest_to_email: str
    auto_send_emails: bool
    followup_days: int
    revenue_target: int
    reply_intent_enabled: bool
    reply_intent_min_prob: float
    reply_intent_volume_threshold: int
    motion_hot_threshold: int
    motion_possible_threshold: int
    motion_hot_cap: int
    motion_possible_sample_size: int
    motion_shadow_mode: bool
    spend_filter_required: bool
    spend_min_trigger_count: int
    # === V3 CIS CONFIGURATION ===
    cis_routing_mode: str  # "dual_shadow", "v2_only", "v3_only"
    cis_hot_threshold: int  # CIS score threshold for HOT band (default 80)
    cis_possible_threshold: int  # CIS score threshold for POSSIBLE band (default 50)

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        return cls(
            openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
            apollo_api_key=os.environ.get("APOLLO_API_KEY", "").strip(),
            hunter_api_key=os.environ.get("HUNTER_API_KEY", "").strip(),
            airtable_api_key=os.environ.get("AIRTABLE_API_KEY", "").strip(),
            airtable_base_id=os.environ.get("AIRTABLE_BASE_ID", "").strip(),
            airtable_prospects_table=os.environ.get(
                "AIRTABLE_PROSPECTS_TABLE", "Prospects"
            ).strip(),
            airtable_kpis_table=os.environ.get(
                "AIRTABLE_KPIS_TABLE", "WeeklyKPIs"
            ).strip(),
            notion_api_key=os.environ.get("NOTION_API_KEY", "").strip(),
            notion_prospects_db=os.environ.get("NOTION_PROSPECTS_DB", "").strip(),
            notion_kpis_db=os.environ.get("NOTION_KPIS_DB", "").strip(),
            resend_api_key=os.environ.get("RESEND_API_KEY", "").strip(),
            resend_from_email=os.environ.get("RESEND_FROM_EMAIL", "").strip(),
            resend_from_name=os.environ.get(
                "RESEND_FROM_NAME", "Ismael Sudally"
            ).strip(),
            digest_to_email=os.environ.get("DIGEST_TO_EMAIL", "").strip(),
            auto_send_emails=_env_bool("AUTO_SEND_EMAILS", False),
            followup_days=_env_int("FOLLOWUP_DAYS", 4),
            revenue_target=_env_int("REVENUE_TARGET", 10000),
            reply_intent_enabled=_env_bool("REPLY_INTENT_ENABLED", False),
            reply_intent_min_prob=_env_float("REPLY_INTENT_MIN_PROB", 0.12),
            reply_intent_volume_threshold=_env_int("REPLY_INTENT_VOLUME_THRESHOLD", 12),
            motion_hot_threshold=_env_int("MOTION_HOT_THRESHOLD", 7),
            motion_possible_threshold=_env_int("MOTION_POSSIBLE_THRESHOLD", 5),
            motion_hot_cap=_env_int("MOTION_HOT_CAP", 25),
            motion_possible_sample_size=_env_int("MOTION_POSSIBLE_SAMPLE_SIZE", 10),
            motion_shadow_mode=_env_bool("MOTION_SHADOW_MODE", True),
            spend_filter_required=_env_bool("SPEND_FILTER_REQUIRED", True),
            spend_min_trigger_count=_env_int("SPEND_MIN_TRIGGER_COUNT", 1),
            # === V3 CIS CONFIGURATION ===
            cis_routing_mode=os.environ.get("CIS_ROUTING_MODE", "dual_shadow").strip().lower(),
            cis_hot_threshold=_env_int("CIS_HOT_THRESHOLD", 80),
            cis_possible_threshold=_env_int("CIS_POSSIBLE_THRESHOLD", 50),
        )


def build_config_status(cfg: RuntimeConfig) -> Dict[str, bool]:
    return {
        "OPENAI_API_KEY": _is_effective_secret(cfg.openai_api_key),
        "APOLLO_API_KEY": _is_effective_secret(cfg.apollo_api_key),
        "HUNTER_API_KEY": _is_effective_secret(cfg.hunter_api_key),
        "NOTION_API_KEY": _is_effective_secret(cfg.notion_api_key),
        "AIRTABLE_API_KEY": _is_effective_secret(cfg.airtable_api_key),
        "RESEND_API_KEY": _is_effective_secret(cfg.resend_api_key),
    }


def collect_config_warnings(cfg: RuntimeConfig) -> List[str]:
    warnings: List[str] = []
    status = build_config_status(cfg)

    for key, is_set in status.items():
        if not is_set:
            warnings.append(f"{key} not set (feature disabled)")

    if status["NOTION_API_KEY"]:
        if not cfg.notion_prospects_db:
            warnings.append("NOTION_PROSPECTS_DB missing while NOTION_API_KEY is set")
        elif not _valid_notion_id(cfg.notion_prospects_db):
            warnings.append(
                "NOTION_PROSPECTS_DB invalid format (expected 32 hex chars)"
            )

        if not cfg.notion_kpis_db:
            warnings.append("NOTION_KPIS_DB missing while NOTION_API_KEY is set")
        elif not _valid_notion_id(cfg.notion_kpis_db):
            warnings.append("NOTION_KPIS_DB invalid format (expected 32 hex chars)")

    if status["AIRTABLE_API_KEY"] and not cfg.airtable_base_id:
        warnings.append("AIRTABLE_BASE_ID missing while AIRTABLE_API_KEY is set")

    if cfg.auto_send_emails:
        if not status["RESEND_API_KEY"]:
            warnings.append("AUTO_SEND_EMAILS=true but RESEND_API_KEY is not set")
        if not cfg.resend_from_email:
            warnings.append("AUTO_SEND_EMAILS=true but RESEND_FROM_EMAIL is not set")
        try:
            from batch_guard import get_test_approval_state

            approved, reason = get_test_approval_state()
        except Exception as exc:
            approved, reason = False, str(exc)
        if not approved:
            warnings.append(
                f"AUTO_SEND_EMAILS=true but batch.lock test approval is not valid ({reason})"
            )

    return warnings


def collect_live_mode_blockers(cfg: RuntimeConfig) -> List[str]:
    blockers: List[str] = []
    status = build_config_status(cfg)
    required = ("OPENAI_API_KEY", "HUNTER_API_KEY", "NOTION_API_KEY")
    for key in required:
        if not status[key]:
            blockers.append(f"{key} must be configured for live mode")

    blockers.extend(
        issue
        for issue in collect_config_warnings(cfg)
        if "missing while" in issue
        or "invalid format" in issue
        or issue.startswith("AUTO_SEND_EMAILS=true")
    )
    return blockers


def preflight_messages(cfg: RuntimeConfig) -> List[Tuple[bool, str]]:
    checks: List[Tuple[bool, str]] = []
    status = build_config_status(cfg)
    for key, is_set in status.items():
        checks.append(
            (
                True,
                f"{'[ok]' if is_set else '[warn]'} {key} {'set' if is_set else 'not set (feature disabled)'}",
            )
        )

    for warning in collect_config_warnings(cfg):
        if warning.endswith("not set (feature disabled)"):
            continue
        is_fail = "missing while" in warning or "invalid format" in warning
        checks.append((not is_fail, f"{'[fail]' if is_fail else '[warn]'} {warning}"))
    return checks
