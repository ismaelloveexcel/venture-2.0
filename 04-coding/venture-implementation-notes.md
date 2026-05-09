# Venture OS — implementation notes

Personal automation workspace: scripts, contracts, and SQLite-backed state for outbound workflow. Not tied to any external product brand.

## Implemented runtime (`04-coding/scripts`)

- Economic / qualification gates, message quality checks, send caps, integrity thresholds, compliance hooks
- **Block severity** on `block_logs`: **HARD** (freeze outreach), **SOFT** (skip this send), **INFO** (observability)
- **Reply-intent** logistic filter with persisted **training rows** (`reply_intent_training_data`: features, `predicted_prob`, `actual_outcome`), weekly stale settlement, and **`reply_intent_retrain_hint.json`** for manual weight updates
- **Low-volume protection**: when trailing 7-day outbound sends are below **`REPLY_INTENT_VOLUME_THRESHOLD`**, the reply-intent filter is bypassed so the system does not over-filter early volume
- **Funnel health snapshots** after each pipeline run (`generated`, `qualified`, `sent`, `blocked`, `reply_rate_estimate`)
- **Deterministic lifecycle replay** with **`state_engine_version`** stored per opportunity (`lifecycle_engine.STATE_ENGINE_VERSION`) so replay audits catch logic drift

**Docs:** [README](../README.md), [scripts README](scripts/README.md), [venture-mcp-server README](../venture-mcp-server/README.md), [venture-engine README](venture-engine/README.md), [.env.example](../.env.example).
