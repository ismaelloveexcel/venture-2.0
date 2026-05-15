"""
Client runtime layer — thin boundary abstraction.

Responsibilities:
- config_loader: Load and validate client config JSON
- client_router: Route execution to client-scoped directories
- dashboard_renderer: Render static HTML reports

Does NOT contain business logic, pipeline awareness, or orchestration.
"""

from .config_loader import ClientConfig, load_client_config, validate_client_config
from .client_router import ClientRouter, get_client_router
from .run_history import get_previous_run

__all__ = [
    "ClientConfig",
    "load_client_config",
    "validate_client_config",
    "ClientRouter",
    "get_client_router",
    "get_previous_run",
]
