from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from hfss_agent_mcp.core.service import HfssService


def register(mcp: FastMCP, service: HfssService) -> None:
    @mcp.tool(
        description=(
            "List only the server-registered HFSS automation scripts. "
            "The agent cannot provide an arbitrary script path or executable code."
        )
    )
    def list_automation_scripts() -> dict:
        return service.list_automation_scripts()

    @mcp.tool(
        description=(
            "Run one registered HFSS automation script through the native AEDT CLI, "
            "the PyAEDT CLI, or an attached AEDT COM session. Use operation=batch_solve "
            "only with a managed .aedt project path. Arbitrary code is not accepted."
        )
    )
    def run_automation_script(
        script_id: str,
        runner: str = "pyaedt",
        operation: str = "script",
        port: int | None = None,
        project_path: str | None = None,
        relative_output: str | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> dict:
        return service.run_automation_script(
            script_id=script_id,
            runner=runner,
            operation=operation,
            port=port,
            project_path=project_path,
            relative_output=relative_output,
            arguments=arguments,
        )
