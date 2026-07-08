from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from hfss_agent_mcp.core.geometry import (
    BoundaryAssignment,
    GeometryPrimitive,
    PortAssignment,
)
from hfss_agent_mcp.core.models import PatchAntennaSpec


@dataclass(frozen=True)
class PatchDimensions:
    patch_width_mm: float
    patch_length_mm: float
    ground_width_mm: float
    ground_length_mm: float
    substrate_height_mm: float
    feed_width_mm: float
    feed_length_mm: float
    feed_offset_mm: float
    airbox_margin_mm: float
    airbox_height_mm: float
    effective_permittivity: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def build_patch_antenna(spec: PatchAntennaSpec) -> dict[str, Any]:
    dimensions = estimate_patch_dimensions(spec)
    object_names = {
        "substrate": f"{spec.name}_substrate",
        "ground": f"{spec.name}_ground",
        "patch": f"{spec.name}_patch",
        "feed": f"{spec.name}_feed",
        "airbox": f"{spec.name}_airbox",
        "port": f"{spec.name}_{spec.port_type}_port",
    }
    geometry = _build_geometry(spec, dimensions, object_names)
    boundaries = [
        BoundaryAssignment(
            name=f"{spec.name}_radiation",
            boundary_type="radiation",
            objects=(object_names["airbox"],),
        )
    ]
    ports = [
        PortAssignment(
            name=object_names["port"],
            port_type=spec.port_type,
            objects=(object_names["feed"], object_names["ground"]),
            integration_line_mm=(
                (0.0, -dimensions.ground_length_mm / 2, dimensions.substrate_height_mm),
                (0.0, -dimensions.ground_length_mm / 2, 0.0),
            ),
        )
    ]
    return {
        "antenna_name": spec.name,
        "frequency_ghz": spec.frequency_ghz,
        "materials": {
            "substrate": spec.substrate_material,
            "conductor": spec.conductor_material,
            "airbox": "air",
        },
        "object_names": object_names,
        "dimensions_mm": _rounded_dimensions(dimensions),
        "geometry": [primitive.to_dict() for primitive in geometry],
        "boundaries": [boundary.to_dict() for boundary in boundaries],
        "ports": [port.to_dict() for port in ports],
        "next_steps": [
            "create_simulation_setup",
            "validate_design",
            "run_simulation",
        ],
    }


def estimate_patch_dimensions(spec: PatchAntennaSpec) -> PatchDimensions:
    er = relative_permittivity(spec.substrate_material)
    frequency_hz = spec.frequency_ghz * 1e9
    c = 299_792_458.0

    calculated_width_mm = c / (2 * frequency_hz) * math.sqrt(2 / (er + 1)) * 1000
    width_for_eff = spec.patch_width_mm or calculated_width_mm
    eps_eff = (er + 1) / 2 + (er - 1) / 2 / math.sqrt(
        1 + 12 * spec.substrate_height_mm / width_for_eff
    )
    delta_l = (
        0.412
        * spec.substrate_height_mm
        * ((eps_eff + 0.3) * (width_for_eff / spec.substrate_height_mm + 0.264))
        / ((eps_eff - 0.258) * (width_for_eff / spec.substrate_height_mm + 0.8))
    )
    calculated_length_mm = c / (2 * frequency_hz * math.sqrt(eps_eff)) * 1000 - 2 * delta_l

    patch_width = spec.patch_width_mm or calculated_width_mm
    patch_length = spec.patch_length_mm or calculated_length_mm
    ground_width = spec.ground_width_mm or patch_width + 6 * spec.substrate_height_mm
    ground_length = spec.ground_length_mm or patch_length + 6 * spec.substrate_height_mm
    feed_length = max((ground_length - patch_length) / 2 + spec.feed_offset_mm, spec.feed_width_mm)
    airbox_margin = spec.airbox_margin_mm or max(c / (4 * frequency_hz) * 1000, ground_width / 2)
    airbox_height = spec.substrate_height_mm + 2 * airbox_margin

    return PatchDimensions(
        patch_width_mm=patch_width,
        patch_length_mm=patch_length,
        ground_width_mm=ground_width,
        ground_length_mm=ground_length,
        substrate_height_mm=spec.substrate_height_mm,
        feed_width_mm=spec.feed_width_mm,
        feed_length_mm=feed_length,
        feed_offset_mm=spec.feed_offset_mm,
        airbox_margin_mm=airbox_margin,
        airbox_height_mm=airbox_height,
        effective_permittivity=eps_eff,
    )


def relative_permittivity(material: str) -> float:
    lookup = {
        "fr4": 4.4,
        "fr4_epoxy": 4.4,
        "rogers4350": 3.48,
        "rogers_ro4350": 3.48,
        "air": 1.0,
    }
    return lookup.get(material.strip().lower(), 4.4)


def _build_geometry(
    spec: PatchAntennaSpec,
    dimensions: PatchDimensions,
    object_names: dict[str, str],
) -> list[GeometryPrimitive]:
    ground_width = dimensions.ground_width_mm
    ground_length = dimensions.ground_length_mm
    patch_width = dimensions.patch_width_mm
    patch_length = dimensions.patch_length_mm
    substrate_height = dimensions.substrate_height_mm
    feed_length = dimensions.feed_length_mm
    margin = dimensions.airbox_margin_mm

    return [
        GeometryPrimitive(
            name=object_names["substrate"],
            role="substrate",
            kind="box",
            origin_mm=(-ground_width / 2, -ground_length / 2, 0.0),
            size_mm=(ground_width, ground_length, substrate_height),
            material=spec.substrate_material,
        ),
        GeometryPrimitive(
            name=object_names["ground"],
            role="ground",
            kind="sheet",
            origin_mm=(-ground_width / 2, -ground_length / 2, 0.0),
            size_mm=(ground_width, ground_length, 0.0),
            material=spec.conductor_material,
        ),
        GeometryPrimitive(
            name=object_names["patch"],
            role="patch",
            kind="sheet",
            origin_mm=(-patch_width / 2, -patch_length / 2 + spec.feed_offset_mm, substrate_height),
            size_mm=(patch_width, patch_length, 0.0),
            material=spec.conductor_material,
        ),
        GeometryPrimitive(
            name=object_names["feed"],
            role="feed",
            kind="sheet",
            origin_mm=(-spec.feed_width_mm / 2, -ground_length / 2, substrate_height),
            size_mm=(spec.feed_width_mm, feed_length, 0.0),
            material=spec.conductor_material,
        ),
        GeometryPrimitive(
            name=object_names["airbox"],
            role="airbox",
            kind="box",
            origin_mm=(-ground_width / 2 - margin, -ground_length / 2 - margin, -margin),
            size_mm=(ground_width + 2 * margin, ground_length + 2 * margin, substrate_height + 2 * margin),
            material="air",
            metadata={"transparent": True},
        ),
    ]


def _rounded_dimensions(dimensions: PatchDimensions) -> dict[str, float]:
    return {
        key: round(value, 3)
        for key, value in dimensions.to_dict().items()
    }
