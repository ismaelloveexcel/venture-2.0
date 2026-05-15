"""Deterministic campaign state machine."""

from __future__ import annotations

from typing import Final

VALID_CAMPAIGN_STATES: Final[tuple[str, ...]] = (
    "draft",
    "approved",
    "queued",
    "running",
    "paused",
    "completed",
    "failed",
)

ALLOWED_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "draft": frozenset({"approved", "failed"}),
    "approved": frozenset({"queued", "paused", "failed"}),
    "queued": frozenset({"running", "paused", "failed"}),
    "running": frozenset({"paused", "completed", "failed"}),
    "paused": frozenset({"queued", "running", "failed"}),
    "completed": frozenset(),
    "failed": frozenset(),
}


class CampaignStateTransitionError(ValueError):
    """Raised when a campaign state transition is invalid."""


def normalize_campaign_state(value: str) -> str:
    state = (value or "").strip().lower()
    if state not in VALID_CAMPAIGN_STATES:
        raise CampaignStateTransitionError(f"invalid campaign state: {value!r}")
    return state


def can_transition_campaign_state(from_state: str, to_state: str) -> bool:
    src = normalize_campaign_state(from_state)
    dst = normalize_campaign_state(to_state)
    return dst in ALLOWED_TRANSITIONS[src]


def transition_campaign_state(from_state: str, to_state: str) -> str:
    src = normalize_campaign_state(from_state)
    dst = normalize_campaign_state(to_state)
    if dst == src:
        return src
    if not can_transition_campaign_state(src, dst):
        raise CampaignStateTransitionError(
            f"invalid campaign transition: {src!r} -> {dst!r}"
        )
    return dst
