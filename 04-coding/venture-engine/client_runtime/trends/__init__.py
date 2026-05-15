"""Historical trend intelligence layer."""

from __future__ import annotations

from .trend_engine import build_trend_outputs

generate_trend_outputs = build_trend_outputs

__all__ = ["build_trend_outputs", "generate_trend_outputs"]
