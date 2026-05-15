#!/usr/bin/env python3
"""Generate deterministic, solo-operator architecture docs and single-file overview."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StepDef:
    key: str
    check_token: str
    title: str
    detail: str


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[2]
DOCS_DIR = REPO_ROOT / "docs" / "solo-operator"
RUN_DAILY_PATH = REPO_ROOT / "04-coding" / "scripts" / "run_daily.py"
CLIENT_RUNTIME_DIR = REPO_ROOT / "04-coding" / "venture-engine" / "client_runtime"

WATCH_PATHS = [
    REPO_ROOT / "04-coding" / "scripts" / "run_daily.py",
    REPO_ROOT / "04-coding" / "venture-engine" / "client_runtime",
    REPO_ROOT / "04-coding" / "venture-engine" / "reporting",
]

STEP_DEFS: list[StepDef] = [
    StepDef(
        "campaign_report",
        "build_campaign_report_artifacts(",
        "Create campaign report files",
        "The run report is converted into campaign report files for review.",
    ),
    StepDef(
        "client_folder",
        "get_client_router(",
        "Prepare client run folder",
        "A client folder and run folder are ensured before writing delivery files.",
    ),
    StepDef(
        "save_run_report",
        "run_report_path",
        "Save run report copy",
        "A run-specific copy of the run report is written into the client run folder.",
    ),
    StepDef(
        "save_projection",
        "projection_path",
        "Save projection copy",
        "A run-specific projection file is written when available.",
    ),
    StepDef(
        "comparison",
        "run_comparison(",
        "Compare against previous run",
        "Current run results are compared with the previous run.",
    ),
    StepDef(
        "health",
        "compute_health(",
        "Score run health",
        "A health score and risk flags are computed from run-to-run changes.",
    ),
    StepDef(
        "dashboard",
        "render_client_dashboard(",
        "Build client dashboard",
        "A static dashboard page is created for the run.",
    ),
    StepDef(
        "value_summary",
        "generate_value_summary(",
        "Create value summary",
        "A plain summary of impact and value is created.",
    ),
    StepDef(
        "delivery_bundle",
        "build_delivery_package(",
        "Create delivery package",
        "Delivery package metadata is assembled for all run outputs.",
    ),
    StepDef(
        "executive",
        "generate_executive_outputs(",
        "Create executive outputs",
        "Executive-ready files are created for stakeholder review.",
    ),
    StepDef(
        "trends",
        "generate_trend_outputs(",
        "Create trend outputs",
        "Trend and timeline files are created from run history.",
    ),
    StepDef(
        "operator",
        "generate_operator_outputs(",
        "Create operator action list",
        "Operator priorities and tasks are created.",
    ),
    StepDef(
        "sales",
        "generate_sales_outputs(",
        "Create sales outputs",
        "Sales-facing outputs are created from the run.",
    ),
]

REQUIRED_SECTIONS = [
    "Current Revision Status",
    "What Happens",
    "Your Responsibilities",
    "What Gets Created",
    "When You Make Changes",
    "Revision Map",
    "Business Flow",
]

PLAIN_LANGUAGE_STAGES: list[dict[str, str]] = [
    {
        "title": "1. Finding potential clients",
        "happening": "The system gathers possible companies from your saved sources and configured channels.",
        "result": "A candidate list of companies to consider.",
        "next": "Quickly remove obvious bad-fit companies before moving forward.",
    },
    {
        "title": "2. Understanding each company",
        "happening": "The system builds short context notes for each company so outreach is relevant.",
        "result": "A basic profile for each company.",
        "next": "Spot-check a few profiles to confirm they make business sense.",
    },
    {
        "title": "3. Selecting the best opportunities",
        "happening": "Weak-fit companies are filtered out so effort stays focused.",
        "result": "A shortlist of stronger opportunities.",
        "next": "Confirm this shortlist still matches your current offer.",
    },
    {
        "title": "4. Preparing personalized messages",
        "happening": "Messages are tailored so they sound relevant instead of generic.",
        "result": "Ready-to-send personalized messages.",
        "next": "Review one sample message before sending.",
    },
    {
        "title": "5. Sending the messages",
        "happening": "Messages are sent in a controlled pace instead of all at once.",
        "result": "Messages delivered to selected prospects.",
        "next": "Let the cycle run fully before judging performance.",
    },
    {
        "title": "6. Watching for replies",
        "happening": "The system tracks who replied and who did not.",
        "result": "A clear response picture for this cycle.",
        "next": "Focus follow-up on engaged prospects first.",
    },
    {
        "title": "7. Improving the next round",
        "happening": "Results from this cycle are used to improve the next one.",
        "result": "A better next cycle plan.",
        "next": "Change one thing at a time so improvements are measurable.",
    },
]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _file_hash(path: Path) -> str:
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    return ""


def _directory_hash(path: Path) -> str:
    if not path.exists():
        return ""
    hasher = hashlib.sha256()
    files = sorted(p for p in path.rglob("*") if p.is_file())
    for file_path in files:
        rel = file_path.relative_to(path).as_posix()
        hasher.update(rel.encode("utf-8"))
        hasher.update(_file_hash(file_path).encode("utf-8"))
    return hasher.hexdigest()


def _watch_fingerprints() -> dict[str, str]:
    out: dict[str, str] = {}
    for watch in WATCH_PATHS:
        key = watch.relative_to(REPO_ROOT).as_posix()
        if watch.is_file():
            out[key] = _file_hash(watch)
        elif watch.is_dir():
            out[key] = _directory_hash(watch)
        else:
            out[key] = ""
    return out


def _extract_entry_points_from_ast(path: Path) -> list[str]:
    source = _read_text(path)
    if not source:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    entry_points: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in {"main", "_bridge"}:
            entry_points.append(node.name)
    if 'if __name__ == "__main__"' in source:
        entry_points.append("__main__ guard")
    return sorted(set(entry_points))


def _extract_client_runtime_files() -> list[str]:
    if not CLIENT_RUNTIME_DIR.is_dir():
        return []
    files = sorted(
        p.relative_to(REPO_ROOT).as_posix()
        for p in CLIENT_RUNTIME_DIR.rglob("*.py")
        if p.is_file()
    )
    return files


def _detect_execution_steps(run_daily_source: str) -> list[StepDef]:
    steps = [step for step in STEP_DEFS if step.check_token in run_daily_source]
    return steps


def _collect_latest_populated_run() -> dict[str, Any]:
    clients_dir = REPO_ROOT / "clients"
    if not clients_dir.is_dir():
        return {}

    best: dict[str, Any] = {}
    for client_dir in sorted(p for p in clients_dir.iterdir() if p.is_dir()):
        runs_dir = client_dir / "runs"
        if not runs_dir.is_dir():
            continue
        for run_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
            run_report_path = run_dir / "run_report.json"
            if not run_report_path.is_file():
                continue
            payload: dict[str, Any] = {}
            try:
                payload = json.loads(run_report_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            timestamp = str(payload.get("timestamp_utc") or "")
            key = (timestamp, client_dir.name, run_dir.name)
            if not best or key > best["sort_key"]:
                best = {
                    "sort_key": key,
                    "client_id": client_dir.name,
                    "run_id": run_dir.name,
                    "run_dir": run_dir,
                    "run_report": payload,
                }
    return best


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _extract_numbers(run_report: dict[str, Any]) -> dict[str, float]:
    outbound = run_report.get("outbound") if isinstance(run_report, dict) else {}
    outbound = outbound if isinstance(outbound, dict) else {}
    telemetry = outbound.get("pipeline_telemetry")
    telemetry = telemetry if isinstance(telemetry, dict) else {}
    run_health = telemetry.get("run_health")
    run_health = run_health if isinstance(run_health, dict) else {}

    sent = int(run_health.get("sent") or 0)
    replies = int(run_health.get("replies") or 0)
    qualified = int(run_health.get("qualified") or 0)
    reply_rate = float(
        run_health.get("reply_rate_estimate") or run_health.get("reply_rate") or 0.0
    )
    if sent > 0 and reply_rate <= 0.0:
        reply_rate = replies / sent

    return {
        "sent": sent,
        "replies": replies,
        "qualified": qualified,
        "reply_rate": round(reply_rate, 4),
    }


def _artifact_rows(run_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    files = (
        sorted(p.name for p in run_dir.iterdir() if p.is_file())
        if run_dir.is_dir()
        else []
    )
    descriptor_map = {
        "run_report.json": {
            "name": "Campaign activity summary",
            "stage": "During and after run",
            "purpose": "Shows how many were contacted and key outcomes",
            "who": "You",
            "next": "Use this as your baseline before changing anything",
        },
        "comparison.json": {
            "name": "What changed since last cycle",
            "stage": "After run",
            "purpose": "Shows whether this cycle improved or declined",
            "who": "You",
            "next": "Decide if you keep current approach or revise one part",
        },
        "health.json": {
            "name": "Campaign health snapshot",
            "stage": "After run",
            "purpose": "Quick signal of how healthy this cycle is",
            "who": "You",
            "next": "Prioritize fixes if health is weak",
        },
        "value_summary.json": {
            "name": "Value summary",
            "stage": "After run",
            "purpose": "Explains results in plain language",
            "who": "You and client",
            "next": "Share this in your update message",
        },
        "operator_tasks.json": {
            "name": "Next actions list",
            "stage": "After run",
            "purpose": "Shows what to do next in priority order",
            "who": "You",
            "next": "Work top-down and close the highest-impact action first",
        },
        "dashboard.html": {
            "name": "Client-ready dashboard",
            "stage": "After run",
            "purpose": "A simple page to present campaign results",
            "who": "You and client",
            "next": "Use this in client check-ins",
        },
    }

    preferred = [
        "run_report.json",
        "comparison.json",
        "health.json",
        "value_summary.json",
        "operator_tasks.json",
        "dashboard.html",
    ]
    ordered_core = [name for name in preferred if name in files]
    other_files = [name for name in files if name not in preferred]

    for name in ordered_core:
        descriptor = descriptor_map.get(name, {})
        rows.append(
            {
                "name": str(descriptor.get("name") or "Campaign output"),
                "stage": str(descriptor.get("stage") or "After run"),
                "purpose": str(
                    descriptor.get("purpose") or "Result used in follow-up actions"
                ),
                "who": str(descriptor.get("who") or "You"),
                "next": str(descriptor.get("next") or "Review and act on this output"),
            }
        )

    if other_files:
        rows.append(
            {
                "name": f"{len(other_files)} additional support files",
                "stage": "After run",
                "purpose": "Background files kept by the system; you usually do not need to open them",
                "who": "You",
                "next": "No action needed unless troubleshooting",
            }
        )
    return rows


def _mermaid_block(content: str) -> str:
    return f"```mermaid\n{content}\n```\n"


def _build_what_happens(
    run_id: str,
    client_id: str,
    steps: list[StepDef],
    numbers: dict[str, float],
) -> str:
    mermaid_lines = [
        "flowchart LR",
        "  A[Find potential companies] --> B[Understand each company]",
        "  B --> C[Select best opportunities]",
        "  C --> D[Prepare messages]",
        "  D --> E[Send messages]",
        "  E --> F[Track responses]",
        "  F --> G[Improve next cycle]",
        "  G --> A",
    ]

    return "\n".join(
        [
            "# What Happens",
            "",
            "For Non-Technical Readers:",
            "- This is the plain-language real-life story of each cycle.",
            "- You are always choosing direction; the system handles repetition.",
            "- At the end of each cycle, you get clear next actions.",
            "",
            f"Current example: client {client_id}, run {run_id}.",
            (
                f"Last run snapshot: {int(numbers['sent'])} sent, {int(numbers['replies'])} replies, "
                f"{int(numbers['qualified'])} qualified, reply rate {numbers['reply_rate']:.4f}."
            ),
            (
                "System activity this cycle: "
                f"{len(steps)} internal background tasks completed to produce your outputs."
            ),
            "",
            _mermaid_block("\n".join(mermaid_lines)).rstrip(),
            "",
            "## Step-by-Step Story",
            "### 1. Finding potential clients",
            "The system gathers companies that may be a fit for your offer.",
            "Output: a list of possible companies to contact.",
            "",
            "### 2. Understanding each company",
            "The system builds short context so outreach can be relevant.",
            "Output: a simple profile for each company.",
            "",
            "### 3. Selecting the best opportunities",
            "Weak-fit companies are removed.",
            "Output: a shortlist of stronger opportunities.",
            "",
            "### 4. Preparing personalized messages",
            "Messages are adapted to each company's likely needs.",
            "Output: ready-to-send messages.",
            "",
            "### 5. Sending the messages",
            "Messages are sent gradually, not all at once.",
            "Output: delivered outreach.",
            "",
            "### 6. Watching for replies",
            "Responses are tracked clearly.",
            "Output: a response and engagement view.",
            "",
            "### 7. Improving the next round",
            "What worked is kept, what failed is revised.",
            "Output: improved next cycle.",
            "",
        ]
    )


def _build_your_responsibilities() -> str:
    return "\n".join(
        [
            "# Your Responsibilities",
            "",
            "For Non-Technical Readers:",
            "- You make business decisions.",
            "- The system handles repetitive execution work.",
            "- You decide what to keep and what to improve.",
            "",
            "## What Is Happening Right Now",
            "- A cycle is running or just finished",
            "- Results are available for review",
            "- A revision decision is due",
            "",
            "## What You Should Do",
            "- Confirm the target list still matches your offer",
            "- Approve or revise message wording",
            "- Review outcomes and pick one improvement",
            "",
            "## What The System Does For You",
            "- Organizes the cycle end-to-end",
            "- Produces clear summaries",
            "- Tracks changes between cycles",
            "",
        ]
    )


def _build_what_gets_created(rows: list[dict[str, str]]) -> str:
    header = "| What You Receive | When | Why It Matters | What To Do Next |\n|---|---|---|---|"
    table_rows = [
        f"| {row['name']} | {row['stage']} | {row['purpose']} | {row['next']} |"
        for row in rows
    ]

    mermaid = _mermaid_block(
        "\n".join(
            [
                "flowchart LR",
                "  A[Cycle starts] --> B[Campaign summary]",
                "  B --> C[What changed]",
                "  C --> D[Health snapshot]",
                "  D --> E[Value summary]",
                "  E --> F[Next actions]",
                "  F --> G[Client dashboard]",
            ]
        )
    ).rstrip()

    return "\n".join(
        [
            "# What Gets Created",
            "",
            "For Non-Technical Readers:",
            "- You get a small set of decision-ready outputs.",
            "- Each output answers a practical business question.",
            "- You can operate daily by using just these outputs.",
            "",
            header,
            *table_rows,
            "",
            mermaid,
            "",
        ]
    )


def _build_when_you_make_changes() -> str:
    return "\n".join(
        [
            "# When You Make Changes",
            "",
            "For Non-Technical Readers:",
            "- Make one change at a time.",
            "- Keep other choices locked so results stay comparable.",
            "",
            "## Change: Message wording",
            "- What updates: response quality view, cycle summary, client dashboard",
            "- Check first: message still matches your offer",
            "- What may change: reply pattern",
            "",
            "## Change: Target people",
            "- What updates: totals, cycle comparison, trends",
            "- Check first: target quality and size",
            "- What may change: baseline and fair comparison",
            "",
            "## Change: Send timing",
            "- What updates: response timing view and trends",
            "- Check first: keep timing stable for one full run",
            "- What may change: response timing and rates",
            "",
            "## Change: Success metric",
            "- What updates: how results are interpreted",
            "- Check first: keep one metric rule for the current cycle",
            "- What may change: score labels even if raw numbers are the same",
            "",
        ]
    )


def _build_revision_map(
    client_id: str,
    run_id: str,
    comparison: dict[str, Any],
    health: dict[str, Any],
) -> str:
    trend = str(comparison.get("trend") or "BASELINE")
    health_label = str(health.get("label") or "BASELINE")
    health_score = int(health.get("health_score") or 0)
    breakpoints = comparison.get("breakpoints")
    breakpoint_list = breakpoints if isinstance(breakpoints, list) else []

    mermaid = _mermaid_block(
        "\n".join(
            [
                "flowchart TD",
                "  A[Current cycle review] --> B{Revision choice}",
                "  B -->|Keep| C[Run one more cycle]\n",
                "  B -->|Revise message| D[Refresh outcomes and dashboard]",
                "  B -->|Revise targets| E[Refresh totals and trends]",
                "  B -->|Revise timing| F[Refresh timing outcomes and trends]",
                "  D --> G[New review point]",
                "  E --> G",
                "  F --> G",
            ]
        )
    ).rstrip()

    bp_text = ", ".join(str(x) for x in breakpoint_list) if breakpoint_list else "none"

    return "\n".join(
        [
            "# Revision Map",
            "",
            "For Non-Technical Readers:",
            "- This is where you see exactly where revision is happening.",
            "- The decision point is explicit, and each revision path shows what updates.",
            "",
            f"Current status: client {client_id}, run {run_id}.",
            f"Current trend: {trend}. Current health: {health_label} ({health_score}).",
            f"Current watch flags: {bp_text}.",
            "",
            "## Locked Right Now (keep stable for fair comparison)",
            "- Keep target people stable for one revision cycle",
            "- Keep send timing stable for one revision cycle",
            "",
            "## Open Right Now (safe to revise)",
            "- Message wording",
            "- Call-to-action phrasing",
            "",
            "## Revision Impact Timeline",
            "- Immediate: outcome view refreshes",
            "- Same cycle: summary and dashboard refresh",
            "- Next cycle: trend direction becomes clearer",
            "",
            mermaid,
            "",
        ]
    )


def _build_business_flow() -> str:
    mermaid = _mermaid_block(
        "\n".join(
            [
                "flowchart LR",
                "  A[Find potential companies] --> B[Understand each company]",
                "  B --> C[Select best opportunities]",
                "  C --> D[Prepare messages]",
                "  D --> E[Send messages]",
                "  E --> F[Track responses]",
                "  F --> G[Improve next cycle]",
                "  G --> A",
            ]
        )
    ).rstrip()

    return "\n".join(
        [
            "# Business Flow",
            "",
            "For Non-Technical Readers:",
            "- This is the full business cycle in plain language.",
            "- Every cycle ends with a clear decision for the next cycle.",
            "- Improvement is continuous, not one-time.",
            "",
            mermaid,
            "",
            "## Example Client Journey",
            "1. Day 1: Build and review opportunity shortlist.",
            "2. Day 2: Send personalized outreach.",
            "3. Day 3: Review responses and engagement.",
            "4. Day 4: Apply one improvement.",
            "5. Day 5: Run the next improved cycle.",
            "",
        ]
    )


def _build_control_center(
    *,
    entry_points: list[str],
    runtime_files: list[str],
    steps: list[StepDef],
    latest_run: dict[str, Any],
    comparison: dict[str, Any],
    health: dict[str, Any],
    rows: list[dict[str, str]],
    watch_fingerprints: dict[str, str],
) -> dict[str, Any]:
    run_report = latest_run.get("run_report") if isinstance(latest_run, dict) else {}
    run_report = run_report if isinstance(run_report, dict) else {}
    run_id = str(latest_run.get("run_id") or "none")
    client_id = str(latest_run.get("client_id") or "none")

    artifact_map = {
        row["name"]: {
            "stage": row["stage"],
            "purpose": row["purpose"],
        }
        for row in rows
    }

    execution_edges = []
    for idx in range(len(steps) - 1):
        execution_edges.append(
            {
                "from": steps[idx].title,
                "to": steps[idx + 1].title,
            }
        )

    return {
        "operator": "solo",
        "source": {
            "entry_points": entry_points,
            "root_run_script": RUN_DAILY_PATH.relative_to(REPO_ROOT).as_posix(),
            "watch_fingerprints": watch_fingerprints,
        },
        "system_status": {
            "client_id": client_id,
            "run_id": run_id,
            "run_timestamp_utc": run_report.get("timestamp_utc") or "",
            "trend": comparison.get("trend") or "BASELINE",
            "health_score": int(health.get("health_score") or 0),
            "health_label": health.get("label") or "BASELINE",
        },
        "files": {
            "docs": {
                "what_happens": "docs/solo-operator/what_happens.md",
                "your_responsibilities": "docs/solo-operator/your_responsibilities.md",
                "what_gets_created": "docs/solo-operator/what_gets_created.md",
                "when_you_make_changes": "docs/solo-operator/when_you_make_changes.md",
                "revision_map": "docs/solo-operator/revision_map.md",
                "business_flow": "docs/solo-operator/business_flow.md",
                "overview": "docs/solo-operator/overview.html",
            }
        },
        "execution_order": [step.title for step in steps],
        "modules": runtime_files,
        "artifacts": artifact_map,
        "execution_edges": execution_edges,
        "change_impact_rules": {
            "message_change": {
                "updates": [
                    "comparison.json",
                    "health.json",
                    "dashboard.html",
                    "value_summary.json",
                ],
                "risk": "can reduce fair comparison with previous message versions",
            },
            "target_change": {
                "updates": [
                    "run_report.json",
                    "comparison.json",
                    "trend_projection.json",
                ],
                "risk": "rate comparisons may no longer be apples-to-apples",
            },
            "timing_change": {
                "updates": ["run_report.json", "comparison.json", "trend_summary.json"],
                "risk": "timing shift can hide true message effect",
            },
        },
    }


def _overview_section(title: str, body_html: str) -> str:
    return f'<section class="card">' f"<h2>{title}</h2>" f"{body_html}" f"</section>"


def _build_overview_html(
    control_center: dict[str, Any], rows: list[dict[str, str]]
) -> str:
    status = control_center.get("system_status", {})
    status = status if isinstance(status, dict) else {}
    trend = str(status.get("trend") or "BASELINE")
    score = int(status.get("health_score") or 0)
    label = str(status.get("health_label") or "BASELINE")
    run_id = str(status.get("run_id") or "none")
    client_id = str(status.get("client_id") or "none")

    table_rows = "".join(
        "<tr>"
        f"<td>{row['name']}</td><td>{row['stage']}</td><td>{row['purpose']}</td><td>{row.get('next', '')}</td>"
        "</tr>"
        for row in rows
    )

    stage_cards = "".join(
        (
            '<article class="stage">'
            f"<h3>{stage['title']}</h3>"
            f"<p><strong>What is happening:</strong> {stage['happening']}</p>"
            f"<p><strong>What you get:</strong> {stage['result']}</p>"
            f"<p><strong>What to do next:</strong> {stage['next']}</p>"
            "</article>"
        )
        for stage in PLAIN_LANGUAGE_STAGES
    )

    stage_strip = "".join(
        (
            f'<div class="flow-step"><span class="step-num">{idx}</span>'
            f"<span>{stage['title'].split('. ', 1)[1]}</span></div>"
        )
        for idx, stage in enumerate(PLAIN_LANGUAGE_STAGES, start=1)
    )

    revision_diagram = """
flowchart TD
    A[Current cycle review] --> B{Revision choice}
  B -->|Keep| C[Run next cycle]
    B -->|Revise message| D[Refresh outcomes and dashboard]
    B -->|Revise targets| E[Refresh totals and trends]
    B -->|Revise timing| F[Refresh timing outcomes and trends]
""".strip()

    execution_diagram = """
flowchart LR
    A[Find potential companies] --> B[Understand each company]
    B --> C[Select best opportunities]
    C --> D[Prepare messages]
    D --> E[Send messages]
    E --> F[Track responses]
    F --> G[Improve next cycle]
    G --> A
""".strip()

    section_status = _overview_section(
        "Current Revision Status",
        (
            '<div class="status-grid">'
            f'<div class="status-pill"><span class="k">Client</span><span class="v">{client_id}</span></div>'
            f'<div class="status-pill"><span class="k">Run</span><span class="v">{run_id}</span></div>'
            f'<div class="status-pill"><span class="k">Trend</span><span class="v">{trend}</span></div>'
            f'<div class="status-pill"><span class="k">Health</span><span class="v">{label} ({score})</span></div>'
            "</div>"
            "<p><strong>What to focus on now:</strong> test message wording only, keep audience and timing fixed.</p>"
            "<p><strong>Decision today:</strong> choose one improvement for the next cycle.</p>"
        ),
    )

    section_what_system_does = _overview_section(
        "What the System Is Actually Doing",
        (
            "<h3>In simple real-world terms</h3>"
            "<p>This system is automatically handling your outreach process end-to-end:</p>"
            '<div class="system-actions">'
            '<div class="action-step">'
            "<strong>1. It collects company information</strong><br/>"
            "It looks for companies that match your ideal customer profile using publicly available sources.<br/>"
            '<em>Think: "building a list of potential customers for you"</em>'
            "</div>"
            '<div class="action-step">'
            "<strong>2. It gathers background details</strong><br/>"
            "For each company, it pulls what they do, who decides, and whether they're growing.<br/>"
            '<em>Think: "researching each company like a sales assistant would"</em>'
            "</div>"
            '<div class="action-step">'
            "<strong>3. It prepares outreach messages</strong><br/>"
            "It writes a short personalized message for each company based on its situation.<br/>"
            '<em>Think: "drafting a tailored email for every prospect"</em>'
            "</div>"
            '<div class="action-step">'
            "<strong>4. It sends the messages</strong><br/>"
            "It sends those messages out gradually to avoid looking like spam.<br/>"
            '<em>Think: "sending emails on your behalf in a controlled way"</em>'
            "</div>"
            '<div class="action-step">'
            "<strong>5. It watches reactions</strong><br/>"
            "It tracks who opened the message, who replied, and who ignored it.<br/>"
            '<em>Think: "monitoring responses like an inbox assistant"</em>'
            "</div>"
            '<div class="action-step">'
            "<strong>6. It improves future results</strong><br/>"
            "It uses results from previous runs to improve wording, targeting, and response rates.<br/>"
            '<em>Think: "learning what works and adjusting automatically"</em>'
            "</div>"
            "</div>"
        ),
    )

    section_what_happens = _overview_section(
        "What Happens",
        (
            "<p>Plain-language cycle story: find, understand, select, message, send, track, improve.</p>"
            f'<div class="flow-strip">{stage_strip}</div>'
            f'<div class="mermaid diagram">{execution_diagram}</div>'
            f'<div class="stages">{stage_cards}</div>'
        ),
    )

    section_roles = _overview_section(
        "Your Responsibilities",
        (
            "<ul>"
            "<li>You choose audience, message, and timing.</li>"
            "<li>You review what happened this cycle.</li>"
            "<li>You choose one next action.</li>"
            "<li>The system handles repetitive execution work for you.</li>"
            "</ul>"
        ),
    )

    section_outputs = _overview_section(
        "What Gets Created",
        (
            "<p>Only decision-ready outputs are shown here.</p>"
            "<table><thead><tr><th>What you receive</th><th>When</th><th>Why it matters</th><th>What to do next</th></tr></thead>"
            f"<tbody>{table_rows}</tbody></table>"
        ),
    )

    section_changes = _overview_section(
        "When You Make Changes",
        (
            "<ul>"
            "<li>Message change: updates outcomes and client-facing summary.</li>"
            "<li>Audience change: updates totals and trend direction.</li>"
            "<li>Timing change: updates response timing patterns.</li>"
            "<li>Best practice: change one thing at a time.</li>"
            "</ul>"
        ),
    )

    section_revision = _overview_section(
        "Revision Map",
        (
            "<p>This shows exactly where revision decisions happen and what each decision affects.</p>"
            f'<div class="mermaid diagram">{revision_diagram}</div>'
        ),
    )

    section_business = _overview_section(
        "Business Flow",
        (
            "<ol>"
            "<li>Find and shortlist the right companies.</li>"
            "<li>Send personalized messages.</li>"
            "<li>Track replies and engagement.</li>"
            "<li>Apply one improvement and repeat.</li>"
            "</ol>"
        ),
    )

    sections = (
        section_status
        + section_what_system_does
        + section_what_happens
        + section_roles
        + section_outputs
        + section_changes
        + section_revision
        + section_business
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Non-Technical Operator Dashboard</title>
  <style>
    :root {{
            --bg: #f8fbff;
      --card: #ffffff;
            --text: #13253a;
            --muted: #3f5672;
            --line: #d6e2f1;
            --accent: #0b7285;
    }}
    body {{
      margin: 0;
            background: linear-gradient(180deg, #edf4ff 0%, var(--bg) 52%, #f3fff8 100%);
      color: var(--text);
      font-family: "Segoe UI", "Trebuchet MS", sans-serif;
    }}
    .wrap {{
            max-width: 900px;
      margin: 0 auto;
      padding: 24px;
    }}
    h1 {{ margin: 0 0 6px; }}
        .sub {{ color: var(--muted); margin: 0 0 20px; font-size: 1rem; }}
    .grid {{
      display: grid;
            grid-template-columns: 1fr;
      gap: 14px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
      box-shadow: 0 6px 20px rgba(13, 23, 37, 0.04);
    }}
    .card h2 {{ margin-top: 0; font-size: 1.1rem; }}
    p, li {{ line-height: 1.45; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.92rem; }}
    th, td {{ border: 1px solid var(--line); padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f0f7ff; }}
        .diagram {{
      margin: 0;
      border: 1px dashed var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fbfdff;
      color: #254056;
    }}
        .system-actions {{ margin-top: 10px; }}
    .action-step {{ margin: 8px 0; padding: 8px 10px; background: #fcfeff; border-left: 3px solid #0b7285; font-size: 0.92rem; line-height: 1.5; }}
    .action-step strong {{ display: block; margin-bottom: 3px; }}
    .action-step em {{ color: var(--muted); font-style: italic; display: block; margin-top: 4px; font-size: 0.88rem; }}
    .status-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 8px; margin-bottom: 10px; }}
        .status-pill {{ border: 1px solid var(--line); border-radius: 10px; padding: 8px; background: #fafdff; }}
        .status-pill .k {{ display: block; font-size: 0.78rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; }}
        .status-pill .v {{ display: block; font-weight: 600; margin-top: 2px; }}
        .flow-strip {{ display: grid; gap: 8px; margin: 10px 0 12px; }}
        .flow-step {{ border: 1px solid var(--line); border-radius: 999px; padding: 8px 12px; background: #f9fcff; display: flex; align-items: center; gap: 8px; font-size: 0.94rem; }}
        .step-num {{ width: 22px; height: 22px; border-radius: 50%; background: #0b7285; color: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 0.8rem; font-weight: 700; }}
        .stages {{ margin-top: 12px; display: grid; gap: 10px; }}
        .stage {{ border: 1px solid var(--line); border-radius: 10px; padding: 10px; background: #fcfeff; }}
        .stage h3 {{ margin: 0 0 8px; font-size: 1rem; }}
        .stage p {{ margin: 6px 0; }}
        .foot {{ margin-top: 16px; color: var(--muted); font-size: 0.9rem; }}
  </style>
</head>
<body>
  <div class="wrap">
        <h1>Non-Technical Operator Dashboard</h1>
        <p class="sub">This system finds companies, sends personalized messages on your behalf, tracks responses, and improves results automatically over time.</p>
    <div class="grid">{sections}</div>
        <p class="foot">This page is auto-updated from your latest run.</p>
  </div>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
    <script>
        if (window.mermaid) {{
            window.mermaid.initialize({{ startOnLoad: true, theme: "neutral", securityLevel: "loose" }});
        }}
    </script>
</body>
</html>
"""
    return html


def _validate_outputs() -> list[str]:
    errors: list[str] = []
    required = [
        DOCS_DIR / "what_happens.md",
        DOCS_DIR / "your_responsibilities.md",
        DOCS_DIR / "what_gets_created.md",
        DOCS_DIR / "when_you_make_changes.md",
        DOCS_DIR / "revision_map.md",
        DOCS_DIR / "business_flow.md",
        DOCS_DIR / "control_center.json",
        DOCS_DIR / "overview.html",
    ]
    for path in required:
        if not path.is_file():
            errors.append(f"missing file: {path.relative_to(REPO_ROOT).as_posix()}")

    overview = _read_text(DOCS_DIR / "overview.html")
    for section in REQUIRED_SECTIONS:
        if section not in overview:
            errors.append(f"overview missing section: {section}")

    return errors


def generate() -> int:
    run_daily_source = _read_text(RUN_DAILY_PATH)
    steps = _detect_execution_steps(run_daily_source)
    entry_points = _extract_entry_points_from_ast(RUN_DAILY_PATH)
    runtime_files = _extract_client_runtime_files()
    latest_run = _collect_latest_populated_run()

    run_report = latest_run.get("run_report") if isinstance(latest_run, dict) else {}
    run_report = run_report if isinstance(run_report, dict) else {}
    run_dir = latest_run.get("run_dir") if isinstance(latest_run, dict) else None
    run_dir = run_dir if isinstance(run_dir, Path) else Path()
    client_id = str(latest_run.get("client_id") or "none")
    run_id = str(latest_run.get("run_id") or "none")

    comparison = _load_json_if_exists(run_dir / "comparison.json") if run_dir else {}
    health = _load_json_if_exists(run_dir / "health.json") if run_dir else {}

    numbers = _extract_numbers(run_report)
    rows = _artifact_rows(run_dir)
    watch_fingerprints = _watch_fingerprints()

    what_happens = _build_what_happens(run_id, client_id, steps, numbers)
    responsibilities = _build_your_responsibilities()
    what_gets_created = _build_what_gets_created(rows)
    when_you_make_changes = _build_when_you_make_changes()
    revision_map = _build_revision_map(client_id, run_id, comparison, health)
    business_flow = _build_business_flow()

    control_center = _build_control_center(
        entry_points=entry_points,
        runtime_files=runtime_files,
        steps=steps,
        latest_run=latest_run,
        comparison=comparison,
        health=health,
        rows=rows,
        watch_fingerprints=watch_fingerprints,
    )
    overview = _build_overview_html(control_center, rows)

    _write_text(DOCS_DIR / "what_happens.md", what_happens)
    _write_text(DOCS_DIR / "your_responsibilities.md", responsibilities)
    _write_text(DOCS_DIR / "what_gets_created.md", what_gets_created)
    _write_text(DOCS_DIR / "when_you_make_changes.md", when_you_make_changes)
    _write_text(DOCS_DIR / "revision_map.md", revision_map)
    _write_text(DOCS_DIR / "business_flow.md", business_flow)
    _write_text(
        DOCS_DIR / "control_center.json",
        json.dumps(control_center, indent=2, sort_keys=True),
    )
    _write_text(DOCS_DIR / "overview.html", overview)

    errors = _validate_outputs()
    if errors:
        for err in errors:
            print(f"[error] {err}")
        return 1

    print("[ok] solo operator docs regenerated")
    print(
        f"[ok] main view: {(DOCS_DIR / 'overview.html').relative_to(REPO_ROOT).as_posix()}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate solo-operator architecture docs"
    )
    parser.add_argument("--check", action="store_true", help="Only validate outputs")
    args = parser.parse_args()

    if args.check:
        errs = _validate_outputs()
        if errs:
            for err in errs:
                print(f"[error] {err}")
            return 1
        print("[ok] solo-operator docs validation passed")
        return 0

    return generate()


if __name__ == "__main__":
    raise SystemExit(main())
