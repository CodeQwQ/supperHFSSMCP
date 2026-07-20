from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from hfss_agent_mcp.core.geometry import BoundaryAssignment, GeometryPrimitive, PortAssignment
from hfss_agent_mcp.core.models import DipoleAntennaSpec


@dataclass(frozen=True)
class DipoleDimensions:
    arm_length_mm: float
    arm_width_mm: float
    arm_thickness_mm: float
    gap_mm: float
    total_length_mm: float
    airbox_margin_mm: float

    def to_dict(self) -> dict[str, float]:
        return {key: round(value, 3) for key, value in asdict(self).items()}


def build_dipole_antenna(spec: DipoleAntennaSpec) -> dict[str, Any]:
    dimensions = estimate_dipole_dimensions(spec)
    names = {
        "arm_negative": f"{spec.name}_arm_negative",
        "arm_positive": f"{spec.name}_arm_positive",
        "port": f"{spec.name}_{spec.port_type}_port",
        "airbox": f"{spec.name}_airbox",
    }
    geometry = _build_geometry(spec, dimensions, names)
    return {
        "antenna_name": spec.name,
        "antenna_type": "dipole",
        "frequency_ghz": spec.frequency_ghz,
        "materials": {"conductor": spec.conductor_material, "airbox": "air"},
        "object_names": names,
        "dimensions_mm": dimensions.to_dict(),
        "geometry": [item.to_dict() for item in geometry],
        "boundaries": [
            BoundaryAssignment(
                name=f"{spec.name}_radiation",
                boundary_type="radiation",
                objects=(names["airbox"],),
            ).to_dict()
        ],
        "ports": [
            PortAssignment(
                name=names["port"],
                port_type=spec.port_type,
                objects=(names["port"],),
                integration_line_mm=(
                    (-dimensions.gap_mm / 2, 0.0, 0.0),
                    (dimensions.gap_mm / 2, 0.0, 0.0),
                ),
            ).to_dict()
        ],
        "next_steps": ["create_simulation_setup", "validate_design", "run_simulation"],
    }


def estimate_dipole_dimensions(spec: DipoleAntennaSpec) -> DipoleDimensions:
    wavelength_mm = 299_792_458.0 / (spec.frequency_ghz * 1e9) * 1000
    arm_length = spec.arm_length_mm or wavelength_mm * 0.24
    margin = spec.airbox_margin_mm or wavelength_mm / 4
    return DipoleDimensions(
        arm_length_mm=arm_length,
        arm_width_mm=spec.arm_width_mm,
        arm_thickness_mm=spec.arm_thickness_mm,
        gap_mm=spec.gap_mm,
        total_length_mm=2 * arm_length + spec.gap_mm,
        airbox_margin_mm=margin,
    )


def _build_geometry(
    spec: DipoleAntennaSpec,
    dimensions: DipoleDimensions,
    names: dict[str, str],
) -> list[GeometryPrimitive]:
    arm = dimensions.arm_length_mm
    width = dimensions.arm_width_mm
    gap = dimensions.gap_mm
    margin = dimensions.airbox_margin_mm
    half_total = dimensions.total_length_mm / 2
    thickness = dimensions.arm_thickness_mm
    return [
        GeometryPrimitive(
            name=names["arm_negative"],
            role="arm_negative",
            kind="sheet",
            origin_mm=(-half_total, -width / 2, 0.0),
            size_mm=(arm, width, 0.0),
            material=spec.conductor_material,
        ),
        GeometryPrimitive(
            name=names["arm_positive"],
            role="arm_positive",
            kind="sheet",
            origin_mm=(gap / 2, -width / 2, 0.0),
            size_mm=(arm, width, 0.0),
            material=spec.conductor_material,
        ),
        GeometryPrimitive(
            name=names["port"],
            role="port",
            kind="sheet",
            origin_mm=(-gap / 2, -width / 2, 0.0),
            size_mm=(gap, width, 0.0),
            material="air",
            metadata={"orientation": "XY", "port_sheet": True},
        ),
        GeometryPrimitive(
            name=names["airbox"],
            role="airbox",
            kind="box",
            origin_mm=(-half_total - margin, -margin, -margin),
            size_mm=(
                dimensions.total_length_mm + 2 * margin,
                width + 2 * margin,
                thickness + 2 * margin,
            ),
            material="air",
            metadata={"transparent": True},
        ),
    ]
