# venture-mcp-server

Shared Python modules for the Venture job queue, lifecycle replay, and MCP server.

## Modules

| Module | Role |
|--------|------|
| `job_queue.py` | SQLite `JobQueue`: jobs, outbound/suppression, **block logs with severity**, trust, opportunities, lifecycle events/snapshots, **`reply_intent_training_data`**, **`funnel_health_snapshots`**, weekly send counts |
| `lifecycle_engine.py` | Deterministic **`replay_outreach_state`** from ordered events; exports **`STATE_ENGINE_VERSION`** (bump when replay rules change) |
| `lifecycle_validation.py` | Payload validation for lifecycle writes |
| `reply_intent.py` | Feature extraction + probability from `reply_intent.model.json` |
| `outreach_state_machine.py` | Signal → state transitions |
| `resilience.py` | Retries, rate limiting |
| `server.py` | MCP server entry |

## Block severity

`JobQueue.log_block(..., severity=...)` persists `block_logs.severity`:

- **`HARD`** — sets outreach freeze (`system_control`); use for integrity/capacity/compliance stops.
- **`SOFT`** — log + skip current action (e.g. one send) without freezing the whole system.
- **`INFO`** — observability-only; same storage as `SOFT` unless callers branch on severity.

Default severity can be inferred from `block_type` when omitted.

## Replay version lock

On lifecycle writes, **`opportunities.state_engine_version`** is updated to match `lifecycle_engine.STATE_ENGINE_VERSION`. Older rows keep the version they were last written with so audits can detect **historical reinterpretation drift** after code changes.

## Requirements

See `requirements.txt`. Consumers (e.g. `04-coding/scripts/*.py`) extend `sys.path` to import these modules.
