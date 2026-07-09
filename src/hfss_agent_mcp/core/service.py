from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from hfss_agent_mcp.backends.base import HfssBackend
from hfss_agent_mcp.config import ServerConfig
from hfss_agent_mcp.core.environment import collect_environment
from hfss_agent_mcp.core.errors import HfssAgentError, InputValidationError, SessionError
from hfss_agent_mcp.core.jobs import JobManager
from hfss_agent_mcp.core.models import (
    ConnectionSpec,
    DesignSpec,
    PatchAntennaSpec,
    ProjectSpec,
    SessionLaunchSpec,
    SetupSpec,
    SweepSpec,
    ToolResponse,
)
from hfss_agent_mcp.core.project import ProjectPathPolicy
from hfss_agent_mcp.core.session import SessionManager


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
        self.jobs = JobManager()

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
        non_graphical: bool = True,
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
        except HfssAgentError as exc:
            session = self._active_session_data()
            data: dict[str, Any] = {"error_type": exc.__class__.__name__}
            if session:
                data["session"] = session
            return ToolResponse(
                status="error",
                message=str(exc),
                data=data,
                next_actions=["get_session_info", "env_check", "connect_hfss"],
            ).to_dict()

    def list_aedt_sessions(self) -> dict[str, Any]:
        return self._call(
            "AEDT session records retrieved.",
            lambda: {
                "count": len(self.sessions.list()),
                "active_session_id": self.sessions.active_session_id,
                "sessions": [record.to_dict() for record in self.sessions.list()],
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
        non_graphical: bool = True,
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
            lambda: {"session": self.sessions.require(session_id).to_dict()},
            next_actions=["connect_hfss", "release_connection"],
        )

    def release_connection(self, session_id: str) -> dict[str, Any]:
        _require_non_empty("session_id", session_id)
        return self._call(
            "AEDT session record released.",
            lambda: {"session": self.sessions.release(session_id).to_dict()},
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
            lambda: self.backend.open_project(self.project_paths.resolve_relative(relative_path)),
            next_actions=["get_project_info", "create_hfss_design", "set_active_design"],
        )

    def save_project(self, relative_path: str | None = None) -> dict[str, Any]:
        return self._call(
            "HFSS project saved.",
            lambda: self.backend.save_project(
                self.project_paths.resolve_relative(relative_path)
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
            next_actions=["set_active_design", "create_patch_antenna", "create_simulation_setup"],
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

    def run_simulation(self, setup_name: str, wait_for_completion: bool = True) -> dict[str, Any]:
        _require_non_empty("setup_name", setup_name)
        return self._call(
            "Simulation job started.",
            lambda: self._run_simulation_job(setup_name, wait_for_completion),
            next_actions=["get_simulation_job", "get_s_parameters", "export_touchstone"],
        )

    def get_simulation_job(self, job_id: str) -> dict[str, Any]:
        _require_non_empty("job_id", job_id)
        return self._call(
            "Simulation job retrieved.",
            lambda: {"job": self.jobs.require(job_id).to_dict()},
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

    def _environment_data(self) -> dict[str, Any]:
        return collect_environment(self.config, self.backend.health())

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

    def _active_session_data(self) -> dict[str, Any] | None:
        session_id = self.sessions.active_session_id
        if not session_id:
            return None
        try:
            return self.sessions.require(session_id).to_dict()
        except HfssAgentError:
            return None

    def _create_project(self, project_name: str, relative_path: str | None) -> dict[str, Any]:
        _require_non_empty("project_name", project_name)
        project_path = (
            self.project_paths.resolve_relative(relative_path)
            if relative_path is not None
            else self.project_paths.default_project_path(project_name)
        )
        return self.backend.create_project(
            ProjectSpec(
                project_name=project_name,
                project_path=str(project_path),
            )
        )

    def _run_simulation_job(self, setup_name: str, wait_for_completion: bool) -> dict[str, Any]:
        job = self.jobs.create(setup_name)
        self.jobs.start(job.job_id, "Simulation job accepted by MCP service.")
        if not wait_for_completion:
            return {
                "job": job.to_dict(),
                "status": job.status,
                "backend_note": "Job is tracked by MCP service; backend solve has not been awaited.",
            }

        try:
            result = self.backend.run_simulation(setup_name)
        except HfssAgentError as exc:
            self.jobs.fail(job.job_id, str(exc))
            raise
        if result.get("status") == "failed":
            failed = self.jobs.fail(
                job.job_id,
                str(result.get("failure_reason") or "Backend reported simulation failure."),
            )
            data = dict(result)
            data["job"] = failed.to_dict()
            data["status"] = "failed"
            return data
        completed = self.jobs.complete(
            job.job_id,
            result,
            result.get("backend_note", "Backend solve finished."),
        )
        data = dict(result)
        data["job"] = completed.to_dict()
        data["status"] = completed.status if result.get("status") == "completed" else result.get("status", completed.status)
        return data

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
