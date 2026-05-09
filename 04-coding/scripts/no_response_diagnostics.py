"""
No-response diagnostics for identifying silent outreach failures.
"""

from __future__ import annotations

from typing import Dict

from job_queue import JobQueue


def analyze_no_response_patterns(queue: JobQueue, days: int = 7) -> Dict[str, str]:
    funnel = queue.get_funnel_counts(days=days)
    sent = int(funnel.get("email_sent", 0))
    opened = int(funnel.get("opened", 0))
    clicked = int(funnel.get("clicked", 0))
    replied = int(funnel.get("replied", 0))

    if sent == 0:
        return {"status": "insufficient_data", "diagnosis": "no messages sent"}

    if opened <= max(2, int(sent * 0.1)):
        return {"status": "warning", "diagnosis": "low_opens_subject_or_targeting_issue"}
    if opened > 0 and replied == 0 and clicked > 0:
        return {"status": "warning", "diagnosis": "opens_and_clicks_no_replies_evidence_or_cta_issue"}
    if opened > 0 and replied == 0:
        return {"status": "warning", "diagnosis": "opens_no_replies_cta_or_message_quality_issue"}
    return {"status": "healthy", "diagnosis": "response_pattern_within_expected_range"}
