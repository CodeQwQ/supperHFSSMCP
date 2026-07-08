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
        sweep_type: str = "LinearCount",
        max_delta_s: float = 0.02,
        max_passes: int = 10,
        min_passes: int = 1,
    ) -> dict:
        return service.create_simulation_setup(
            setup_name=setup_name,
            frequency_ghz=frequency_ghz,
            sweep_name=sweep_name,
            sweep_start_ghz=sweep_start_ghz,
            sweep_stop_ghz=sweep_stop_ghz,
            sweep_points=sweep_points,
            sweep_type=sweep_type,
            max_delta_s=max_delta_s,
            max_passes=max_passes,
            min_passes=min_passes,
        )

    @mcp.tool(description="Create or replace a frequency sweep for an existing HFSS setup.")
    def create_frequency_sweep(
        setup_name: str,
        sweep_name: str,
        sweep_start_ghz: float,
        sweep_stop_ghz: float,
        sweep_points: int,
        sweep_type: str = "LinearCount",
    ) -> dict:
        return service.create_frequency_sweep(
            setup_name=setup_name,
            sweep_name=sweep_name,
            sweep_start_ghz=sweep_start_ghz,
            sweep_stop_ghz=sweep_stop_ghz,
            sweep_points=sweep_points,
            sweep_type=sweep_type,
        )

    @mcp.tool(description="Validate the active HFSS design before solve.")
    def validate_design() -> dict:
        return service.validate_design()

    @mcp.tool(description="Run simulation for an existing HFSS setup and track it as a job.")
    def run_simulation(setup_name: str, wait_for_completion: bool = True) -> dict:
        return service.run_simulation(
            setup_name=setup_name,
            wait_for_completion=wait_for_completion,
        )

    @mcp.tool(description="Read the status of a tracked simulation job.")
    def get_simulation_job(job_id: str) -> dict:
        return service.get_simulation_job(job_id=job_id)
