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

    @mcp.tool(description="Analyze S-parameter resonance, bandwidth, VSWR, and target-frequency compliance.")
    def analyze_s_parameters(
        setup_name: str,
        sweep_name: str | None = None,
        expression: str = "dB(S(1,1))",
        target_frequency_ghz: float | None = None,
        threshold_db: float = -10.0,
    ) -> dict:
        return service.analyze_s_parameters(
            setup_name=setup_name,
            sweep_name=sweep_name,
            expression=expression,
            target_frequency_ghz=target_frequency_ghz,
            threshold_db=threshold_db,
        )

    @mcp.tool(description="Analyze complex input impedance samples returned by an HFSS setup.")
    def analyze_input_impedance(
        setup_name: str,
        sweep_name: str | None = None,
        expression: str = "Z(1,1)",
        target_frequency_ghz: float | None = None,
    ) -> dict:
        return service.analyze_input_impedance(
            setup_name=setup_name,
            sweep_name=sweep_name,
            expression=expression,
            target_frequency_ghz=target_frequency_ghz,
        )

    @mcp.tool(description="Export retrieved S-parameter samples and analysis into JSON or CSV.")
    def export_result_report(
        setup_name: str,
        relative_path: str = "results/report.json",
        sweep_name: str | None = None,
        expression: str = "dB(S(1,1))",
        target_frequency_ghz: float | None = None,
        threshold_db: float = -10.0,
    ) -> dict:
        return service.export_result_report(
            setup_name=setup_name,
            relative_path=relative_path,
            sweep_name=sweep_name,
            expression=expression,
            target_frequency_ghz=target_frequency_ghz,
            threshold_db=threshold_db,
        )
