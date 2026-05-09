# Venture Engine V1 Contracts

JSON and SQL **contracts** for the **Venture OS** pipeline: your offer, scoring, vertical economics, compliance, and reply-intent model. These files configure **your** revenue engine — they are not a public multi-tenant product schema.

This directory contains:

- `config/offer.config.json`: locked offer definition
- `config/scoring.config.json`: scoring weights and viability thresholds
- `config/verticals.config.json`: vertical ticket and deal constraints
- `config/compliance.config.json`: channel and opt-out policy
- `config/reply_intent.model.json`: logistic weights + feature order for **reply-intent** pre-send scoring (used by `venture-mcp-server/reply_intent.py` and `venture_pipeline.py`)
- `db/schema.sql`: baseline relational model
- `db/migrations/001_baseline.sql`: migration marker

These contracts are intended to be enforced by runtime services, not treated as optional guidance.

## Weekly optimizer outputs

`04-coding/scripts/weekly_optimizer.py` writes:

- `config/optimizer_output.json` — aggregated trust/optimizer signals (includes a `reply_intent` section when training data exists)
- `config/reply_intent_retrain_hint.json` — suggested calibration from labeled `reply_intent_training_data` (merge manually into `reply_intent.model.json` until an automated trainer is added)

## Runtime data (SQLite, not in this folder)

The live pipeline persists operational metrics in **`04-coding/scripts/venture_jobs.db`** (gitignored). Relevant artifacts:

| Artifact | Table / column | Notes |
|----------|----------------|--------|
| Block typing + **severity** | `block_logs.block_type`, `block_logs.severity` | `HARD` → global outreach freeze |
| Reply-intent training | `reply_intent_training_data` | `features_json`, `predicted_prob`, `actual_outcome` |
| Funnel KPI row | `funnel_health_snapshots` | Per run: `generated`, `qualified`, `sent`, `blocked`, `reply_rate_estimate`, `payload_json` |
| Replay lock | `opportunities.state_engine_version` | Must match `STATE_ENGINE_VERSION` in `venture-mcp-server/lifecycle_engine.py` for current logic |

Environment variables for reply-intent and low-volume bypass are documented in **`.env.example`** (`REPLY_INTENT_ENABLED`, `REPLY_INTENT_MIN_PROB`, `REPLY_INTENT_VOLUME_THRESHOLD`).
