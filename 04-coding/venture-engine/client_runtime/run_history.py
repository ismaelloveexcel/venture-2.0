"""Run history helpers for client run directories."""

from __future__ import annotations

from pathlib import Path


def get_previous_run(
    client_id: str,
    current_run_id: str,
    *,
    repo_root: Path,
) -> Path | None:
    """
    Return previous run directory for client, excluding current run id.

    Logic:
    - list clients/{client_id}/runs/ folders
    - sort by modified time descending
    - return first run != current_run_id
    - if none -> None
    """
    runs_dir = repo_root / "clients" / client_id / "runs"
    if not runs_dir.is_dir():
        return None

    run_dirs = sorted(
        [p for p in runs_dir.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for run_dir in run_dirs:
        if run_dir.name != current_run_id:
            return run_dir
    return None
