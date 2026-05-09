"""
Message variation helper to avoid repetitive outreach fingerprints.
"""

from __future__ import annotations

import hashlib


VARIANT_OPENERS = [
    "I checked your setup quickly and noticed something specific.",
    "I took a quick look at your lead flow and spotted a gap.",
    "I ran a short check on your site and found one issue worth sharing.",
]


def select_variant_seed(seed_value: str) -> int:
    digest = hashlib.sha256(seed_value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def choose_opener(seed_value: str) -> str:
    idx = select_variant_seed(seed_value) % len(VARIANT_OPENERS)
    return VARIANT_OPENERS[idx]
