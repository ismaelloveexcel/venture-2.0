"""
System Integrity Monitor for Venture pipeline safety.
Blocks outbound when system metrics indicate silent degradation.
"""

from __future__ import annotations

import os
import pathlib
import sys
from dataclasses import dataclass
from typing import Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "venture-mcp-server"))
from job_queue import JobQueue


@dataclass
class IntegrityReport:
    healthy: bool
    should_block_outreach: bool
    reasons: List[str]
    metrics: Dict[str, float]


def evaluate_integrity(queue: JobQueue) -> IntegrityReport:
    summary = queue.get_summary()
    funnel_7d = queue.get_funnel_counts(days=7)
    funnel_24h = queue.get_funnel_counts_since_hours(hours=24)

    loaded = float(funnel_7d.get("prospect_loaded", 0))
    sent = float(funnel_7d.get("email_sent", 0))
    replied = float(funnel_7d.get("replied", 0))
    blocked = float(len(queue.get_blocked_prospects(limit=200)))
    failed_jobs = float(summary.get("failed", 0) + summary.get("abandoned", 0))
    sent_24h = float(funnel_24h.get("email_sent", 0))
    replied_24h = float(funnel_24h.get("replied", 0))

    reply_rate = (replied / sent) if sent > 0 else 0.0
    reply_rate_24h = (replied_24h / sent_24h) if sent_24h > 0 else 0.0
    block_ratio = (blocked / loaded) if loaded > 0 else 0.0

    min_reply_rate = float(os.environ.get("INTEGRITY_MIN_REPLY_RATE", "0.03"))
    min_reply_rate_24h = float(os.environ.get("INTEGRITY_MIN_REPLY_RATE_24H", "0.02"))
    max_reply_delta_drop = float(os.environ.get("INTEGRITY_MAX_REPLY_DROP_DELTA", "0.08"))
    max_block_ratio = float(os.environ.get("INTEGRITY_MAX_BLOCK_RATIO", "0.6"))
    max_failed_jobs = float(os.environ.get("INTEGRITY_MAX_FAILED_JOBS", "25"))

    reasons: List[str] = []
    if sent >= 25 and reply_rate < min_reply_rate:
        reasons.append(f"reply_rate_below_threshold ({reply_rate:.3f} < {min_reply_rate:.3f})")
    if sent_24h >= 10 and reply_rate_24h < min_reply_rate_24h:
        reasons.append(f"reply_rate_24h_below_threshold ({reply_rate_24h:.3f} < {min_reply_rate_24h:.3f})")
    if sent >= 25 and sent_24h >= 10 and (reply_rate - reply_rate_24h) > max_reply_delta_drop:
        reasons.append(f"reply_rate_delta_drop ({(reply_rate-reply_rate_24h):.3f} > {max_reply_delta_drop:.3f})")
    if loaded >= 25 and block_ratio > max_block_ratio:
        reasons.append(f"block_ratio_above_threshold ({block_ratio:.3f} > {max_block_ratio:.3f})")
    if failed_jobs > max_failed_jobs:
        reasons.append(f"failed_jobs_above_threshold ({failed_jobs:.0f} > {max_failed_jobs:.0f})")

    should_block = len(reasons) > 0
    return IntegrityReport(
        healthy=not should_block,
        should_block_outreach=should_block,
        reasons=reasons,
        metrics={
            "loaded_7d": loaded,
            "sent_7d": sent,
            "replied_7d": replied,
            "reply_rate_7d": round(reply_rate, 4),
            "sent_24h": sent_24h,
            "replied_24h": replied_24h,
            "reply_rate_24h": round(reply_rate_24h, 4),
            "blocked_open": blocked,
            "block_ratio_7d": round(block_ratio, 4),
            "failed_jobs_open": failed_jobs,
        },
    )
