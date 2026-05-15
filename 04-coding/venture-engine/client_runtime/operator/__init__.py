"""Operator workflow automation layer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from client_runtime.file_io import atomic_write_json

from .action_queue import build_action_queue
from .operator_tasks import generate_operator_tasks
from .workflow_state import build_workflow_state


def generate_operator_outputs(
    *,
    run_dir: Path,
    executive_outputs: dict[str, Any],
    trend_outputs: dict[str, Any],
    health: dict[str, Any],
    value_summary: dict[str, Any],
) -> dict[str, Any]:
    tasks = generate_operator_tasks(
        executive_summary=executive_outputs.get("executive_summary") or {},
        trend_outputs=trend_outputs,
        health=health,
        value_summary=value_summary,
    )
    queue = build_action_queue(tasks)
    workflow_state = build_workflow_state(queue)
    priority_actions = {
        "actions": tasks[:3],
        "top_action": queue.get("next_action", "None"),
        "priority": queue.get("highest_priority", "LOW"),
    }
    operator_tasks = {
        "tasks": tasks,
        "top_action": queue.get("next_action", "None"),
    }

    queue_path = run_dir / "operator_queue.json"
    tasks_path = run_dir / "operator_tasks.json"
    priority_path = run_dir / "priority_actions.json"
    workflow_path = run_dir / "workflow_state.json"

    atomic_write_json(queue_path, queue)
    atomic_write_json(tasks_path, operator_tasks)
    atomic_write_json(priority_path, priority_actions)
    atomic_write_json(workflow_path, workflow_state)

    return {
        "operator_queue": queue,
        "operator_tasks": operator_tasks,
        "priority_actions": priority_actions,
        "workflow_state": workflow_state,
        "paths": {
            "operator_queue": str(queue_path),
            "operator_tasks": str(tasks_path),
            "priority_actions": str(priority_path),
            "workflow_state": str(workflow_path),
        },
    }
