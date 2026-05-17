# runtime_contract.md — Execution State Machine Source of Truth
# Version: 1.0.0 | Status: LOCKED (PR1 Baseline)

---

## §1 — Ownership Model

### FastAPI (control plane — stateless)
- Manages its own HTTP/WebSocket lifecycle
- Delegates session creation requests to SessionManager
- Owns event dispatcher lifecycle (streaming)
- Performs NO computation on execution state

### SessionManager (exclusive authority)
- **Sole generator of `run_id`** — no `uuid4` call for run_id is permitted anywhere else
- Owns the full session lifecycle and state transitions
- Enforces state machine rules (invalid transitions raise `InvalidTransitionError`)
- Thread-safe by design

### venture_pipeline (pure computation kernel)
- Pure computation only — no import-time side effects (INV-1)
- No I/O at module scope (no `load_dotenv`, no `setup_logging`, no `get_queue` at module scope)
- No `datetime.now()` without UTC — always use `datetime.now(timezone.utc)`
- No `uuid4()` for `run_id` generation anywhere outside SessionManager

---

## §2 — Function Contract Table

| Function | Input | Return Type | Side Effects |
|----------|-------|-------------|--------------|
| `filter_prospects_for_outbound` | raw dataset | `list[ProspectRecord]` | logs only |
| `run_outbound_batch` | `BatchConfig` | `BatchResult` | logs only |
| `emit_governance_event` | payload | `NormalizedEvent` | none |
| `evaluate_compliance_cooldown` | context | `ComplianceResult` | none |
| `build_runtime_governance` | config | `RuntimeGovernanceModel` | none |

All functions at public boundaries MUST return typed dataclasses, never `dict` or `None`.

---

## §3 — Domain Types

```python
@dataclass(frozen=True)
class ProspectRecord:
    company_name: str
    domain: str
    name: str
    email: str
    role: str
    industry: str
    validation_status: str
    run_id: str

@dataclass(frozen=True)
class BatchResult:
    run_id: str
    session_id: str
    attempted: int
    sent: int
    blocked: int
    events: list
    reasons: list[str]

@dataclass(frozen=True)
class GovernanceEvent:
    event_id: str
    session_id: str
    severity: str
    description: str
    timestamp: str

@dataclass(frozen=True)
class FailureEvent:
    event_id: str
    session_id: str
    job_id: str
    reason: str
    retry_count: int
    timestamp: str

@dataclass(frozen=True)
class NormalizedEvent:
    event_id: str
    session_id: str
    run_id: str
    event_type: str
    severity: str      # INFO | SOFT | HARD
    timestamp: str
    sequence: int
    description: str
    metadata: dict[str, object]   # typed dict — not untyped
```

---

## §4 — Single Pipeline Rule

Demo and real execution ALWAYS converge through the same normalizer:

```
DemoEventGenerator  RealExecution
         \               /
          \             /
           ↓           ↓
            Normalizer
                ↓
   Replay → Query → FastAPI → WebSocket → UI
```

- No `is_demo` or `source` fields in the envelope post-normalization (INV-7)
- Events are immutable after normalization (frozen dataclass)
- The normalizer is the single pipeline entry point

---

## §5 — Execution State Model

### States
```
pending → running → paused → awaiting_approval → completed
                           ↘                  ↗
                             failed
```

| State | Description |
|-------|-------------|
| `pending` | Session created, execution not started |
| `running` | Execution in progress |
| `paused` | Operator-initiated pause |
| `awaiting_approval` | Governance escalation; blocked pending operator decision |
| `failed` | Terminal — execution failed |
| `completed` | Terminal — execution succeeded |

### Valid Transitions
| From | To | Trigger |
|------|----|---------|
| `pending` | `running` | `start` command |
| `running` | `paused` | `pause` command |
| `running` | `awaiting_approval` | HARD governance event |
| `running` | `failed` | fatal error |
| `running` | `completed` | batch complete |
| `paused` | `running` | `resume` command |
| `awaiting_approval` | `running` | `approve` command |
| `awaiting_approval` | `failed` | `reject` command |

### run_id Rule
- **ONLY `SessionManager.create_session()` generates run_id**
- Format: `run-{ulid}` (deterministic from seed in demo mode)
- No `uuid4()` call for run_id is valid anywhere outside `session_manager.py`

---

## §6 — Demo Scenarios

Three deterministic scenarios feed the real normalizer:

| Key | Description | Terminal State |
|-----|-------------|----------------|
| `clean_run` | Happy path — all sends succeed | `completed` |
| `governance_escalation` | HARD block → awaiting_approval → approved → completed | `completed` |
| `retry_failure` | Retry cycle → terminal failure | `failed` |

Signature:
```python
def generate_scenario(scenario_key: str) -> list[NormalizedEvent]:
    ...
```
Must be deterministic: same `scenario_key` always produces identical event sequences.

---

## §7 — Architectural Invariants

| ID | Rule |
|----|------|
| INV-1 | `import venture_pipeline` has zero side effects |
| INV-2 | Single event pipeline — no branching post-normalization |
| INV-3 | No untyped `dict` / `None` returns at boundaries |
| INV-4 | `CommandValidator` is stateless, no execution logic |
| INV-5 | UI contains no execution logic |
| INV-6 | Persistence only via event sinks |
| INV-7 | Events immutable post-normalization |

---

## §8 — API Endpoints (FastAPI Control Plane)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check → `{"status": "ok"}` |
| GET | `/status` | Session counts by state |
| GET | `/sessions` | List all sessions |
| GET | `/sessions/{id}` | Get session detail + current state |
| GET | `/sessions/{id}/events` | Get all events for session |
| GET | `/sessions/{id}/replay` | Replay events in sequence order |
| WS  | `/sessions/{id}/stream` | Live event stream (PR2) |
| POST| `/sessions/{id}/command` | Send command to session (PR2) |
| GET | `/query/{path:path}` | Generic query pass-through |

---

## §9 — Phase A Exit Checklist

- [x] runtime_contract.md exists
- [x] All 4 + 1 dataclasses defined (ProspectRecord, BatchResult, GovernanceEvent, FailureEvent, NormalizedEvent)
- [x] Function contract table complete
- [x] State model complete with valid transitions
- [x] Demo scenarios defined (3)
- [x] FastAPI endpoint list defined
- [x] Contract covers all 6 required sections

_FastAPI starts cleanly verification: `pytest 04-coding/event_engine/tests/test_pr1.py`_
