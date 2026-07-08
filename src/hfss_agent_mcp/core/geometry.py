from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class GeometryPrimitive:
    name: str
    role: str
    kind: str
    origin_mm: tuple[float, float, float]
    size_mm: tuple[float, float, float]
    material: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BoundaryAssignment:
    name: str
    boundary_type: str
    objects: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PortAssignment:
    name: str
    port_type: str
    objects: tuple[str, ...]
    integration_line_mm: tuple[tuple[float, float, float], tuple[float, float, float]]
    impedance_ohm: float = 50.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
