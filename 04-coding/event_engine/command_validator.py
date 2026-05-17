"""
command_validator.py -- Stateless command validator (INV-4).

Rules (runtime_contract.md section 7 INV-4):
- CommandValidator is stateless -- no instance state
- No execution logic -- validation and pure lookup only
"""

from __future__ import annotations

VALID_COMMANDS: frozenset[str] = frozenset(
    {"start", "pause", "resume", "approve", "reject"}
)

COMMAND_TRANSITIONS: dict[str, str] = {
    "start": "running",
    "pause": "paused",
    "resume": "running",
    "approve": "running",
    "reject": "failed",
}


class InvalidCommandError(Exception):
    """Raised when an unrecognised command is submitted."""


class CommandValidator:
    """Stateless command validator. No instance state. No execution logic (INV-4)."""

    def validate(self, command: str) -> str:
        """Validate a command string. Returns command if valid, raises InvalidCommandError otherwise."""
        if command not in VALID_COMMANDS:
            raise InvalidCommandError(
                f"Unknown command {command!r}. Valid: {sorted(VALID_COMMANDS)}"
            )
        return command

    def target_state(self, command: str) -> str:
        """Return the target session state for a command. Raises InvalidCommandError if invalid."""
        self.validate(command)
        return COMMAND_TRANSITIONS[command]
