from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from hfss_agent_mcp.core.service import HfssService


def register(mcp: FastMCP, service: HfssService) -> None:
    @mcp.tool(
        description=(
            "Create a 3D HFSS box in the active design. Coordinates and sizes use mm; "
            "origin_mm and size_mm must each contain three numbers."
        )
    )
    def create_model_box(
        name: str,
        origin_mm: list[float],
        size_mm: list[float],
        material: str = "air",
        role: str = "custom",
    ) -> dict:
        return service.create_model_box(
            name=name,
            origin_mm=origin_mm,
            size_mm=size_mm,
            material=material,
            role=role,
        )

    @mcp.tool(
        description=(
            "Create a rectangular HFSS sheet in the active design. Coordinates and "
            "sizes use mm; orientation must be XY, YZ, or XZ."
        )
    )
    def create_model_sheet(
        name: str,
        orientation: str,
        origin_mm: list[float],
        size_mm: list[float],
        material: str = "copper",
        role: str = "custom",
    ) -> dict:
        return service.create_model_sheet(
            name=name,
            orientation=orientation,
            origin_mm=origin_mm,
            size_mm=size_mm,
            material=material,
            role=role,
        )

    @mcp.tool(description="Set the material of one existing HFSS model object.")
    def set_object_material(object_name: str, material: str) -> dict:
        return service.set_object_material(object_name=object_name, material=material)

    @mcp.tool(description="Assign a Perfect E boundary to explicit existing object names.")
    def assign_perfect_e(
        name: str,
        object_names: list[str],
        is_infinite_ground: bool = False,
    ) -> dict:
        return service.assign_perfect_e(
            name=name,
            object_names=object_names,
            is_infinite_ground=is_infinite_ground,
        )

    @mcp.tool(description="Assign a Radiation boundary to explicit existing object names.")
    def assign_radiation_boundary(name: str, object_names: list[str]) -> dict:
        return service.assign_radiation_boundary(name=name, object_names=object_names)

    @mcp.tool(
        description=(
            "Create a lumped port on an existing port sheet. Integration line points "
            "use mm and must each contain three numbers."
        )
    )
    def create_lumped_port(
        name: str,
        sheet_name: str,
        integration_start_mm: list[float],
        integration_end_mm: list[float],
        impedance_ohm: float = 50.0,
    ) -> dict:
        return service.create_lumped_port(
            name=name,
            sheet_name=sheet_name,
            integration_start_mm=integration_start_mm,
            integration_end_mm=integration_end_mm,
            impedance_ohm=impedance_ohm,
        )

    @mcp.tool(
        description=(
            "Delete explicit existing object names from the active design. Wildcards "
            "and clear-all operations are not supported."
        )
    )
    def delete_model_objects(object_names: list[str]) -> dict:
        return service.delete_model_objects(object_names=object_names)
