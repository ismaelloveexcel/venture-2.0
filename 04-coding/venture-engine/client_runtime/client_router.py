"""
Client router — filesystem isolation and path resolution only.

NO business logic. NO execution logic.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional


class ClientRouter:
    """Route client_id and run_id to isolated directories."""

    def __init__(self, repo_root: str | Path):
        """Initialize router with repo root."""
        self.repo_root = Path(repo_root)
        self.clients_dir = self.repo_root / "clients"

    def get_client_base_path(self, client_id: str) -> Path:
        """Get base directory for client: clients/{client_id}/"""
        return self.clients_dir / client_id

    def get_client_config_path(self, client_id: str) -> Path:
        """Get config.json path for client."""
        return self.get_client_base_path(client_id) / "config.json"

    def get_client_runs_dir(self, client_id: str) -> Path:
        """Get runs directory for client: clients/{client_id}/runs/"""
        return self.get_client_base_path(client_id) / "runs"

    def get_run_output_dir(self, client_id: str, run_id: str) -> Path:
        """Get output directory for a specific run: clients/{client_id}/runs/{run_id}/"""
        return self.get_client_runs_dir(client_id) / run_id

    def ensure_client_structure(self, client_id: str) -> None:
        """Create client directory structure if it doesn't exist."""
        self.get_client_base_path(client_id).mkdir(parents=True, exist_ok=True)
        self.get_client_runs_dir(client_id).mkdir(parents=True, exist_ok=True)

    def ensure_run_directory(self, client_id: str, run_id: str) -> None:
        """Create run-specific directory."""
        self.get_run_output_dir(client_id, run_id).mkdir(parents=True, exist_ok=True)

    def get_latest_run_dir(self, client_id: str) -> Optional[Path]:
        """Get the most recently created run directory, or None."""
        runs_dir = self.get_client_runs_dir(client_id)
        if not runs_dir.is_dir():
            return None

        run_dirs = sorted(
            [d for d in runs_dir.iterdir() if d.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return run_dirs[0] if run_dirs else None

    def get_run_report_path(self, client_id: str, run_id: str) -> Path:
        """Get run_report.json path for a run."""
        return self.get_run_output_dir(client_id, run_id) / "run_report.json"

    def get_dashboard_path(self, client_id: str, run_id: str) -> Path:
        """Get dashboard HTML path for a run."""
        return self.get_run_output_dir(client_id, run_id) / "dashboard.html"

    def get_projection_path(self, client_id: str, run_id: str) -> Path:
        """Get projection.json path for a run."""
        return self.get_run_output_dir(client_id, run_id) / "projection.json"

    def get_comparison_path(self, client_id: str, run_id: str) -> Path:
        """Get comparison.json path for a run."""
        return self.get_run_output_dir(client_id, run_id) / "comparison.json"

    def get_health_path(self, client_id: str, run_id: str) -> Path:
        """Get health.json path for a run."""
        return self.get_run_output_dir(client_id, run_id) / "health.json"

    def list_client_runs(self, client_id: str) -> list[str]:
        """List all run_ids for a client (sorted by modification time, newest first)."""
        runs_dir = self.get_client_runs_dir(client_id)
        if not runs_dir.is_dir():
            return []

        run_dirs = sorted(
            [d.name for d in runs_dir.iterdir() if d.is_dir()],
            key=lambda name: (runs_dir / name).stat().st_mtime,
            reverse=True,
        )
        return run_dirs


def get_client_router(repo_root: str | Path) -> ClientRouter:
    """Factory function to get a client router instance."""
    return ClientRouter(repo_root)
