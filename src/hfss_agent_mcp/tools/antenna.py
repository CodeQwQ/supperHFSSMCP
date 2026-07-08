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
        substrate_height_mm: float = 1.6,
        patch_length_mm: float | None = None,
        patch_width_mm: float | None = None,
        ground_length_mm: float | None = None,
        ground_width_mm: float | None = None,
        feed_offset_mm: float = 0.0,
        feed_width_mm: float = 3.0,
    ) -> dict:
        return service.create_patch_antenna(
            name=name,
            frequency_ghz=frequency_ghz,
            substrate_material=substrate_material,
            substrate_height_mm=substrate_height_mm,
            patch_length_mm=patch_length_mm,
            patch_width_mm=patch_width_mm,
            ground_length_mm=ground_length_mm,
            ground_width_mm=ground_width_mm,
            feed_offset_mm=feed_offset_mm,
            feed_width_mm=feed_width_mm,
        )
