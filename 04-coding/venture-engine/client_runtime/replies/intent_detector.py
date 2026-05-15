"""Deterministic phrase extraction for reply intelligence."""

from __future__ import annotations


def _extract_matching_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    body = (text or "").strip().lower()
    return [phrase for phrase in phrases if phrase in body]


def extract_objections(text: str) -> list[str]:
    return _extract_matching_phrases(
        text,
        (
            "not interested",
            "too expensive",
            "already use",
            "no budget",
            "wrong person",
            "not a priority",
        ),
    )


def extract_positive_intent_phrases(text: str) -> list[str]:
    return _extract_matching_phrases(
        text,
        (
            "interested",
            "sounds good",
            "looks good",
            "happy to",
            "keen to",
            "let us talk",
        ),
    )


def extract_cta_requests(text: str) -> list[str]:
    return _extract_matching_phrases(
        text,
        (
            "send times",
            "book a call",
            "schedule",
            "calendar link",
            "next week",
            "tomorrow",
        ),
    )
