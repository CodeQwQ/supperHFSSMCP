from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from hfss_agent_mcp.core.service import HfssService


def register(mcp: FastMCP, service: HfssService) -> None:
    @mcp.tool(description="Read the current HFSS project, design, object and setup state.")
    def get_project_info() -> dict:
        return service.get_project_info()

    @mcp.tool(description="Create or switch to an HFSS design inside the active AEDT project.")
    def create_hfss_design(
        design_name: str,
        project_name: str | None = None,
        solution_type: str = "DrivenModal",
    ) -> dict:
        return service.create_hfss_design(
            project_name=project_name,
            design_name=design_name,
            solution_type=solution_type,
        )
