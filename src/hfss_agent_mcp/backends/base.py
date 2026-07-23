from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from hfss_agent_mcp.core.models import (
    ConnectionSpec,
    DesignSpec,
    DipoleAntennaSpec,
    PatchAntennaSpec,
    ProjectSpec,
    SetupSpec,
    SweepSpec,
)


class HfssBackend(Protocol):
    name: str

    def health(self) -> dict[str, Any]:
        ...

    def connect(self, spec: ConnectionSpec) -> dict[str, Any]:
        ...

    def get_project_info(self) -> dict[str, Any]:
        ...

    def create_project(self, spec: ProjectSpec) -> dict[str, Any]:
        ...

    def open_project(self, path: Path) -> dict[str, Any]:
        ...

    def save_project(self, path: Path | None = None) -> dict[str, Any]:
        ...

    def close_project(self, save: bool = False) -> dict[str, Any]:
        ...

    def disconnect(
        self,
        *,
        save_project: bool = True,
        close_projects: bool = True,
        close_desktop: bool = True,
    ) -> dict[str, Any]:
        ...

    def create_design(self, spec: DesignSpec) -> dict[str, Any]:
        ...

    def set_active_design(self, design_name: str) -> dict[str, Any]:
        ...

    def get_design_summary(self, design_name: str | None = None) -> dict[str, Any]:
        ...

    def create_patch_antenna(self, spec: PatchAntennaSpec) -> dict[str, Any]:
        ...

    def create_dipole_antenna(self, spec: DipoleAntennaSpec) -> dict[str, Any]:
        ...

    def set_design_variable(self, name: str, value: str) -> dict[str, Any]:
        ...

    def create_setup(self, spec: SetupSpec) -> dict[str, Any]:
        ...

    def create_frequency_sweep(self, spec: SweepSpec) -> dict[str, Any]:
        ...

    def validate_design(self) -> dict[str, Any]:
        ...

    def run_simulation(self, setup_name: str) -> dict[str, Any]:
        ...

    def get_s_parameters(
        self,
        setup_name: str,
        sweep_name: str | None,
        expression: str,
    ) -> dict[str, Any]:
        ...

    def export_touchstone(self, path: Path) -> dict[str, Any]:
        ...
