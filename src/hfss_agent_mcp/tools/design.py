from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from hfss_agent_mcp.core.service import HfssService


def register(mcp: FastMCP, service: HfssService) -> None:
    @mcp.tool(description="Read the current HFSS project, design, object and setup state.")
    def get_project_info() -> dict:
        return service.get_project_info()

    @mcp.tool(description="Create a new HFSS project inside the managed server project workspace.")
    def create_project(
        project_name: str,
        relative_path: str | None = None,
    ) -> dict:
        return service.create_project(
            project_name=project_name,
            relative_path=relative_path,
        )

    @mcp.tool(description="Open an HFSS project from the managed server project workspace.")
    def open_project(relative_path: str) -> dict:
        return service.open_project(relative_path=relative_path)

    @mcp.tool(description="Save the active HFSS project, optionally to a managed relative path.")
    def save_project(relative_path: str | None = None) -> dict:
        return service.save_project(relative_path=relative_path)

    @mcp.tool(description="Close the active HFSS project while keeping the MCP session available.")
    def close_project(save: bool = False) -> dict:
        return service.close_project(save=save)

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

    @mcp.tool(description="Switch the active HFSS design inside the current project.")
    def set_active_design(design_name: str) -> dict:
        return service.set_active_design(design_name=design_name)

    @mcp.tool(description="Read object, setup and solution summary for an HFSS design.")
    def get_design_summary(design_name: str | None = None) -> dict:
        return service.get_design_summary(design_name=design_name)
