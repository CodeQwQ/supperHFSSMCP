from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from hfss_agent_mcp.core.service import HfssService


def register(mcp: FastMCP, service: HfssService) -> None:
    @mcp.tool(description="Check whether the MCP server and selected HFSS backend are reachable.")
    def health_check() -> dict:
        return service.health_check()

    @mcp.tool(
        description=(
            "Inspect the server runtime environment, including Python, MCP packages, "
            "PyAEDT availability, AEDT executable detection, transport and output directory."
        )
    )
    def env_check() -> dict:
        return service.env_check()

    @mcp.tool(
        description=(
            "Connect to an AEDT/HFSS session. Use machine and port for a remote "
            "gRPC AEDT service, or project_path/design_name for a local workflow."
        )
    )
    def connect_hfss(
        desktop_version: str | None = None,
        project_path: str | None = None,
        design_name: str | None = None,
        solution_type: str = "DrivenModal",
        non_graphical: bool = True,
        new_desktop: bool = False,
        machine: str | None = None,
        port: int | None = None,
    ) -> dict:
        return service.connect_hfss(
            desktop_version=desktop_version,
            project_path=project_path,
            design_name=design_name,
            solution_type=solution_type,
            non_graphical=non_graphical,
            new_desktop=new_desktop,
            machine=machine,
            port=port,
        )
