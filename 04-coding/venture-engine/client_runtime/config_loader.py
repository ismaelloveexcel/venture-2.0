"""
Client config loader — JSON validation and normalization only.

NO business logic. NO pipeline awareness.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ICP:
    """Ideal Customer Profile definition."""

    industry: str = ""
    job_titles: list[str] = field(default_factory=list)
    company_size_range: str = ""
    geography: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ICP:
        return cls(
            industry=data.get("industry", ""),
            job_titles=data.get("job_titles", []),
            company_size_range=data.get("company_size_range", ""),
            geography=data.get("geography", []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "industry": self.industry,
            "job_titles": self.job_titles,
            "company_size_range": self.company_size_range,
            "geography": self.geography,
        }


@dataclass
class TargetSource:
    """Where prospects come from."""

    type: str = "csv"  # csv | apollo | manual
    reference: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TargetSource:
        return cls(
            type=data.get("type", "csv"),
            reference=data.get("reference", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "reference": self.reference,
        }


@dataclass
class OfferContext:
    """What you're selling."""

    value_proposition: str = ""
    pain_point: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OfferContext:
        return cls(
            value_proposition=data.get("value_proposition", ""),
            pain_point=data.get("pain_point", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "value_proposition": self.value_proposition,
            "pain_point": self.pain_point,
        }


@dataclass
class Messaging:
    """Message generation parameters."""

    tone: str = "consultative"  # consultative | direct | aggressive
    personalization_level: str = "medium"  # low | medium | high

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Messaging:
        return cls(
            tone=data.get("tone", "consultative"),
            personalization_level=data.get("personalization_level", "medium"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tone": self.tone,
            "personalization_level": self.personalization_level,
        }


@dataclass
class Constraints:
    """Execution constraints."""

    daily_send_limit: int = 0
    approval_mode: str = "auto"  # auto | manual

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Constraints:
        return cls(
            daily_send_limit=int(data.get("daily_send_limit", 0)),
            approval_mode=data.get("approval_mode", "auto"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "daily_send_limit": self.daily_send_limit,
            "approval_mode": self.approval_mode,
        }


@dataclass
class Tracking:
    """What metrics to track."""

    metrics: list[str] = field(default_factory=lambda: ["reply", "meeting"])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Tracking:
        return cls(
            metrics=data.get("metrics", ["reply", "meeting"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"metrics": self.metrics}


@dataclass
class Reporting:
    """Client reporting config."""

    email: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Reporting:
        return cls(email=data.get("email", ""))

    def to_dict(self) -> dict[str, Any]:
        return {"email": self.email}


@dataclass
class ClientConfig:
    """Minimal client configuration schema."""

    client_id: str
    campaign_name: str
    icp: ICP
    target_source: TargetSource
    offer_context: OfferContext
    messaging: Messaging
    constraints: Constraints
    tracking: Tracking
    reporting: Reporting

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "campaign_name": self.campaign_name,
            "icp": self.icp.to_dict(),
            "target_source": self.target_source.to_dict(),
            "offer_context": self.offer_context.to_dict(),
            "messaging": self.messaging.to_dict(),
            "constraints": self.constraints.to_dict(),
            "tracking": self.tracking.to_dict(),
            "reporting": self.reporting.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClientConfig:
        return cls(
            client_id=data.get("client_id", ""),
            campaign_name=data.get("campaign_name", ""),
            icp=ICP.from_dict(data.get("icp", {})),
            target_source=TargetSource.from_dict(data.get("target_source", {})),
            offer_context=OfferContext.from_dict(data.get("offer_context", {})),
            messaging=Messaging.from_dict(data.get("messaging", {})),
            constraints=Constraints.from_dict(data.get("constraints", {})),
            tracking=Tracking.from_dict(data.get("tracking", {})),
            reporting=Reporting.from_dict(data.get("reporting", {})),
        )


def validate_client_config(config: ClientConfig) -> list[str]:
    """
    Validate required fields.

    Returns list of errors (empty if valid).
    """
    errors: list[str] = []

    if not config.client_id or not config.client_id.strip():
        errors.append("client_id: required")
    if not config.campaign_name or not config.campaign_name.strip():
        errors.append("campaign_name: required")
    if not config.icp.industry or not config.icp.industry.strip():
        errors.append("icp.industry: required")
    if not config.target_source.type or not config.target_source.type.strip():
        errors.append("target_source.type: required")
    if config.target_source.type.lower() not in ("csv", "apollo", "manual"):
        errors.append(
            f"target_source.type: must be 'csv', 'apollo', or 'manual' (got {config.target_source.type!r})"
        )
    if not config.offer_context.value_proposition:
        errors.append("offer_context.value_proposition: required")
    if not config.offer_context.pain_point:
        errors.append("offer_context.pain_point: required")
    if not config.messaging.tone:
        errors.append("messaging.tone: required")
    if not config.reporting.email:
        errors.append("reporting.email: required")

    return errors


def load_client_config(config_path: str | Path) -> ClientConfig:
    """
    Load and validate client config from JSON file.

    Raises ValueError if validation fails.
    """
    config_path = Path(config_path)
    if not config_path.is_file():
        raise ValueError(f"Config file not found: {config_path}")

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {config_path}: {e}") from e

    config = ClientConfig.from_dict(data)
    errors = validate_client_config(config)
    if errors:
        raise ValueError(
            f"Config validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    return config
