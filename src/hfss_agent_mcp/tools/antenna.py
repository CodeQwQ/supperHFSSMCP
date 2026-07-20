from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from hfss_agent_mcp.core.service import HfssService


def register(mcp: FastMCP, service: HfssService) -> None:
    @mcp.tool(
        description=(
            "Create a rectangular microstrip patch antenna workflow object. "
            "The backend creates substrate, ground, patch, feed and airbox objects, "
            "or returns the equivalent planned geometry in mock mode."
        )
    )
    def create_patch_antenna(
        name: str,
        frequency_ghz: float,
        substrate_material: str = "FR4_epoxy",
        conductor_material: str = "copper",
        substrate_height_mm: float = 1.6,
        patch_length_mm: float | None = None,
        patch_width_mm: float | None = None,
        ground_length_mm: float | None = None,
        ground_width_mm: float | None = None,
        feed_offset_mm: float = 0.0,
        feed_width_mm: float = 3.0,
        airbox_margin_mm: float | None = None,
        port_type: str = "lumped",
    ) -> dict:
        return service.create_patch_antenna(
            name=name,
            frequency_ghz=frequency_ghz,
            substrate_material=substrate_material,
            conductor_material=conductor_material,
            substrate_height_mm=substrate_height_mm,
            patch_length_mm=patch_length_mm,
            patch_width_mm=patch_width_mm,
            ground_length_mm=ground_length_mm,
            ground_width_mm=ground_width_mm,
            feed_offset_mm=feed_offset_mm,
            feed_width_mm=feed_width_mm,
            airbox_margin_mm=airbox_margin_mm,
            port_type=port_type,
        )

    @mcp.tool(
        description=(
            "Create a planar center-fed dipole antenna workflow object with two arms, "
            "a lumped port, and a radiation airbox."
        )
    )
    def create_dipole_antenna(
        name: str,
        frequency_ghz: float,
        conductor_material: str = "copper",
        arm_length_mm: float | None = None,
        arm_width_mm: float = 2.0,
        arm_thickness_mm: float = 0.035,
        gap_mm: float = 1.0,
        airbox_margin_mm: float | None = None,
        port_type: str = "lumped",
    ) -> dict:
        return service.create_dipole_antenna(
            name=name,
            frequency_ghz=frequency_ghz,
            conductor_material=conductor_material,
            arm_length_mm=arm_length_mm,
            arm_width_mm=arm_width_mm,
            arm_thickness_mm=arm_thickness_mm,
            gap_mm=gap_mm,
            airbox_margin_mm=airbox_margin_mm,
            port_type=port_type,
        )

    @mcp.tool(
        description=(
            "Run a bounded design-variable optimization. Each candidate is applied to "
            "HFSS, solved, and scored from returned S-parameter data."
        )
    )
    def optimize_design_variable(
        variable_name: str,
        candidate_values: list[str],
        setup_name: str,
        target_frequency_ghz: float,
        sweep_name: str | None = None,
        expression: str = "dB(S(1,1))",
        threshold_db: float = -10.0,
        max_evaluations: int | None = None,
    ) -> dict:
        return service.optimize_design_variable(
            variable_name=variable_name,
            candidate_values=candidate_values,
            setup_name=setup_name,
            target_frequency_ghz=target_frequency_ghz,
            sweep_name=sweep_name,
            expression=expression,
            threshold_db=threshold_db,
            max_evaluations=max_evaluations,
        )

    @mcp.tool(
        description=(
            "Set one explicit HFSS design variable to a controlled value before a "
            "simulation or optimization run."
        )
    )
    def set_design_variable(name: str, value: str) -> dict:
        return service.set_design_variable(name=name, value=value)
