"""Deterministic weighted ranking for pattern memory."""

from __future__ import annotations


def score_pattern(*, sent: int, replies: int, qualified: int, appearances: int) -> float:
    if appearances <= 0:
        return 0.0
    sent_safe = max(1, int(sent))
    reply_rate = float(replies) / sent_safe
    qualification_rate = float(qualified) / sent_safe
    support = min(1.0, appearances / 10.0)
    score = (reply_rate * 0.5) + (qualification_rate * 0.35) + (support * 0.15)
    return round(score * 100.0, 4)
