"""Rule-based reply classification."""

from __future__ import annotations


def classify_reply(text: str) -> str:
    body = (text or "").strip().lower()
    if not body:
        return "neutral"

    unsubscribe_terms = (
        "unsubscribe",
        "remove me",
        "stop emailing",
        "opt out",
        "no more emails",
    )
    meeting_terms = (
        "book a call",
        "schedule",
        "calendar",
        "meet",
        "discovery call",
        "send times",
    )
    objection_terms = (
        "not interested",
        "too expensive",
        "already use",
        "no budget",
        "wrong person",
        "not a priority",
    )
    positive_terms = (
        "interested",
        "sounds good",
        "yes",
        "let us talk",
        "this is relevant",
        "thanks",
    )

    if any(term in body for term in unsubscribe_terms):
        return "unsubscribe"
    if any(term in body for term in meeting_terms):
        return "meeting_intent"
    if any(term in body for term in objection_terms):
        return "objection"
    if any(term in body for term in positive_terms):
        return "positive"
    return "neutral"
