from __future__ import annotations

from collections.abc import Iterable

from mcp.server.fastmcp import FastMCP

from hfss_agent_mcp.core.service import HfssService
from hfss_agent_mcp.tools import antenna, design, results, session, simulation

TOOL_GROUPS = {
    "session": session.register,
    "design": design.register,
    "antenna": antenna.register,
    "simulation": simulation.register,
    "results": results.register,
}


def register_all_tools(
    mcp: FastMCP,
    service: HfssService,
    groups: Iterable[str] | None = None,
) -> None:
    selected_groups = list(groups or TOOL_GROUPS)
    for group in selected_groups:
        TOOL_GROUPS[group](mcp, service)
