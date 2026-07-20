from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolResponse:
    status: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConnectionSpec:
    desktop_version: str | None = None
    project_path: str | None = None
    design_name: str | None = None
    solution_type: str = "DrivenModal"
    non_graphical: bool = True
    new_desktop: bool = False
    student_version: bool = False
    aedt_executable: str | None = None
    connect_timeout_seconds: float | None = None
    machine: str | None = None
    port: int | None = None
    session_id: str | None = None
    owner: str | None = None


@dataclass(frozen=True)
class SessionLaunchSpec:
    desktop_version: str | None = None
    machine: str | None = None
    port: int | None = None
    project_path: str | None = None
    design_name: str | None = None
    owner: str | None = None
    non_graphical: bool = True


@dataclass(frozen=True)
class DesignSpec:
    design_name: str
    project_name: str | None = None
    solution_type: str = "DrivenModal"


@dataclass(frozen=True)
class ProjectSpec:
    project_name: str
    project_path: str


@dataclass(frozen=True)
class PatchAntennaSpec:
    name: str
    frequency_ghz: float
    substrate_material: str = "FR4_epoxy"
    conductor_material: str = "copper"
    substrate_height_mm: float = 1.6
    patch_length_mm: float | None = None
    patch_width_mm: float | None = None
    ground_length_mm: float | None = None
    ground_width_mm: float | None = None
    feed_offset_mm: float = 0.0
    feed_width_mm: float = 3.0
    airbox_margin_mm: float | None = None
    port_type: str = "lumped"


@dataclass(frozen=True)
class DipoleAntennaSpec:
    name: str
    frequency_ghz: float
    conductor_material: str = "copper"
    arm_length_mm: float | None = None
    arm_width_mm: float = 2.0
    arm_thickness_mm: float = 0.035
    gap_mm: float = 1.0
    airbox_margin_mm: float | None = None
    port_type: str = "lumped"


@dataclass(frozen=True)
class SetupSpec:
    setup_name: str
    frequency_ghz: float
    sweep_name: str = "Sweep1"
    sweep_start_ghz: float = 1.0
    sweep_stop_ghz: float = 3.0
    sweep_points: int = 201
    sweep_type: str = "LinearCount"
    max_delta_s: float = 0.02
    max_passes: int = 10
    min_passes: int = 1


@dataclass(frozen=True)
class SweepSpec:
    setup_name: str
    sweep_name: str
    sweep_start_ghz: float
    sweep_stop_ghz: float
    sweep_points: int
    sweep_type: str = "LinearCount"
