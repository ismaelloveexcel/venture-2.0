# Independent Agent Review Protocol

Purpose: eliminate guesswork during external or autonomous review by defining exact truth sources, commands, and acceptance gates.

## 1. Truth Hierarchy (strict)

1. [README.md](../README.md)
2. [04-coding/venture-implementation-notes.md](../04-coding/venture-implementation-notes.md)
3. [AGENTS.md](../AGENTS.md)
4. [docs/SEMANTIC_CONTRACT.md](SEMANTIC_CONTRACT.md)
5. [04-coding/scripts/README.md](../04-coding/scripts/README.md)

If documents conflict, follow the order above and report the conflict explicitly in findings.

## 2. Non-Negotiable Runtime Facts

- Canonical orchestrator: [04-coding/scripts/run_daily.py](../04-coding/scripts/run_daily.py)
- Governed execution path: [04-coding/scripts/venture_pipeline.py](../04-coding/scripts/venture_pipeline.py)
- Run report contract source: [04-coding/scripts/run_report_schema.py](../04-coding/scripts/run_report_schema.py)
- Atomic report writer/parser: [04-coding/scripts/run_report_writer.py](../04-coding/scripts/run_report_writer.py)
- Runtime governance engine: [04-coding/scripts/runtime_governance.py](../04-coding/scripts/runtime_governance.py)
- SQLite queue/lifecycle DB: venture_jobs.db at repo root

## 3. Required Review Commands

Run from repo root in this exact order:

```powershell
.venv\Scripts\python -m pytest tests -q
.venv\Scripts\python 04-coding\scripts\validate_repo_contract.py
.venv\Scripts\python 04-coding\scripts\run_daily.py --execute-outbound --dry-run
```

Optional fast gate (subset + contract):

```powershell
.venv\Scripts\python 04-coding\scripts\run_daily.py bridge validate
```

## 4. Evidence You Must Capture

- Test pass/fail status and failing test names (if any)
- Contract validation pass/fail status
- Dry-run completion status including outbound status and pipeline child exit code
- Confirmed location of generated [run_report.json](../run_report.json)
- Whether [docs/solo-operator/overview.html](solo-operator/overview.html) renders current report values without console/runtime errors

## 5. Forbidden Assumptions

- Do not assume alternate CLIs are production entrypoints.
- Do not infer product positioning from legacy or vendor comparison docs.
- Do not treat dashboard visuals as truth; backend report fields are truth.
- Do not redefine schema fields outside [04-coding/scripts/run_report_schema.py](../04-coding/scripts/run_report_schema.py).
- Do not modify outbound behavior outside guarded modules and contracts.

## 6. Review Output Format (required)

1. Critical findings (severity-ordered) with file evidence links
2. Open questions or data gaps
3. Change summary
4. Go/No-Go recommendation with rationale

If no issues are found, explicitly state: "No critical findings. Residual risk: <short note>."
