from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from hfss_agent_mcp.core.service import HfssService


def register(mcp: FastMCP, service: HfssService) -> None:
    @mcp.tool(description="Create an HFSS setup and linear frequency sweep.")
    def create_simulation_setup(
        setup_name: str,
        frequency_ghz: float,
        sweep_name: str = "Sweep1",
        sweep_start_ghz: float = 1.0,
        sweep_stop_ghz: float = 3.0,
        sweep_points: int = 201,
    ) -> dict:
        return service.create_simulation_setup(
            setup_name=setup_name,
            frequency_ghz=frequency_ghz,
            sweep_name=sweep_name,
            sweep_start_ghz=sweep_start_ghz,
            sweep_stop_ghz=sweep_stop_ghz,
            sweep_points=sweep_points,
        )

    @mcp.tool(description="Validate the active HFSS design before solve.")
    def validate_design() -> dict:
        return service.validate_design()

    @mcp.tool(description="Run simulation for an existing HFSS setup.")
    def run_simulation(setup_name: str) -> dict:
        return service.run_simulation(setup_name=setup_name)
