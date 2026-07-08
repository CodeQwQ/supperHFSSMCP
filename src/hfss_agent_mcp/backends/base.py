from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from hfss_agent_mcp.core.models import (
    ConnectionSpec,
    DesignSpec,
    PatchAntennaSpec,
    SetupSpec,
)


class HfssBackend(Protocol):
    name: str

    def health(self) -> dict[str, Any]:
        ...

    def connect(self, spec: ConnectionSpec) -> dict[str, Any]:
        ...

    def get_project_info(self) -> dict[str, Any]:
        ...

    def create_design(self, spec: DesignSpec) -> dict[str, Any]:
        ...

    def create_patch_antenna(self, spec: PatchAntennaSpec) -> dict[str, Any]:
        ...

    def create_setup(self, spec: SetupSpec) -> dict[str, Any]:
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
