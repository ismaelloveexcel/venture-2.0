"""Deterministic operator queue assembly."""

from __future__ import annotations

from typing import Any


def build_action_queue(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    queue = [
        {
            "action": str(task.get("action") or ""),
            "priority": str(task.get("priority") or "LOW"),
            "reason": str(task.get("reason") or ""),
            "score": int(task.get("score") or 0),
        }
        for task in tasks
    ]
    return {
        "queue": queue,
        "queue_size": len(queue),
        "highest_priority": queue[0]["priority"] if queue else "LOW",
        "next_action": queue[0]["action"] if queue else "None",
    }
