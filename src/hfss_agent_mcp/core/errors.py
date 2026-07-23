from __future__ import annotations


from __future__ import annotations

from typing import Any


class HfssAgentError(Exception):
    """Base error for controlled HFSS agent failures."""

    def __init__(self, message: str = "", *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class BackendUnavailableError(HfssAgentError):
    """Raised when the selected backend cannot execute an operation."""


class BackendStateError(HfssAgentError):
    """Raised when a backend is available but not in the required state."""


class ConfigurationError(HfssAgentError):
    """Raised when server configuration is invalid."""


class InputValidationError(HfssAgentError):
    """Raised when tool input violates project constraints."""


class SessionError(HfssAgentError):
    """Raised when session lifecycle operations cannot be completed."""


class JobError(HfssAgentError):
    """Raised when simulation job operations cannot be completed."""
