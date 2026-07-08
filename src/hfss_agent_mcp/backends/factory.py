from __future__ import annotations

from hfss_agent_mcp.backends.base import HfssBackend
from hfss_agent_mcp.backends.mock import MockHfssBackend
from hfss_agent_mcp.backends.pyaedt import PyAedtBackend
from hfss_agent_mcp.core.errors import ConfigurationError


def create_backend(name: str) -> HfssBackend:
    normalized = name.strip().lower()
    if normalized == "mock":
        return MockHfssBackend()
    if normalized == "pyaedt":
        return PyAedtBackend()
    raise ConfigurationError(f"Unsupported HFSS backend: {name!r}")
