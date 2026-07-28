from __future__ import annotations

import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from hfss_agent_mcp.backends.base import HfssBackend
from hfss_agent_mcp.backends.cli_runner import CliRunner
from hfss_agent_mcp.backends.com import ComAdapter
from hfss_agent_mcp.config import ServerConfig
from hfss_agent_mcp.core.environment import collect_environment
from hfss_agent_mcp.core.errors import (
    BackendUnavailableError,
    HfssAgentError,
    InputValidationError,
    SessionError,
)
from hfss_agent_mcp.core.jobs import JobManager
from hfss_agent_mcp.core.models import (
    BoundarySpec,
    BoxSpec,
    ConnectionSpec,
    DeleteObjectsSpec,
    DesignSpec,
    DipoleAntennaSpec,
    LumpedPortSpec,
    MaterialAssignmentSpec,
    PatchAntennaSpec,
    ProjectSpec,
    SessionLaunchSpec,
    SetupSpec,
    SheetSpec,
    SweepSpec,
    ToolResponse,
)
from hfss_agent_mcp.core.project import ProjectPathPolicy
from hfss_agent_mcp.core.optimization import evaluate_candidate, optimize_candidates
from hfss_agent_mcp.core.results import analyze_input_impedance, analyze_s_parameter_points
from hfss_agent_mcp.core.session import SessionManager
from hfss_agent_mcp.core.scripts import ScriptRegistry
from hfss_agent_mcp.core.security import SecurityManager, current_identity
from hfss_agent_mcp.results.analysis import build_result_report, write_result_report


class HfssService:
    def __init__(
        self,
        backend: HfssBackend,
        output_root: Path | str,
        config: ServerConfig | None = None,
    ) -> None:
        self.backend = backend
        self.output_root = Path(output_root).resolve()
        self.config = config or ServerConfig(output_root=self.output_root)
        self.sessions = SessionManager(backend.name)
        self.project_paths = ProjectPathPolicy(self.output_root / "projects")
        self.jobs = JobManager(self.output_root / "simulation_jobs.json")
        self._simulation_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="hfss-agent-simulation",
        )
        self.security = SecurityManager(
            self.output_root,
            audit_log_path=self.config.audit_log_path,
            require_client_id=self.config.require_client_id,
            lock_timeout_seconds=self.config.lock_timeout_seconds,
        )
        self.script_registry = ScriptRegistry(self.config.script_root)
        self.script_registry.register(
            "aedt_probe",
            "aedt_probe.py",
            "Read the active AEDT project and design without changing the model.",
        )
        self.com_adapter = ComAdapter(
            self.script_registry.root,
            self.output_root,
            progid=self.config.com_progid,
        )

    def health_check(self) -> dict[str, Any]:
        environment = self._environment_data()
        return self._ok(
            "HFSS Agent MCP service is reachable.",
            data={
                "backend": self.backend.health(),
                "output_root": str(self.output_root),
                "environment": environment,
            },
            warnings=environment["warnings"],
            next_actions=["env_check", "connect_hfss", "get_project_info"],
        )

    def env_check(self) -> dict[str, Any]:
        environment = self._environment_data()
        return self._ok(
            "Environment check finished.",
            data=environment,
            warnings=environment["warnings"],
            next_actions=["connect_hfss", "health_check"],
        )

    def connect_hfss(
        self,
        desktop_version: str | None = None,
        project_path: str | None = None,
        design_name: str | None = None,
        solution_type: str = "DrivenModal",
        non_graphical: bool = False,
        new_desktop: bool = False,
        student_version: bool | None = None,
        machine: str | None = None,
        port: int | None = None,
        session_id: str | None = None,
        owner: str | None = None,
        connect_timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if connect_timeout_seconds is not None:
            _require_positive("connect_timeout_seconds", connect_timeout_seconds)
        resolved_student_version = (
            student_version
            if student_version is not None
            else self._is_student_aedt_configured()
        )
        resolved_desktop_version = desktop_version or self._desktop_version_from_configured_aedt()
        resolved_connect_timeout = connect_timeout_seconds or self.config.connect_timeout_seconds
        spec = ConnectionSpec(
            desktop_version=resolved_desktop_version,
            project_path=project_path,
            design_name=design_name,
            solution_type=solution_type,
            non_graphical=non_graphical,
            new_desktop=new_desktop,
            student_version=resolved_student_version,
            aedt_executable=str(self.config.aedt_executable) if self.config.aedt_executable else None,
            connect_timeout_seconds=resolved_connect_timeout,
            machine=machine,
            port=port,
            session_id=session_id,
            owner=owner,
        )
        next_actions = [
            "get_session_info",
            "get_project_info",
            "create_hfss_design",
            "create_patch_antenna",
        ]
        try:
            return self._ok(
                "Connected to HFSS session.",
                self._connect_session(spec),
                next_actions=next_actions,
            )
        except (HfssAgentError, ValueError, RuntimeError, OSError) as exc:
            session = self._active_session_data()
            data: dict[str, Any] = {"error_type": exc.__class__.__name__}
            if session:
                data["session"] = session
            return self._error_response(
                exc,
                data=data,
                next_actions=["get_session_info", "env_check", "connect_hfss"],
            )

    def list_aedt_sessions(self) -> dict[str, Any]:
        return self._call(
            "AEDT session records retrieved.",
            lambda: {
                "count": len(self._owned_sessions()),
                "active_session_id": self._owned_active_session_id(),
                "sessions": [record.to_dict() for record in self._owned_sessions()],
            },
            next_actions=["launch_aedt", "connect_hfss"],
        )

    def launch_aedt(
        self,
        desktop_version: str | None = None,
        machine: str | None = None,
        port: int | None = None,
        project_path: str | None = None,
        design_name: str | None = None,
        owner: str | None = None,
        non_graphical: bool = False,
    ) -> dict[str, Any]:
        spec = SessionLaunchSpec(
            desktop_version=desktop_version,
            machine=machine,
            port=port,
            project_path=project_path,
            design_name=design_name,
            owner=owner,
            non_graphical=non_graphical,
        )
        return self._call(
            "AEDT session record launched.",
            lambda: {"session": self.sessions.launch(spec).to_dict()},
            next_actions=["connect_hfss", "get_session_info"],
        )

    def get_session_info(self, session_id: str) -> dict[str, Any]:
        _require_non_empty("session_id", session_id)
        return self._call(
            "AEDT session record retrieved.",
            lambda: {"session": self._require_owned_session(session_id).to_dict()},
            next_actions=["connect_hfss", "release_connection"],
        )

    def release_connection(
        self,
        session_id: str,
        save_project: bool = True,
        close_desktop: bool = True,
    ) -> dict[str, Any]:
        _require_non_empty("session_id", session_id)
        return self._call(
            "AEDT session released.",
            lambda: self._release_connection(
                session_id,
                save_project=save_project,
                close_desktop=close_desktop,
            ),
            next_actions=["list_aedt_sessions", "connect_hfss"],
        )

    def get_project_info(self) -> dict[str, Any]:
        return self._call(
            "Project state retrieved.",
            self.backend.get_project_info,
            next_actions=["create_project", "open_project", "create_hfss_design", "validate_design"],
        )

    def create_project(
        self,
        project_name: str,
        relative_path: str | None = None,
    ) -> dict[str, Any]:
        return self._call(
            "HFSS project created.",
            lambda: self._create_project(project_name, relative_path),
            next_actions=["create_hfss_design", "save_project", "get_project_info"],
        )

    def open_project(self, relative_path: str) -> dict[str, Any]:
        return self._call(
            "HFSS project opened.",
            lambda: self.backend.open_project(self._project_policy().resolve_relative(relative_path)),
            next_actions=["get_project_info", "create_hfss_design", "set_active_design"],
        )

    def save_project(self, relative_path: str | None = None) -> dict[str, Any]:
        return self._call(
            "HFSS project saved.",
            lambda: self.backend.save_project(
                self._project_policy().resolve_relative(relative_path)
                if relative_path is not None
                else None
            ),
            next_actions=["get_project_info", "close_project"],
        )

    def close_project(self, save: bool = False) -> dict[str, Any]:
        return self._call(
            "HFSS project closed.",
            lambda: self.backend.close_project(save=save),
            next_actions=["open_project", "create_project"],
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
            next_actions=["get_design_summary", "create_patch_antenna", "create_simulation_setup"],
        )

    def set_active_design(self, design_name: str) -> dict[str, Any]:
        _require_non_empty("design_name", design_name)
        return self._call(
            "Active HFSS design selected.",
            lambda: self.backend.set_active_design(design_name),
            next_actions=["get_design_summary", "create_patch_antenna", "validate_design"],
        )

    def get_design_summary(self, design_name: str | None = None) -> dict[str, Any]:
        return self._call(
            "HFSS design summary retrieved.",
            lambda: self.backend.get_design_summary(design_name),
            next_actions=["set_active_design", "create_model_box", "create_patch_antenna", "create_simulation_setup"],
        )

    def create_model_box(
        self,
        name: str,
        origin_mm: list[float],
        size_mm: list[float],
        material: str = "air",
        role: str = "custom",
    ) -> dict[str, Any]:
        _require_non_empty("name", name)
        _require_non_empty("material", material)
        _require_non_empty("role", role)
        origin = _require_vector("origin_mm", origin_mm, 3)
        size = _require_vector("size_mm", size_mm, 3)
        for index, value in enumerate(size):
            _require_positive(f"size_mm[{index}]", value)
        spec = BoxSpec(
            name=name,
            origin_mm=(origin[0], origin[1], origin[2]),
            size_mm=(size[0], size[1], size[2]),
            material=material,
            role=role,
        )
        return self._call(
            "HFSS model box created.",
            lambda: self.backend.create_model_box(spec),
            next_actions=["create_model_sheet", "assign_radiation_boundary", "get_design_summary"],
        )

    def create_model_sheet(
        self,
        name: str,
        orientation: str,
        origin_mm: list[float],
        size_mm: list[float],
        material: str = "copper",
        role: str = "custom",
    ) -> dict[str, Any]:
        _require_non_empty("name", name)
        _require_non_empty("orientation", orientation)
        _require_non_empty("material", material)
        _require_non_empty("role", role)
        normalized_orientation = orientation.upper()
        if normalized_orientation not in {"XY", "YZ", "XZ"}:
            raise InputValidationError("orientation must be one of: XY, YZ, XZ.")
        origin = _require_vector("origin_mm", origin_mm, 3)
        size = _require_vector("size_mm", size_mm, 2)
        for index, value in enumerate(size):
            _require_positive(f"size_mm[{index}]", value)
        spec = SheetSpec(
            name=name,
            orientation=normalized_orientation,
            origin_mm=(origin[0], origin[1], origin[2]),
            size_mm=(size[0], size[1]),
            material=material,
            role=role,
        )
        return self._call(
            "HFSS model sheet created.",
            lambda: self.backend.create_model_sheet(spec),
            next_actions=["assign_perfect_e", "create_lumped_port", "get_design_summary"],
        )

    def set_object_material(self, object_name: str, material: str) -> dict[str, Any]:
        _require_non_empty("object_name", object_name)
        _require_non_empty("material", material)
        spec = MaterialAssignmentSpec(object_name=object_name, material=material)
        return self._call(
            "HFSS object material updated.",
            lambda: self.backend.set_object_material(spec),
            next_actions=["get_design_summary", "validate_design"],
        )

    def assign_perfect_e(
        self,
        name: str,
        object_names: list[str],
        is_infinite_ground: bool = False,
    ) -> dict[str, Any]:
        _require_non_empty("name", name)
        objects = _require_object_names(object_names)
        spec = BoundarySpec(
            name=name,
            boundary_type="perfect_e",
            object_names=objects,
            is_infinite_ground=is_infinite_ground,
        )
        return self._call(
            "Perfect E boundary assigned.",
            lambda: self.backend.assign_boundary(spec),
            next_actions=["create_lumped_port", "assign_radiation_boundary", "validate_design"],
        )

    def assign_radiation_boundary(self, name: str, object_names: list[str]) -> dict[str, Any]:
        _require_non_empty("name", name)
        objects = _require_object_names(object_names)
        spec = BoundarySpec(
            name=name,
            boundary_type="radiation",
            object_names=objects,
        )
        return self._call(
            "Radiation boundary assigned.",
            lambda: self.backend.assign_boundary(spec),
            next_actions=["create_lumped_port", "create_simulation_setup", "validate_design"],
        )

    def create_lumped_port(
        self,
        name: str,
        sheet_name: str,
        integration_start_mm: list[float],
        integration_end_mm: list[float],
        impedance_ohm: float = 50.0,
    ) -> dict[str, Any]:
        _require_non_empty("name", name)
        _require_non_empty("sheet_name", sheet_name)
        start = _require_vector("integration_start_mm", integration_start_mm, 3)
        end = _require_vector("integration_end_mm", integration_end_mm, 3)
        _require_positive("impedance_ohm", impedance_ohm)
        spec = LumpedPortSpec(
            name=name,
            sheet_name=sheet_name,
            integration_start_mm=(start[0], start[1], start[2]),
            integration_end_mm=(end[0], end[1], end[2]),
            impedance_ohm=impedance_ohm,
        )
        return self._call(
            "Lumped port created.",
            lambda: self.backend.create_lumped_port(spec),
            next_actions=["create_simulation_setup", "validate_design"],
        )

    def delete_model_objects(self, object_names: list[str]) -> dict[str, Any]:
        objects = _require_object_names(object_names)
        for object_name in objects:
            if any(marker in object_name for marker in ("*", "?")):
                raise InputValidationError("delete_model_objects does not support wildcards.")
        spec = DeleteObjectsSpec(object_names=objects)
        return self._call(
            "HFSS model object(s) deleted.",
            lambda: self.backend.delete_model_objects(spec),
            next_actions=["get_design_summary", "validate_design"],
        )

    def create_patch_antenna(
        self,
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
    ) -> dict[str, Any]:
        _require_non_empty("name", name)
        _require_non_empty("substrate_material", substrate_material)
        _require_non_empty("conductor_material", conductor_material)
        _require_non_empty("port_type", port_type)
        _require_positive("frequency_ghz", frequency_ghz)
        _require_positive("substrate_height_mm", substrate_height_mm)
        _require_positive("feed_width_mm", feed_width_mm)
        for field_name, value in {
            "patch_length_mm": patch_length_mm,
            "patch_width_mm": patch_width_mm,
            "ground_length_mm": ground_length_mm,
            "ground_width_mm": ground_width_mm,
            "airbox_margin_mm": airbox_margin_mm,
        }.items():
            if value is not None:
                _require_positive(field_name, value)

        spec = PatchAntennaSpec(
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
        return self._call(
            "Patch antenna workflow object created.",
            lambda: self.backend.create_patch_antenna(spec),
            next_actions=["create_simulation_setup", "validate_design"],
        )

    def create_dipole_antenna(
        self,
        name: str,
        frequency_ghz: float,
        conductor_material: str = "copper",
        arm_length_mm: float | None = None,
        arm_width_mm: float = 2.0,
        arm_thickness_mm: float = 0.035,
        gap_mm: float = 1.0,
        airbox_margin_mm: float | None = None,
        port_type: str = "lumped",
    ) -> dict[str, Any]:
        _require_non_empty("name", name)
        _require_non_empty("conductor_material", conductor_material)
        _require_non_empty("port_type", port_type)
        _require_positive("frequency_ghz", frequency_ghz)
        _require_positive("arm_width_mm", arm_width_mm)
        _require_positive("arm_thickness_mm", arm_thickness_mm)
        _require_positive("gap_mm", gap_mm)
        for field_name, value in {
            "arm_length_mm": arm_length_mm,
            "airbox_margin_mm": airbox_margin_mm,
        }.items():
            if value is not None:
                _require_positive(field_name, value)
        spec = DipoleAntennaSpec(
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
        return self._call(
            "Dipole antenna workflow object created.",
            lambda: self.backend.create_dipole_antenna(spec),
            next_actions=["create_simulation_setup", "validate_design"],
        )

    def set_design_variable(self, name: str, value: str) -> dict[str, Any]:
        _require_non_empty("name", name)
        _require_non_empty("value", value)
        return self._call(
            "HFSS design variable updated.",
            lambda: self.backend.set_design_variable(name, value),
            next_actions=["run_simulation", "optimize_design_variable"],
        )

    def optimize_design_variable(
        self,
        variable_name: str,
        candidate_values: list[str],
        setup_name: str,
        target_frequency_ghz: float,
        sweep_name: str | None = None,
        expression: str = "dB(S(1,1))",
        threshold_db: float = -10.0,
        max_evaluations: int | None = None,
    ) -> dict[str, Any]:
        _require_non_empty("variable_name", variable_name)
        _require_non_empty("setup_name", setup_name)
        _require_non_empty("expression", expression)
        _require_positive("target_frequency_ghz", target_frequency_ghz)
        if not candidate_values:
            raise InputValidationError("candidate_values must contain at least one value.")

        def evaluate(value: str) -> dict[str, Any]:
            variable = self.backend.set_design_variable(variable_name, str(value))
            simulation = self._run_validated_backend_simulation(setup_name)
            if simulation.get("status") != "completed":
                raise BackendUnavailableError(
                    simulation.get("error", f"HFSS simulation failed for {setup_name!r}.")
                )
            raw = self.backend.get_s_parameters(setup_name, sweep_name, expression)
            result = evaluate_candidate(
                value,
                raw,
                target_frequency_ghz=target_frequency_ghz,
                threshold_db=threshold_db,
            )
            result["variable"] = variable
            result["simulation"] = simulation
            return result

        return self._call(
            "HFSS design-variable optimization completed.",
            lambda: optimize_candidates(
                candidate_values,
                evaluate,
                max_evaluations=max_evaluations,
            ),
            next_actions=["set_design_variable", "get_s_parameters", "analyze_s_parameters"],
        )

    def create_simulation_setup(
        self,
        setup_name: str,
        frequency_ghz: float,
        sweep_name: str = "Sweep1",
        sweep_start_ghz: float = 1.0,
        sweep_stop_ghz: float = 3.0,
        sweep_points: int = 201,
        sweep_type: str = "LinearCount",
        max_delta_s: float = 0.02,
        max_passes: int = 10,
        min_passes: int = 1,
    ) -> dict[str, Any]:
        _require_non_empty("setup_name", setup_name)
        _require_non_empty("sweep_name", sweep_name)
        _require_non_empty("sweep_type", sweep_type)
        _require_positive("frequency_ghz", frequency_ghz)
        _require_positive("sweep_start_ghz", sweep_start_ghz)
        _require_positive("sweep_stop_ghz", sweep_stop_ghz)
        _require_positive("max_delta_s", max_delta_s)
        if sweep_stop_ghz <= sweep_start_ghz:
            raise InputValidationError("sweep_stop_ghz must be greater than sweep_start_ghz.")
        if sweep_points < 2:
            raise InputValidationError("sweep_points must be at least 2.")
        if max_passes < 1:
            raise InputValidationError("max_passes must be at least 1.")
        if min_passes < 1:
            raise InputValidationError("min_passes must be at least 1.")
        if min_passes > max_passes:
            raise InputValidationError("min_passes must be less than or equal to max_passes.")

        spec = SetupSpec(
            setup_name=setup_name,
            frequency_ghz=frequency_ghz,
            sweep_name=sweep_name,
            sweep_start_ghz=sweep_start_ghz,
            sweep_stop_ghz=sweep_stop_ghz,
            sweep_points=sweep_points,
            sweep_type=sweep_type,
            max_delta_s=max_delta_s,
            max_passes=max_passes,
            min_passes=min_passes,
        )
        return self._call(
            "Simulation setup created.",
            lambda: self.backend.create_setup(spec),
            next_actions=["create_frequency_sweep", "validate_design", "run_simulation"],
        )

    def create_frequency_sweep(
        self,
        setup_name: str,
        sweep_name: str,
        sweep_start_ghz: float,
        sweep_stop_ghz: float,
        sweep_points: int,
        sweep_type: str = "LinearCount",
    ) -> dict[str, Any]:
        _require_non_empty("setup_name", setup_name)
        _require_non_empty("sweep_name", sweep_name)
        _require_non_empty("sweep_type", sweep_type)
        _require_positive("sweep_start_ghz", sweep_start_ghz)
        _require_positive("sweep_stop_ghz", sweep_stop_ghz)
        if sweep_stop_ghz <= sweep_start_ghz:
            raise InputValidationError("sweep_stop_ghz must be greater than sweep_start_ghz.")
        if sweep_points < 2:
            raise InputValidationError("sweep_points must be at least 2.")

        spec = SweepSpec(
            setup_name=setup_name,
            sweep_name=sweep_name,
            sweep_start_ghz=sweep_start_ghz,
            sweep_stop_ghz=sweep_stop_ghz,
            sweep_points=sweep_points,
            sweep_type=sweep_type,
        )
        return self._call(
            "Frequency sweep created.",
            lambda: self.backend.create_frequency_sweep(spec),
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
            "Simulation job started.",
            lambda: self._run_simulation_job(setup_name),
            next_actions=["get_simulation_job", "get_s_parameters", "export_touchstone"],
        )

    def get_simulation_job(self, job_id: str) -> dict[str, Any]:
        _require_non_empty("job_id", job_id)
        return self._call(
            "Simulation job retrieved.",
            lambda: {"job": self.jobs.snapshot(job_id, owner=self._owner())},
            next_actions=["get_s_parameters", "run_simulation"],
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
            next_actions=["analyze_s_parameters", "export_touchstone", "create_patch_antenna"],
        )

    def list_automation_scripts(self) -> dict[str, Any]:
        return self._call(
            "Registered HFSS automation scripts retrieved.",
            lambda: {"scripts": self.script_registry.list()},
            next_actions=["run_automation_script"],
        )

    def run_automation_script(
        self,
        script_id: str,
        runner: str = "pyaedt",
        operation: str = "script",
        port: int | None = None,
        project_path: str | None = None,
        relative_output: str | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload_arguments = arguments or {}
        return self._call(
            "HFSS automation operation finished.",
            lambda: self._run_automation(
                script_id=script_id,
                runner=runner,
                operation=operation,
                port=port,
                project_path=project_path,
                relative_output=relative_output,
                arguments=payload_arguments,
            ),
            next_actions=["list_automation_scripts", "get_project_info"],
        )

    def analyze_s_parameters(
        self,
        setup_name: str,
        sweep_name: str | None = None,
        expression: str = "dB(S(1,1))",
        target_frequency_ghz: float | None = None,
        threshold_db: float = -10.0,
    ) -> dict[str, Any]:
        _require_non_empty("setup_name", setup_name)
        _require_non_empty("expression", expression)
        if target_frequency_ghz is not None:
            _require_positive("target_frequency_ghz", target_frequency_ghz)
        return self._call(
            "S-parameter analysis completed.",
            lambda: self._analyze_s_parameters_data(
                setup_name, sweep_name, expression, target_frequency_ghz, threshold_db
            ),
            next_actions=["export_result_report", "export_touchstone", "create_patch_antenna"],
        )

    def analyze_input_impedance(
        self,
        setup_name: str,
        sweep_name: str | None = None,
        expression: str = "Z(1,1)",
        target_frequency_ghz: float | None = None,
    ) -> dict[str, Any]:
        _require_non_empty("setup_name", setup_name)
        _require_non_empty("expression", expression)
        if target_frequency_ghz is not None:
            _require_positive("target_frequency_ghz", target_frequency_ghz)
        return self._call(
            "Input impedance analysis completed.",
            lambda: self._analyze_input_impedance_data(
                setup_name, sweep_name, expression, target_frequency_ghz
            ),
            next_actions=["export_result_report", "analyze_s_parameters"],
        )

    def export_result_report(
        self,
        setup_name: str,
        relative_path: str = "results/report.json",
        sweep_name: str | None = None,
        expression: str = "dB(S(1,1))",
        target_frequency_ghz: float | None = None,
        threshold_db: float = -10.0,
    ) -> dict[str, Any]:
        _require_non_empty("setup_name", setup_name)
        _require_non_empty("expression", expression)
        return self._call(
            "Result report exported.",
            lambda: self._export_result_report_data(
                setup_name,
                relative_path,
                sweep_name,
                expression,
                target_frequency_ghz,
                threshold_db,
            ),
            next_actions=["get_s_parameters", "analyze_s_parameters"],
        )

    def _analyze_s_parameters_data(
        self,
        setup_name: str,
        sweep_name: str | None,
        expression: str,
        target_frequency_ghz: float | None,
        threshold_db: float,
    ) -> dict[str, Any]:
        raw = self.backend.get_s_parameters(setup_name, sweep_name, expression)
        try:
            analysis = analyze_s_parameter_points(
                raw.get("sample_points", []),
                target_frequency_ghz=target_frequency_ghz,
                threshold_db=threshold_db,
            )
        except ValueError as exc:
            raise InputValidationError(str(exc)) from exc
        return {**raw, "analysis": analysis}

    def _analyze_input_impedance_data(
        self,
        setup_name: str,
        sweep_name: str | None,
        expression: str,
        target_frequency_ghz: float | None,
    ) -> dict[str, Any]:
        raw = self.backend.get_s_parameters(setup_name, sweep_name, expression)
        try:
            analysis = analyze_input_impedance(
                raw.get("sample_points", []),
                target_frequency_ghz=target_frequency_ghz,
            )
        except ValueError as exc:
            raise InputValidationError(str(exc)) from exc
        return {**raw, "analysis": analysis}

    def _export_result_report_data(
        self,
        setup_name: str,
        relative_path: str,
        sweep_name: str | None,
        expression: str,
        target_frequency_ghz: float | None,
        threshold_db: float,
    ) -> dict[str, Any]:
        raw = self.backend.get_s_parameters(setup_name, sweep_name, expression)
        try:
            analysis = analyze_s_parameter_points(
                raw.get("sample_points", []),
                target_frequency_ghz=target_frequency_ghz,
                threshold_db=threshold_db,
            )
            payload = build_result_report(raw, analysis)
            report_path = self._safe_output_path(relative_path)
            report = write_result_report(report_path, payload)
        except ValueError as exc:
            raise InputValidationError(str(exc)) from exc
        return {"report": report, "path": str(report_path), "analysis": analysis}

    def export_touchstone(self, relative_path: str = "touchstone/result.s1p") -> dict[str, Any]:
        return self._call(
            "Touchstone file exported.",
            lambda: self.backend.export_touchstone(self._safe_output_path(relative_path)),
            next_actions=["get_s_parameters"],
        )

    def _safe_output_path(self, relative_path: str) -> Path:
        _require_non_empty("relative_path", relative_path)
        root = self._workspace_root()
        candidate = (root / relative_path).resolve()
        if root != candidate and root not in candidate.parents:
            raise InputValidationError("relative_path must stay inside HFSS_AGENT_OUTPUT_ROOT.")
        return candidate

    def _run_automation(
        self,
        script_id: str,
        runner: str,
        operation: str,
        port: int | None,
        project_path: str | None,
        relative_output: str | None,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        _require_non_empty("script_id", script_id)
        _require_non_empty("runner", runner)
        _require_non_empty("operation", operation)
        if runner not in {"native", "pyaedt", "com"}:
            raise InputValidationError("runner must be one of: native, pyaedt, com.")
        if operation not in {"script", "batch_solve"}:
            raise InputValidationError("operation must be one of: script, batch_solve.")
        if operation == "batch_solve" and runner != "native":
            raise InputValidationError("batch_solve currently requires the native runner.")
        if port is not None:
            _require_positive("port", port)
        if operation == "batch_solve" and not project_path:
            raise InputValidationError("project_path is required for batch_solve.")
        definition = self.script_registry.require(script_id)
        output_path = self._safe_output_path(relative_output or f"scripts/{script_id}.json")
        executable = self.config.aedt_executable
        if runner == "pyaedt":
            if port is None:
                raise InputValidationError("port is required for the pyaedt runner.")
            pyaedt_executable = self._find_pyaedt_cli()
            if pyaedt_executable is None:
                raise InputValidationError(
                    "PyAEDT CLI was not found. Install ansys-aedt-core or configure the server virtual environment."
                )
            return CliRunner(
                pyaedt_executable,
                self._workspace_root(),
                self.config.cli_timeout_seconds,
            ).run_pyaedt(
                definition,
                arguments,
                port,
                registry=self.script_registry,
                output_path=output_path,
                student_version=self._is_student_aedt_configured(),
                student_bridge=self.script_registry.root / "pyaedt_student_bridge.py",
            )
        if runner == "native":
            if executable is None or not executable.is_file():
                raise InputValidationError(
                    "AEDT executable is not configured. Set HFSS_AGENT_AEDT_EXECUTABLE."
                )
            workspace_root = self._workspace_root()
            cli = CliRunner(executable, workspace_root, self.config.cli_timeout_seconds)
            if operation == "batch_solve":
                project = Path(project_path or "").expanduser().resolve()
                if workspace_root not in project.parents and project != workspace_root:
                    raise InputValidationError(
                        "project_path must stay inside HFSS_AGENT_OUTPUT_ROOT."
                    )
                return cli.run_batch_solve(project)
            return cli.run_native(
                definition,
                arguments,
                registry=self.script_registry,
                output_path=output_path,
            )
        desktop = self.com_adapter.connect()
        return self.com_adapter.run(
            desktop,
            definition,
            arguments,
            registry=self.script_registry,
            output_path=output_path,
            log_root=self._workspace_root(),
        )

    @staticmethod
    def _find_pyaedt_cli() -> Path | None:
        candidates = [Path(sys.executable).with_name("pyaedt.exe"), Path(sys.executable).with_name("pyaedt")]
        found = shutil.which("pyaedt")
        if found:
            candidates.append(Path(found))
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        return None

    def _environment_data(self) -> dict[str, Any]:
        return collect_environment(self.config, self.backend.health())

    def _workspace_root(self) -> Path:
        return self.security.workspace_root()

    def _project_policy(self) -> ProjectPathPolicy:
        return ProjectPathPolicy(self._workspace_root() / "projects")

    def _owner(self) -> str | None:
        identity = current_identity()
        return identity.owner if identity is not None else None

    def _owned_sessions(self) -> list[Any]:
        owner = self._owner()
        if owner is None:
            return self.sessions.list()
        return [record for record in self.sessions.list() if record.owner in {None, owner}]

    def _owned_active_session_id(self) -> str | None:
        session_id = self.sessions.active_session_id
        if session_id is None:
            return None
        try:
            self._require_owned_session(session_id)
        except HfssAgentError:
            return None
        return session_id

    def _require_owned_session(self, session_id: str) -> Any:
        record = self.sessions.require(session_id)
        owner = self._owner()
        if owner is not None and record.owner not in {None, owner}:
            raise SessionError(f"Session {session_id!r} belongs to another owner.")
        return record

    def _is_student_aedt_configured(self) -> bool:
        executable = self.config.aedt_executable
        return bool(executable and "ansysedtsv" in executable.name.lower())

    def _desktop_version_from_configured_aedt(self) -> str | None:
        executable = self.config.aedt_executable
        if executable is None:
            return None
        for part in executable.parts:
            match = re.fullmatch(r"v?(\d{3})", part.lower())
            if match:
                suffix = match.group(1)
                return f"20{suffix[:2]}.{suffix[2]}"
        return None

    def _connect_session(self, spec: ConnectionSpec) -> dict[str, Any]:
        identity = current_identity()
        identity_owner = identity.owner if identity is not None else None
        if identity_owner is not None and spec.owner != identity_owner:
            from dataclasses import replace

            spec = replace(spec, owner=identity_owner)
        if spec.session_id:
            self._require_owned_session(spec.session_id)
        record = self.sessions.begin_connect(spec)
        try:
            project = self.backend.connect(spec)
        except HfssAgentError as exc:
            self.sessions.mark_failed(record.session_id, str(exc))
            raise
        except Exception as exc:
            message = f"HFSS backend connection failed: {exc}"
            self.sessions.mark_failed(record.session_id, message)
            raise SessionError(message) from exc
        record = self.sessions.mark_connected(record.session_id, spec)
        return {"session": record.to_dict(), "project": project}

    def _release_connection(
        self,
        session_id: str,
        *,
        save_project: bool,
        close_desktop: bool,
    ) -> dict[str, Any]:
        record = self._require_owned_session(session_id)
        running_jobs = self.jobs.running(owner=self._owner())
        if running_jobs:
            raise SessionError(
                "Cannot release the HFSS connection while a simulation is running. "
                "Poll get_simulation_job until every job is completed or failed."
            )
        release_result: dict[str, Any] | None = None
        if self.sessions.active_session_id == record.session_id:
            release_result = self.backend.disconnect(
                save_project=save_project,
                close_projects=close_desktop,
                close_desktop=close_desktop,
            )
        released = self.sessions.release(record.session_id)
        return {
            "session": released.to_dict(),
            "release": release_result
            or {
                "save_project": save_project,
                "close_projects": close_desktop,
                "close_desktop": close_desktop,
                "connected": False,
                "note": "Session record was not the active backend connection.",
            },
        }

    def _active_session_data(self) -> dict[str, Any] | None:
        session_id = self._owned_active_session_id()
        if not session_id:
            return None
        try:
            return self.sessions.require(session_id).to_dict()
        except HfssAgentError:
            return None

    def _create_project(self, project_name: str, relative_path: str | None) -> dict[str, Any]:
        _require_non_empty("project_name", project_name)
        policy = self._project_policy()
        project_path = (
            policy.resolve_relative(relative_path)
            if relative_path is not None
            else policy.default_project_path(project_name)
        )
        return self.backend.create_project(
            ProjectSpec(
                project_name=project_name,
                project_path=str(project_path),
            )
        )

    def _run_simulation_job(self, setup_name: str) -> dict[str, Any]:
        owner = self._owner()
        job = self.jobs.create(setup_name, owner=owner)
        self.jobs.start(job.job_id, "Simulation job accepted by MCP service.", owner=owner)
        validation = self.backend.validate_design()
        validation_failure = _validation_failure_reason(validation)
        if validation_failure:
            failed = self.jobs.fail(job.job_id, validation_failure, owner=owner)
            return {
                "setup_name": setup_name,
                "status": "failed",
                "failure_reason": validation_failure,
                "validation": validation,
                "job": failed.to_dict(),
            }
        self._simulation_executor.submit(
            self._complete_simulation_job,
            job.job_id,
            setup_name,
            owner,
        )
        return {
            "setup_name": setup_name,
            "status": "running",
            "validation": validation,
            "job": self.jobs.snapshot(job.job_id, owner=owner),
            "backend_note": (
                "Real HFSS solver execution was submitted. Poll get_simulation_job; "
                "the job remains attached to the MCP service if this request disconnects."
            ),
        }

    def _complete_simulation_job(self, job_id: str, setup_name: str, owner: str | None) -> None:
        try:
            result = self.backend.run_simulation(setup_name)
        except HfssAgentError as exc:
            failure = {"status": "failed", "error": str(exc), **exc.details}
            self.jobs.fail(job_id, str(exc), owner=owner, result=failure)
            return
        except BaseException as exc:
            failure = {"status": "failed", "error": str(exc)}
            self.jobs.fail(job_id, str(exc), owner=owner, result=failure)
            return
        if result.get("status") == "failed":
            self.jobs.fail(
                job_id,
                str(result.get("failure_reason") or "Backend reported simulation failure."),
                owner=owner,
                result=result,
            )
            return
        self.jobs.complete(
            job_id,
            result,
            result.get("backend_note", "Backend solve finished."),
            owner=owner,
        )

    def _call(
        self,
        message: str,
        operation: Callable[[], dict[str, Any]],
        next_actions: list[str] | None = None,
    ) -> dict[str, Any]:
        try:
            return self._ok(message, operation(), next_actions=next_actions)
        except (HfssAgentError, ValueError, RuntimeError, OSError) as exc:
            return self._error_response(
                exc,
                next_actions=["health_check", "get_project_info"],
            )

    def _run_validated_backend_simulation(self, setup_name: str) -> dict[str, Any]:
        validation = self.backend.validate_design()
        validation_failure = _validation_failure_reason(validation)
        if validation_failure:
            raise BackendUnavailableError(
                f"HFSS validation failed before simulation: {validation_failure}",
                details={"validation": validation},
            )
        return self.backend.run_simulation(setup_name)

    def _error_response(
        self,
        exc: BaseException,
        *,
        data: dict[str, Any] | None = None,
        next_actions: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = dict(data or {})
        payload.setdefault("error_type", exc.__class__.__name__)
        details = getattr(exc, "details", None)
        if isinstance(details, dict) and details:
            payload["details"] = details
            for key in ("hfss_messages", "validation", "worker_traceback"):
                if key in details:
                    payload[key] = details[key]
        return ToolResponse(
            status="error",
            message=str(exc),
            data=payload,
            next_actions=next_actions or ["health_check", "get_project_info"],
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


def _require_vector(field_name: str, value: list[float], length: int) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise InputValidationError(f"{field_name} must contain exactly {length} numeric values.")
    try:
        return tuple(float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise InputValidationError(f"{field_name} must contain only numeric values.") from exc


def _require_object_names(object_names: list[str]) -> tuple[str, ...]:
    if not isinstance(object_names, (list, tuple)) or not object_names:
        raise InputValidationError("object_names must contain at least one object name.")
    normalized: list[str] = []
    for index, object_name in enumerate(object_names):
        _require_non_empty(f"object_names[{index}]", object_name)
        normalized.append(object_name)
    return tuple(normalized)


def _require_positive(field_name: str, value: float) -> None:
    if value <= 0:
        raise InputValidationError(f"{field_name} must be positive.")


def _validation_failure_reason(validation: dict[str, Any]) -> str | None:
    if validation.get("valid", False):
        if _validation_has_execution_evidence(validation):
            return None
        return "HFSS validation failed before simulation: validation did not include execution evidence."
    messages: list[str] = []
    for key in ("errors", "warnings", "messages"):
        for item in validation.get(key, []) or []:
            text = str(item).strip()
            if text and text not in messages:
                messages.append(text)
    if not messages:
        messages.append("HFSS validation returned valid=false.")
    return "HFSS validation failed before simulation: " + " | ".join(messages)


def _validation_has_execution_evidence(validation: dict[str, Any]) -> bool:
    for key in ("api", "checked_by", "validation_backend", "raw_result"):
        value = validation.get(key)
        if value:
            return True
    return bool(validation.get("messages"))
