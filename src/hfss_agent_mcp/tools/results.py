from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from hfss_agent_mcp.core.service import HfssService


def register(mcp: FastMCP, service: HfssService) -> None:
    @mcp.tool(description="Read S-parameter summary data from the selected setup and sweep.")
    def get_s_parameters(
        setup_name: str,
        sweep_name: str | None = None,
        expression: str = "dB(S(1,1))",
    ) -> dict:
        return service.get_s_parameters(
            setup_name=setup_name,
            sweep_name=sweep_name,
            expression=expression,
        )

    @mcp.tool(description="Export Touchstone data into the configured server output directory.")
    def export_touchstone(relative_path: str = "touchstone/result.s1p") -> dict:
        return service.export_touchstone(relative_path=relative_path)
