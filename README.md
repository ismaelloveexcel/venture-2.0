# Venture OS (VENTURE 2.0)

Structured workspace for idea → evaluation → build → design QA → sales → KPIs, with an automated **outreach pipeline** and **replayable lifecycle state**.

## Quick map

| Area | Path |
|------|------|
| Pipeline & scripts | `04-coding/scripts/` — see [scripts README](04-coding/scripts/README.md) |
| Engine contracts (JSON) | `04-coding/venture-engine/` — see [venture-engine README](04-coding/venture-engine/README.md) |
| Job queue, lifecycle, blocks | `venture-mcp-server/` — see [MCP server README](venture-mcp-server/README.md) |
| Copilot / agent defaults | `.github/copilot-instructions.md`, `.github/agents/` |
| Implementation notes (runtime) | `04-coding/venture-implementation-notes.md` |
| Environment template | `.env.example` |

## Operational hardening (runtime)

The pipeline and SQLite-backed `JobQueue` implement:

- **Block severity** (`HARD` / `SOFT` / `INFO`) on `block_logs` — `HARD` triggers outreach freeze.
- **Reply-intent feedback** — rows in `reply_intent_training_data` (`features_json`, `predicted_prob`, `actual_outcome`: `pending` → `replied` | `no_reply` | `not_sent`).
- **Low-volume bypass** — `REPLY_INTENT_VOLUME_THRESHOLD` (trailing 7d send count); below threshold, reply-intent pre-send filter is skipped.
- **Funnel snapshots** — `funnel_health_snapshots` after each pipeline run (`generated`, `qualified`, `sent`, `blocked`, `reply_rate_estimate`, `payload_json`).
- **Replay lock** — `opportunities.state_engine_version` aligned with `STATE_ENGINE_VERSION` in `venture-mcp-server/lifecycle_engine.py`; `replay_audit.py` reports drift.

Weekly maintenance: `04-coding/scripts/weekly_optimizer.py` settles stale reply-intent labels and writes `venture-engine/config/reply_intent_retrain_hint.json`.

## Repository

Initialize or clone as usual; copy `.env.example` → `.env`. Do not commit `.env` or local `venture_jobs.db`.

If this folder had no Git remote yet, create one on your host, then:

```text
git remote add origin <your-repo-url>
git push -u origin main
```

(Use `master` instead of `main` if that is your default branch.)
