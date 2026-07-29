from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from antenna_design_intelligence_mcp.service import IntelligenceService
from antenna_design_intelligence_mcp.tools.extraction import register


def register_all_tools(mcp: FastMCP, service: IntelligenceService) -> None:
    register(mcp, service)
