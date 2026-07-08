from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from hfss_agent_mcp.backends.base import HfssBackend
from hfss_agent_mcp.core.errors import HfssAgentError, InputValidationError
from hfss_agent_mcp.core.models import (
    ConnectionSpec,
    DesignSpec,
    PatchAntennaSpec,
    SetupSpec,
    ToolResponse,
)


class HfssService:
    def __init__(self, backend: HfssBackend, output_root: Path | str) -> None:
        self.backend = backend
        self.output_root = Path(output_root).resolve()

    def health_check(self) -> dict[str, Any]:
        return self._ok(
            "HFSS Agent MCP service is reachable.",
            data={
                "backend": self.backend.health(),
                "output_root": str(self.output_root),
            },
            next_actions=["connect_hfss", "get_project_info"],
        )

    def connect_hfss(
        self,
        desktop_version: str | None = None,
        project_path: str | None = None,
        design_name: str | None = None,
        solution_type: str = "DrivenModal",
        non_graphical: bool = True,
        new_desktop: bool = False,
        machine: str | None = None,
        port: int | None = None,
    ) -> dict[str, Any]:
        spec = ConnectionSpec(
            desktop_version=desktop_version,
            project_path=project_path,
            design_name=design_name,
            solution_type=solution_type,
            non_graphical=non_graphical,
            new_desktop=new_desktop,
            machine=machine,
            port=port,
        )
        return self._call(
            "Connected to HFSS session.",
            lambda: self.backend.connect(spec),
            next_actions=["get_project_info", "create_hfss_design", "create_patch_antenna"],
        )

    def get_project_info(self) -> dict[str, Any]:
        return self._call(
            "Project state retrieved.",
            self.backend.get_project_info,
            next_actions=["create_hfss_design", "validate_design"],
        )

    def create_hfss_design(
        self,
        design_name: str,
        project_name: str | None = None,
        solution_type: str = "DrivenModal",
    ) -> dict[str, Any]:
        _require_non_empty("design_name", design_name)
        spec = DesignSpec(
            project_name=project_name,
            design_name=design_name,
            solution_type=solution_type,
        )
        return self._call(
            "HFSS design is ready.",
            lambda: self.backend.create_design(spec),
            next_actions=["create_patch_antenna", "create_simulation_setup"],
        )

    def create_patch_antenna(
        self,
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
    ) -> dict[str, Any]:
        _require_non_empty("name", name)
        _require_positive("frequency_ghz", frequency_ghz)
        _require_positive("substrate_height_mm", substrate_height_mm)
        _require_positive("feed_width_mm", feed_width_mm)
        for field_name, value in {
            "patch_length_mm": patch_length_mm,
            "patch_width_mm": patch_width_mm,
            "ground_length_mm": ground_length_mm,
            "ground_width_mm": ground_width_mm,
        }.items():
            if value is not None:
                _require_positive(field_name, value)

        spec = PatchAntennaSpec(
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
        return self._call(
            "Patch antenna workflow object created.",
            lambda: self.backend.create_patch_antenna(spec),
            next_actions=["create_simulation_setup", "validate_design"],
        )

    def create_simulation_setup(
        self,
        setup_name: str,
        frequency_ghz: float,
        sweep_name: str = "Sweep1",
        sweep_start_ghz: float = 1.0,
        sweep_stop_ghz: float = 3.0,
        sweep_points: int = 201,
    ) -> dict[str, Any]:
        _require_non_empty("setup_name", setup_name)
        _require_positive("frequency_ghz", frequency_ghz)
        _require_positive("sweep_start_ghz", sweep_start_ghz)
        _require_positive("sweep_stop_ghz", sweep_stop_ghz)
        if sweep_stop_ghz <= sweep_start_ghz:
            raise InputValidationError("sweep_stop_ghz must be greater than sweep_start_ghz.")
        if sweep_points < 2:
            raise InputValidationError("sweep_points must be at least 2.")

        spec = SetupSpec(
            setup_name=setup_name,
            frequency_ghz=frequency_ghz,
            sweep_name=sweep_name,
            sweep_start_ghz=sweep_start_ghz,
            sweep_stop_ghz=sweep_stop_ghz,
            sweep_points=sweep_points,
        )
        return self._call(
            "Simulation setup created.",
            lambda: self.backend.create_setup(spec),
            next_actions=["validate_design", "run_simulation"],
        )

    def validate_design(self) -> dict[str, Any]:
        return self._call(
            "Design validation finished.",
            self.backend.validate_design,
            next_actions=["run_simulation", "get_project_info"],
        )

    def run_simulation(self, setup_name: str) -> dict[str, Any]:
        _require_non_empty("setup_name", setup_name)
        return self._call(
            "Simulation run finished.",
            lambda: self.backend.run_simulation(setup_name),
            next_actions=["get_s_parameters", "export_touchstone"],
        )

    def get_s_parameters(
        self,
        setup_name: str,
        sweep_name: str | None = None,
        expression: str = "dB(S(1,1))",
    ) -> dict[str, Any]:
        _require_non_empty("setup_name", setup_name)
        _require_non_empty("expression", expression)
        return self._call(
            "S-parameter data retrieved.",
            lambda: self.backend.get_s_parameters(setup_name, sweep_name, expression),
            next_actions=["export_touchstone", "create_patch_antenna"],
        )

    def export_touchstone(self, relative_path: str = "touchstone/result.s1p") -> dict[str, Any]:
        return self._call(
            "Touchstone file exported.",
            lambda: self.backend.export_touchstone(self._safe_output_path(relative_path)),
            next_actions=["get_s_parameters"],
        )

    def _safe_output_path(self, relative_path: str) -> Path:
        _require_non_empty("relative_path", relative_path)
        candidate = (self.output_root / relative_path).resolve()
        if self.output_root != candidate and self.output_root not in candidate.parents:
            raise InputValidationError("relative_path must stay inside HFSS_AGENT_OUTPUT_ROOT.")
        return candidate

    def _call(
        self,
        message: str,
        operation: Callable[[], dict[str, Any]],
        next_actions: list[str] | None = None,
    ) -> dict[str, Any]:
        try:
            return self._ok(message, operation(), next_actions=next_actions)
        except HfssAgentError as exc:
            return ToolResponse(
                status="error",
                message=str(exc),
                data={"error_type": exc.__class__.__name__},
                next_actions=["health_check", "get_project_info"],
            ).to_dict()

    def _ok(
        self,
        message: str,
        data: dict[str, Any],
        next_actions: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        return ToolResponse(
            status="ok",
            message=message,
            data=data,
            warnings=warnings or [],
            next_actions=next_actions or [],
        ).to_dict()


def _require_non_empty(field_name: str, value: str | None) -> None:
    if not value or not value.strip():
        raise InputValidationError(f"{field_name} must be a non-empty string.")


def _require_positive(field_name: str, value: float) -> None:
    if value <= 0:
        raise InputValidationError(f"{field_name} must be positive.")
