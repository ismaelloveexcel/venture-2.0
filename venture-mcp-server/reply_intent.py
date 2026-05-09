"""
Minimal reply-intent scorer (logistic linear model, interpretable weights).
No sklearn dependency — coefficients live in venture-engine/config/reply_intent.model.json.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Optional

_DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parent.parent
    / "04-coding"
    / "venture-engine"
    / "config"
    / "reply_intent.model.json"
)


def _sigmoid(z: float) -> float:
    z = max(-60.0, min(60.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def load_model(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or _DEFAULT_MODEL_PATH
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def build_feature_dict(
    message: str,
    *,
    cta_type: str,
    trust_score: float,
    evidence_confidence: float,
    vertical: str,
    state: str,
    industry: str = "",
) -> Dict[str, float]:
    wc = len((message or "").split())
    low = (message or "").lower()
    has_evidence = 1.0 if ("http" in low or "%" in low or "saved" in low or "lost" in low) else 0.0
    return {
        "log_word_count": math.log1p(wc) / 5.0,
        "has_evidence_marker": has_evidence,
        "cta_strength": 0.4 if cta_type in {"call_optional", "calendar_allowed"} else 0.15,
        "trust": max(-1.0, min(1.5, float(trust_score))),
        "evidence_confidence": max(0.0, min(1.0, float(evidence_confidence))),
        "state_warm": 1.0 if state == "WARM" else 0.0,
        "state_engaged": 1.0 if state == "ENGAGED" else 0.0,
        "state_qualified": 1.0 if state == "QUALIFIED" else 0.0,
        "vertical_known": 1.0 if (vertical or industry) else 0.0,
    }


def predict_reply_probability(
    message: str,
    *,
    cta_type: str,
    trust_score: float,
    evidence_confidence: float,
    vertical: str,
    state: str,
    industry: str = "",
    model: Optional[Dict[str, Any]] = None,
    model_path: Optional[Path] = None,
) -> float:
    m = model if model is not None else load_model(model_path)
    feats = build_feature_dict(
        message,
        cta_type=cta_type,
        trust_score=trust_score,
        evidence_confidence=evidence_confidence,
        vertical=vertical,
        state=state,
        industry=industry,
    )
    z = float(m.get("intercept", 0.0))
    for k, coef in (m.get("weights") or {}).items():
        z += float(coef) * float(feats.get(k, 0.0))
    return _sigmoid(z)
