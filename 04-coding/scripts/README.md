# Venture OS — automation scripts

Python entrypoints for outreach generation, sending, trust/integrity gates, and weekly optimization.

## Primary commands

| Script | Purpose |
|--------|---------|
| `venture_pipeline.py` | End-to-end: enrich, draft, gates (qualification, quality, capacity, reply-intent, compliance), send, lifecycle events, funnel snapshot |
| `weekly_optimizer.py` | Weekly run: trust aggregates, settle stale `reply_intent_training_data` (`pending` → `no_reply`), emit retrain hints into `venture-engine/config/` |
| `replay_audit.py` | Replay lifecycle state from SQLite; flag `state_engine_version` drift vs `lifecycle_engine.STATE_ENGINE_VERSION` |
| `integration_test.py` | Resilience + job queue + lifecycle replay smoke tests |

Run from this directory (or repo root with adjusted paths). Example:

```powershell
cd 04-coding/scripts
uv run --with httpx --with python-dotenv python venture_pipeline.py --dry-run
uv run python weekly_optimizer.py
uv run python replay_audit.py
uv run python integration_test.py
```

## Database

Default SQLite path: **`04-coding/scripts/venture_jobs.db`** (same directory as these scripts). Schema is created/migrated by `venture-mcp-server/job_queue.py` on first use.

Notable tables for operations:

- `block_logs` — `block_type`, **`severity`** (`HARD` freezes outreach; `SOFT` / `INFO` do not)
- `reply_intent_training_data` — training rows for reply-intent model calibration
- `funnel_health_snapshots` — one row per pipeline run summary
- `opportunities` / `lifecycle_events` — replayable state; **`state_engine_version`** per opportunity

## Configuration

- **Runtime**: `runtime_config.py` (loads `.env` from repo root)
- **Reply-intent model**: `../venture-engine/config/reply_intent.model.json`
- **Retrain hints** (weekly output): `../venture-engine/config/reply_intent_retrain_hint.json`, merged into `optimizer_output.json`

See root **`README.md`**, **`../venture-implementation-notes.md`**, and **`../venture-engine/README.md`** for runtime summary, contracts, and env vars (`REPLY_INTENT_*`, integrity thresholds, caps).
