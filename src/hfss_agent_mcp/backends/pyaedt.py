from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, replace
import inspect
from math import isfinite
import multiprocessing as mp
from multiprocessing.connection import Connection
import os
import queue
import re
import subprocess
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from hfss_agent_mcp.core.errors import BackendStateError, BackendUnavailableError, SessionError
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
    SetupSpec,
    SheetSpec,
    SweepSpec,
)
from hfss_agent_mcp.core.simulation import setup_to_dict, sweep_to_dict
from hfss_agent_mcp.workflows.patch import build_patch_antenna
from hfss_agent_mcp.workflows.dipole import build_dipole_antenna


_PYAEDT_STUDENT_GRPC_PATCH_LOCK = threading.RLock()
_DEFAULT_WORKER_COMMAND_TIMEOUT_SECONDS = 300.0
_WORKER_SHUTDOWN_TIMEOUT_SECONDS = 5.0


class PyAedtBackend:
    name = "pyaedt"

    def __init__(self, *, use_process_worker: bool = True) -> None:
        self._use_process_worker = use_process_worker
        self._worker: _PyAedtWorkerClient | None = None
        self._hfss: Any | None = None
        self._student_version = False
        self._non_graphical = False
        self._simulation_poll_interval_seconds = 2.0

    def health(self) -> dict[str, Any]:
        try:
            self._load_hfss_class()
            available = True
            error = None
        except BackendUnavailableError as exc:
            available = False
            error = str(exc)
        connected = self._hfss is not None
        if self._use_process_worker and self._worker is not None:
            connected = self._worker.is_alive
        return {
            "backend": self.name,
            "connected": connected,
            "hfss_available": available,
            "error": error,
        }

    def connect(self, spec: ConnectionSpec) -> dict[str, Any]:
        self._student_version = spec.student_version
        self._non_graphical = spec.non_graphical
        if self._use_process_worker:
            return self._call_worker(
                "connect",
                {"spec": asdict(spec)},
                timeout_seconds=spec.connect_timeout_seconds,
            )

        self._prepare_pyaedt_environment(spec)
        Hfss = self._load_hfss_class()
        kwargs: dict[str, Any] = {
            "new_desktop": spec.new_desktop,
            "non_graphical": spec.non_graphical,
            "student_version": spec.student_version,
        }
        if spec.project_path:
            kwargs["project"] = spec.project_path
        if spec.design_name:
            kwargs["design"] = spec.design_name
        if spec.desktop_version:
            kwargs["version"] = spec.desktop_version
        if spec.machine:
            kwargs["machine"] = spec.machine
        if spec.port:
            kwargs["port"] = spec.port
        self._hfss = self._create_hfss_with_timeout(
            Hfss,
            kwargs,
            spec.connect_timeout_seconds,
            student_version=spec.student_version,
        )
        return self.get_project_info()

    def get_project_info(self) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("get_project_info", {})

        self._require_connection()
        designs = _coerce_list(
            getattr(self._hfss, "design_list", None)
            or getattr(self._hfss, "designs", None)
        )
        object_names = _coerce_list(
            getattr(getattr(self._hfss, "modeler", None), "object_names", None)
        )
        return {
            "backend": self.name,
            "connected": True,
            "project_loaded": True,
            "project_name": getattr(self._hfss, "project_name", None),
            "project_path": getattr(self._hfss, "project_file", None),
            "design_name": getattr(self._hfss, "design_name", None),
            "active_design": getattr(self._hfss, "design_name", None),
            "designs": designs,
            "solution_type": getattr(self._hfss, "solution_type", None),
            "object_count": len(object_names),
            "objects": object_names,
        }

    def create_project(self, spec: ProjectSpec) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("create_project", {"spec": asdict(spec)})

        Hfss = self._load_hfss_class()
        with _student_grpc_detection_patch(self._student_version):
            self._hfss = Hfss(
                project=spec.project_path,
                new_desktop=True,
                non_graphical=self._non_graphical,
                student_version=self._student_version,
            )
        save_project = getattr(self._hfss, "save_project", None)
        if callable(save_project):
            save_project(spec.project_path)
        return self.get_project_info()

    def open_project(self, path: Path) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("open_project", {"path": str(path)})
        return self.connect(ConnectionSpec(project_path=str(path)))

    def save_project(self, path: Path | None = None) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker(
                "save_project",
                {"path": str(path) if path is not None else None},
            )

        self._require_connection()
        save_project = getattr(self._hfss, "save_project", None)
        if not callable(save_project):
            raise BackendUnavailableError("The active PyAEDT object does not expose save_project.")
        result = save_project(str(path)) if path is not None else save_project()
        data = self.get_project_info()
        data.update({"saved": bool(result) if result is not None else True})
        return data

    def close_project(self, save: bool = False) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("close_project", {"save": save})

        self._require_connection()
        if save:
            self.save_project()
        close_project = getattr(self._hfss, "close_project", None)
        if callable(close_project):
            close_project(getattr(self._hfss, "project_name", None))
            self._hfss = None
            return {"backend": self.name, "connected": False, "project_loaded": False}
        release_desktop = getattr(self._hfss, "release_desktop", None)
        if callable(release_desktop):
            release_desktop(close_projects=True, close_desktop=False)
            self._hfss = None
            return {"backend": self.name, "connected": False, "project_loaded": False}
        raise BackendUnavailableError("The active PyAEDT object does not expose a close project API.")

    def disconnect(
        self,
        *,
        save_project: bool = True,
        close_projects: bool = True,
        close_desktop: bool = True,
    ) -> dict[str, Any]:
        if self._use_process_worker:
            result = self._call_worker(
                "disconnect",
                {
                    "save_project": save_project,
                    "close_projects": close_projects,
                    "close_desktop": close_desktop,
                },
            )
            if self._worker is not None:
                self._worker.close()
            self._worker = None
            return result

        if self._hfss is None:
            return {
                "backend": self.name,
                "connected": False,
                "saved": False,
                "save_project": save_project,
                "close_projects": close_projects,
                "close_desktop": close_desktop,
            }
        saved = False
        if save_project:
            try:
                self.save_project()
                saved = True
            except Exception as exc:
                raise BackendUnavailableError(
                    f"Unable to save project before releasing AEDT: {exc}",
                    details=self._error_details(),
                ) from exc
        release_desktop = getattr(self._hfss, "release_desktop", None)
        if not callable(release_desktop):
            raise BackendUnavailableError(
                "The active PyAEDT object does not expose release_desktop.",
                details=self._error_details(),
            )
        process_id = _aedt_process_id(self._hfss)
        try:
            release_result = _call_release_desktop(
                release_desktop,
                close_projects=close_projects,
                close_desktop=close_desktop,
            )
        except Exception as exc:
            raise BackendUnavailableError(
                f"Unable to release AEDT desktop: {exc}",
                details=self._error_details(),
            ) from exc
        self._hfss = None
        process_closed = None
        forced_termination: dict[str, Any] | None = None
        if close_desktop and process_id:
            process_closed = _wait_for_process_exit(process_id)
            if not process_closed:
                forced_termination = _terminate_process_tree(process_id)
                process_closed = _wait_for_process_exit(process_id, timeout_seconds=5.0)
                if not process_closed:
                    raise BackendUnavailableError(
                        f"AEDT process {process_id} is still running after release.",
                        details={
                            "aedt_process_id": process_id,
                            "forced_termination": forced_termination,
                        },
                    )
        return {
            "backend": self.name,
            "connected": False,
            "saved": saved,
            "release_result": bool(release_result) if release_result is not None else True,
            "save_project": save_project,
            "close_projects": close_projects,
            "close_desktop": close_desktop,
            "aedt_process_id": process_id,
            "process_closed": process_closed,
            "forced_termination": forced_termination,
        }

    def create_design(self, spec: DesignSpec) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("create_design", {"spec": asdict(spec)})

        self._require_connection()
        insert_design = getattr(self._hfss, "insert_design", None)
        if not callable(insert_design):
            raise BackendUnavailableError("The active PyAEDT object does not expose insert_design.")
        insert_design(spec.design_name, solution_type=spec.solution_type)
        return self.get_project_info()

    def set_active_design(self, design_name: str) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("set_active_design", {"design_name": design_name})

        self._require_connection()
        set_active_design = getattr(self._hfss, "set_active_design", None)
        if not callable(set_active_design):
            raise BackendUnavailableError("The active PyAEDT object does not expose set_active_design.")
        set_active_design(design_name)
        return self.get_project_info()

    def get_design_summary(self, design_name: str | None = None) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("get_design_summary", {"design_name": design_name})

        if design_name:
            self.set_active_design(design_name)
        data = self.get_project_info()
        data["setup_count"] = len(_coerce_list(getattr(self._hfss, "setup_names", None)))
        data["setups"] = _coerce_list(getattr(self._hfss, "setup_names", None))
        data.setdefault("object_details", {})
        data.setdefault("boundaries", {})
        data.setdefault("ports", {})
        data.setdefault("variables", {})
        data.setdefault(
            "warnings",
            ["PyAEDT summary includes object names; boundary and port detail extraction is limited."],
        )
        return data

    def create_model_box(self, spec: BoxSpec) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("create_model_box", {"spec": asdict(spec)})

        self._require_connection()
        primitive = {
            "name": spec.name,
            "role": spec.role,
            "kind": "box",
            "origin_mm": list(spec.origin_mm),
            "size_mm": list(spec.size_mm),
            "material": spec.material,
        }
        created = self._create_geometry_primitive(primitive)
        return {**primitive, "created_object": created}

    def create_model_sheet(self, spec: SheetSpec) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("create_model_sheet", {"spec": asdict(spec)})

        self._require_connection()
        primitive = {
            "name": spec.name,
            "role": spec.role,
            "kind": "sheet",
            "origin_mm": list(spec.origin_mm),
            "size_mm": [spec.size_mm[0], spec.size_mm[1], 0.0],
            "material": spec.material,
            "metadata": {"orientation": spec.orientation},
        }
        created = self._create_geometry_primitive(primitive)
        return {
            "name": spec.name,
            "role": spec.role,
            "kind": "sheet",
            "orientation": spec.orientation,
            "origin_mm": list(spec.origin_mm),
            "size_mm": list(spec.size_mm),
            "material": spec.material,
            "created_object": created,
        }

    def set_object_material(self, spec: MaterialAssignmentSpec) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("set_object_material", {"spec": asdict(spec)})

        self._require_connection()
        modeler = getattr(self._hfss, "modeler", None)
        if modeler is None:
            raise BackendUnavailableError("The active PyAEDT object does not expose modeler.")
        target = _modeler_object(modeler, spec.object_name)
        if target is not None:
            if hasattr(target, "material_name"):
                target.material_name = spec.material
                return {"object_name": spec.object_name, "material": spec.material}
            if hasattr(target, "material"):
                target.material = spec.material
                return {"object_name": spec.object_name, "material": spec.material}
        assign_material = getattr(self._hfss, "assign_material", None)
        if callable(assign_material):
            assign_material(spec.object_name, spec.material)
            return {"object_name": spec.object_name, "material": spec.material}
        raise BackendUnavailableError(
            f"Unable to set material for object {spec.object_name!r}.",
            details=self._error_details(),
        )

    def assign_boundary(self, spec: BoundarySpec) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("assign_boundary", {"spec": asdict(spec)})

        self._require_connection()
        boundary = {
            "name": spec.name,
            "boundary_type": spec.boundary_type,
            "objects": list(spec.object_names),
            "metadata": {"is_infinite_ground": spec.is_infinite_ground},
        }
        self._assign_boundary(boundary)
        return {
            "name": spec.name,
            "boundary_type": spec.boundary_type,
            "objects": list(spec.object_names),
            "is_infinite_ground": spec.is_infinite_ground,
        }

    def create_lumped_port(self, spec: LumpedPortSpec) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("create_lumped_port", {"spec": asdict(spec)})

        self._require_connection()
        port = {
            "name": spec.name,
            "port_type": "lumped",
            "objects": [spec.sheet_name],
            "integration_line_mm": (
                tuple(spec.integration_start_mm),
                tuple(spec.integration_end_mm),
            ),
            "impedance_ohm": spec.impedance_ohm,
        }
        self._assign_port(port)
        return {
            "name": spec.name,
            "port_type": "lumped",
            "objects": [spec.sheet_name],
            "integration_line_mm": [
                list(spec.integration_start_mm),
                list(spec.integration_end_mm),
            ],
            "impedance_ohm": spec.impedance_ohm,
        }

    def delete_model_objects(self, spec: DeleteObjectsSpec) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("delete_model_objects", {"spec": asdict(spec)})

        self._require_connection()
        modeler = getattr(self._hfss, "modeler", None)
        if modeler is None:
            raise BackendUnavailableError("The active PyAEDT object does not expose modeler.")
        before = _coerce_list(getattr(modeler, "object_names", None))
        missing = [name for name in spec.object_names if name not in before]
        if missing:
            raise BackendStateError(f"Object(s) do not exist: {', '.join(missing)}.")
        delete = getattr(modeler, "delete", None)
        if not callable(delete):
            raise BackendUnavailableError("PyAEDT modeler does not expose delete.")
        delete(list(spec.object_names))
        after = _coerce_list(getattr(modeler, "object_names", None))
        return {
            "deleted_objects": list(spec.object_names),
            "before_objects": before,
            "after_objects": after,
        }

    def create_patch_antenna(self, spec: PatchAntennaSpec) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("create_patch_antenna", {"spec": asdict(spec)})

        self._require_connection()
        recipe = build_patch_antenna(spec)
        created_objects: list[str] = []
        for primitive in recipe["geometry"]:
            created_objects.append(self._create_geometry_primitive(primitive))
        for boundary in recipe["boundaries"]:
            self._assign_boundary(boundary)
        for port in recipe["ports"]:
            self._assign_port(port)
        recipe["created_objects"] = created_objects
        return recipe

    def create_dipole_antenna(self, spec: DipoleAntennaSpec) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("create_dipole_antenna", {"spec": asdict(spec)})

        self._require_connection()
        recipe = build_dipole_antenna(spec)
        created_objects: list[str] = []
        for primitive in recipe["geometry"]:
            created_objects.append(self._create_geometry_primitive(primitive))
        for boundary in recipe["boundaries"]:
            self._assign_boundary(boundary)
        for port in recipe["ports"]:
            self._assign_port(port)
        recipe["created_objects"] = created_objects
        return recipe

    def set_design_variable(self, name: str, value: str) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker(
                "set_design_variable",
                {"name": name, "value": value},
            )
        self._require_connection()
        variable_manager = getattr(self._hfss, "variable_manager", None)
        setter = getattr(variable_manager, "set_variable", None)
        if callable(setter):
            setter(name=name, expression=value, overwrite=True)
        else:
            try:
                self._hfss[name] = value
            except Exception as exc:
                raise BackendUnavailableError(
                    "PyAEDT object does not expose a design-variable setter."
                ) from exc
        return {"name": name, "value": value}

    def create_setup(self, spec: SetupSpec) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("create_setup", {"spec": asdict(spec)})

        self._require_connection()
        setup = self._hfss.create_setup(name=spec.setup_name)
        setup.props["Frequency"] = f"{spec.frequency_ghz}GHz"
        setup.props["MaximumPasses"] = spec.max_passes
        setup.props["MinimumPasses"] = spec.min_passes
        setup.props["MaxDeltaS"] = spec.max_delta_s
        sweep = self.create_frequency_sweep(
            SweepSpec(
                setup_name=spec.setup_name,
                sweep_name=spec.sweep_name,
                sweep_start_ghz=spec.sweep_start_ghz,
                sweep_stop_ghz=spec.sweep_stop_ghz,
                sweep_points=spec.sweep_points,
                sweep_type=spec.sweep_type,
            )
        )
        data = setup_to_dict(spec)
        data["sweep"] = sweep
        return data

    def create_frequency_sweep(self, spec: SweepSpec) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("create_frequency_sweep", {"spec": asdict(spec)})

        self._require_connection()
        self._hfss.create_linear_count_sweep(
            setup=spec.setup_name,
            unit="GHz",
            start_frequency=spec.sweep_start_ghz,
            stop_frequency=spec.sweep_stop_ghz,
            num_of_freq_points=spec.sweep_points,
            name=spec.sweep_name,
            sweep_type=_pyaedt_sweep_type(spec.sweep_type),
        )
        return sweep_to_dict(spec)

    def validate_design(self) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("validate_design", {})

        self._require_connection()
        validate_full_design = getattr(self._hfss, "validate_full_design", None)
        if not callable(validate_full_design):
            raise BackendUnavailableError("The active PyAEDT object does not expose validate_full_design.")
        validation = validate_full_design()
        messages, valid = validation if isinstance(validation, tuple) and len(validation) == 2 else ([], bool(validation))
        return {
            "valid": bool(valid),
            "validation_backend": self.name,
            "api": "validate_full_design",
            "errors": [] if valid else [str(message) for message in messages],
            "warnings": [],
            "messages": [str(message) for message in messages],
            "raw_result": str(validation),
        }

    def run_simulation(self, setup_name: str) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("run_simulation", {"setup_name": setup_name}, timeout_seconds=None)

        self._require_connection()
        analyze_setup = getattr(self._hfss, "analyze_setup", None)
        if not callable(analyze_setup):
            raise BackendUnavailableError("The active PyAEDT object does not expose analyze_setup.")
        # Hfss.analyze() saves the active project before solving. Student AEDT
        # sessions can reject that save through gRPC, while AnalyzeSetup is the
        # direct AEDT operation needed by this adapter.
        initial_messages = self._collect_hfss_messages()
        try:
            started = analyze_setup(name=setup_name, blocking=False)
        except Exception as exc:
            details = self._error_details()
            raise BackendUnavailableError(
                f"HFSS solver submission failed for setup {setup_name!r}: {exc}",
                details=details,
            ) from exc
        observations, solver_errors = self._wait_until_solver_idle(initial_messages)
        observed_running = any(item["running"] for item in observations)
        messages = solver_errors or self._collect_hfss_messages()
        status_api_unavailable = bool(observations) and not observations[-1]["status_api_available"]
        if not started or solver_errors or status_api_unavailable:
            failure_reason = _hfss_failure_reason(
                messages,
                (
                    "HFSS simulation completion could not be proven because the "
                    "AEDT simulation status API is unavailable."
                    if status_api_unavailable
                    else f"HFSS solver reported failure for setup {setup_name!r}."
                ),
            )
            return {
                "setup_name": setup_name,
                "status": "failed",
                "error": failure_reason,
                "failure_reason": failure_reason,
                "hfss_messages": messages,
                "simulation_status_checks": len(observations),
                "observed_running": observed_running,
                "solver_state_observations": observations,
            }
        return {
            "setup_name": setup_name,
            "status": "completed",
            "simulation_status_checks": len(observations),
            "observed_running": observed_running,
            "solver_state_observations": observations,
        }

    def get_s_parameters(
        self,
        setup_name: str,
        sweep_name: str | None,
        expression: str,
    ) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker(
                "get_s_parameters",
                {
                    "setup_name": setup_name,
                    "sweep_name": sweep_name,
                    "expression": expression,
                },
            )

        self._require_connection()
        post = getattr(self._hfss, "post", None)
        get_solution_data = getattr(post, "get_solution_data", None)
        if not callable(get_solution_data):
            raise BackendUnavailableError("PyAEDT HFSS session does not expose post.get_solution_data.")

        setup_sweep_name = setup_name
        if sweep_name:
            setup_sweep_name = f"{setup_name} : {sweep_name}"
        solution = get_solution_data(
            expressions=expression,
            setup_sweep_name=setup_sweep_name,
            domain="Sweep",
        )
        if not solution:
            raise BackendUnavailableError(
                f"No solution data was returned for {setup_sweep_name!r} and {expression!r}."
            )
        points = _solution_data_to_points(solution, expression)
        return {
            "setup_name": setup_name,
            "sweep_name": sweep_name,
            "expression": expression,
            "solved": True,
            "sample_points": points,
        }

    def export_touchstone(self, path: Path) -> dict[str, Any]:
        if self._use_process_worker:
            return self._call_worker("export_touchstone", {"path": str(path)})

        self._require_connection()
        result = self._hfss.export_touchstone(str(path))
        return {"path": str(path), "raw_result": str(result)}

    def _require_connection(self) -> None:
        if self._hfss is None:
            raise BackendUnavailableError("PyAEDT HFSS session is not connected.")

    def _create_geometry_primitive(self, primitive: dict[str, Any]) -> str:
        modeler = getattr(self._hfss, "modeler", None)
        if modeler is None:
            raise BackendUnavailableError("The active PyAEDT object does not expose modeler.")

        name = primitive["name"]
        origin = list(primitive["origin_mm"])
        size = list(primitive["size_mm"])
        material = primitive["material"]
        if primitive["kind"] == "box":
            create_box = getattr(modeler, "create_box", None)
            if not callable(create_box):
                raise BackendUnavailableError("PyAEDT modeler does not expose create_box.")
            create_box(origin=origin, sizes=size, name=name, material=material)
            return name

        create_rectangle = getattr(modeler, "create_rectangle", None)
        if not callable(create_rectangle):
            raise BackendUnavailableError("PyAEDT modeler does not expose create_rectangle.")
        orientation = primitive.get("metadata", {}).get("orientation", "XY")
        sizes = [size[0], size[1]]
        create_rectangle(
            orientation=orientation,
            origin=origin,
            sizes=sizes,
            name=name,
            material=material,
        )
        return name

    def _assign_boundary(self, boundary: dict[str, Any]) -> None:
        if boundary["boundary_type"] in {"perfect_e", "perfecte", "perfect E", "Perfect E"}:
            assign_perfecte = getattr(self._hfss, "assign_perfecte_to_sheets", None)
            if callable(assign_perfecte):
                assign_perfecte(
                    list(boundary["objects"]),
                    boundary["name"],
                    bool(boundary.get("metadata", {}).get("is_infinite_ground", False)),
                )
                return
            raise BackendUnavailableError(
                "The active PyAEDT object does not expose assign_perfecte_to_sheets.",
                details=self._error_details(),
            )
        if boundary["boundary_type"] != "radiation":
            raise BackendUnavailableError(f"Unsupported boundary type: {boundary['boundary_type']}")
        assign_radiation = getattr(self._hfss, "assign_radiation_boundary_to_objects", None)
        if callable(assign_radiation):
            assign_radiation(list(boundary["objects"]), boundary["name"])
            return
        assign_radiation = getattr(self._hfss, "assign_radiation_boundary", None)
        if callable(assign_radiation):
            assign_radiation(list(boundary["objects"]), boundary["name"])
            return
        raise BackendUnavailableError("The active PyAEDT object does not expose a radiation boundary API.")

    def _collect_hfss_messages(self, level: int = 0) -> list[str]:
        if self._hfss is None:
            return []
        messages: list[str] = []
        logger = getattr(self._hfss, "logger", None)
        get_messages = getattr(logger, "get_messages", None)
        if callable(get_messages):
            try:
                messages.extend(str(item) for item in get_messages(level=level))
            except Exception:
                pass
        desktop = (
            getattr(self._hfss, "odesktop", None)
            or getattr(getattr(self._hfss, "desktop_class", None), "odesktop", None)
        )
        get_desktop_messages = getattr(desktop, "GetMessages", None)
        if callable(get_desktop_messages):
            project_name = getattr(self._hfss, "project_name", "") or ""
            design_name = getattr(self._hfss, "design_name", "") or ""
            for args in (("", "", level), (project_name, design_name, level)):
                try:
                    messages.extend(str(item) for item in get_desktop_messages(*args))
                except Exception:
                    pass
        deduplicated: list[str] = []
        for message in messages:
            if message and message not in deduplicated:
                deduplicated.append(message)
        return deduplicated[-20:]

    def _wait_until_solver_idle(
        self,
        initial_messages: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        observations: list[dict[str, Any]] = []
        known_messages = set(initial_messages or [])
        solver_errors: list[str] = []
        while True:
            running = self._read_simulation_running_state()
            current_messages = self._collect_hfss_messages()
            new_errors = _new_hfss_errors(current_messages, known_messages)
            for message in new_errors:
                if message not in solver_errors:
                    solver_errors.append(message)
            observation = {
                "check_index": len(observations) + 1,
                "running": bool(running) if running is not None else False,
                "status_api_available": running is not None,
                "timestamp": time.time(),
            }
            if new_errors:
                observation["hfss_messages"] = new_errors
            observations.append(observation)
            if new_errors:
                observation["hfss_messages"] = new_errors
            known_messages.update(current_messages)
            if running is None or not running:
                return observations, solver_errors
            time.sleep(self._simulation_poll_interval_seconds)

    def _read_simulation_running_state(self) -> bool | None:
        if self._hfss is None:
            return None
        candidates = [
            self._hfss,
            getattr(self._hfss, "desktop_class", None),
            getattr(self._hfss, "odesktop", None),
            getattr(getattr(self._hfss, "desktop_class", None), "odesktop", None),
        ]
        for candidate in candidates:
            if candidate is None:
                continue
            for name in ("are_there_simulations_running", "AreThereSimulationsRunning"):
                missing = object()
                value = getattr(candidate, name, missing)
                if value is missing:
                    continue
                try:
                    return bool(value() if callable(value) else value)
                except Exception:
                    continue
        return None

    def _error_details(self) -> dict[str, Any]:
        messages = self._collect_hfss_messages()
        return {"hfss_messages": messages} if messages else {}

    def _assign_port(self, port: dict[str, Any]) -> None:
        if port["port_type"] != "lumped":
            raise BackendUnavailableError(f"Unsupported port type: {port['port_type']}")
        lumped_port = getattr(self._hfss, "lumped_port", None)
        if not callable(lumped_port):
            raise BackendUnavailableError("The active PyAEDT object does not expose lumped_port.")
        start, end = port["integration_line_mm"]
        objects = list(port["objects"])
        assignment = objects[0] if len(objects) == 1 else objects
        lumped_port(
            assignment=assignment,
            integration_line=[list(start), list(end)],
            impedance=port["impedance_ohm"],
            name=port["name"],
        )

    @staticmethod
    def _load_hfss_class() -> Any:
        try:
            from ansys.aedt.core import Hfss

            return Hfss
        except Exception as first_error:
            try:
                from pyaedt import Hfss

                return Hfss
            except Exception as second_error:
                raise BackendUnavailableError(
                    "PyAEDT is not importable. Install the pyaedt extra and run on a machine "
                    "with AEDT/HFSS access. "
                    f"ansys.aedt.core error: {first_error}; pyaedt error: {second_error}"
                ) from second_error

    @staticmethod
    def _prepare_pyaedt_environment(spec: ConnectionSpec) -> None:
        if not spec.aedt_executable:
            return
        executable = Path(spec.aedt_executable)
        suffix = _version_suffix_from_executable(executable, spec.desktop_version)
        if not suffix:
            return
        root = str(executable.parent)
        student_executable = executable.name.lower() == "ansysedtsv.exe" or spec.student_version
        if student_executable:
            os.environ[f"ANSYSEMSV_ROOT{suffix}"] = root
            os.environ.pop(f"ANSYSEM_ROOT{suffix}", None)
            return
        os.environ[f"ANSYSEM_ROOT{suffix}"] = root
        os.environ.pop(f"ANSYSEMSV_ROOT{suffix}", None)

    @staticmethod
    def _create_hfss_with_timeout(
        hfss_class: Any,
        kwargs: dict[str, Any],
        timeout_seconds: float | None,
        *,
        student_version: bool = False,
    ) -> Any:
        if timeout_seconds is None:
            with _student_grpc_detection_patch(student_version):
                return hfss_class(**kwargs)

        result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)
        timed_out = threading.Event()

        def worker() -> None:
            try:
                with _student_grpc_detection_patch(student_version):
                    hfss = hfss_class(**kwargs)
            except BaseException as exc:
                _put_result(result_queue, ("error", exc))
                return
            if timed_out.is_set():
                _release_late_hfss(hfss)
                return
            _put_result(result_queue, ("ok", hfss))

        thread = threading.Thread(
            target=worker,
            name="pyaedt-hfss-connect",
            daemon=True,
        )
        thread.start()
        try:
            status, value = result_queue.get(timeout=timeout_seconds)
        except queue.Empty as exc:
            timed_out.set()
            raise SessionError(
                f"PyAEDT HFSS initialization timed out after {timeout_seconds:g} seconds."
            ) from exc
        if status == "error":
            raise BackendUnavailableError(f"PyAEDT HFSS initialization failed: {value}") from value
        return value

    def _call_worker(
        self,
        command: str,
        args: dict[str, Any],
        timeout_seconds: float | None = _DEFAULT_WORKER_COMMAND_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        if self._worker is None or not self._worker.is_alive:
            self._worker = _PyAedtWorkerClient()
        return self._worker.call(command, args, timeout_seconds=timeout_seconds)


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if callable(value):
        value = value()
    if isinstance(value, (list, tuple, set)):
        return sorted(str(item) for item in value)
    return [str(value)]


def _modeler_object(modeler: Any, object_name: str) -> Any | None:
    getter = getattr(modeler, "get_object_from_name", None)
    if callable(getter):
        try:
            return getter(object_name)
        except Exception:
            pass
    try:
        return modeler[object_name]
    except Exception:
        return None


def _version_suffix_from_executable(executable: Path, desktop_version: str | None) -> str | None:
    if desktop_version:
        parts = desktop_version.split(".")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            return f"{parts[0][-2:]}{parts[1][0]}"
    for part in executable.parts:
        match = re.fullmatch(r"v?(\d{3})", part.lower())
        if match:
            return match.group(1)
    return None


def _pyaedt_sweep_type(sweep_type: str) -> str:
    """Map the service's legacy method label to PyAEDT's accepted values."""
    if sweep_type.strip().lower() in {"linearcount", "linear_count"}:
        return "Discrete"
    return sweep_type


def _hfss_failure_reason(messages: list[str], fallback: str) -> str:
    if not messages:
        return fallback
    error_like = [
        message
        for message in messages
        if any(marker in message.lower() for marker in ("[error]", "error", "failed", "invalid"))
    ]
    selected = error_like or messages
    return " | ".join(selected[-5:])


def _new_hfss_errors(messages: list[str], known_messages: set[str]) -> list[str]:
    return [
        message
        for message in messages
        if message not in known_messages
        and any(marker in message.lower() for marker in ("[error]", "error", "failed", "invalid"))
    ]


def _aedt_process_id(hfss: Any) -> int | None:
    desktop_class = getattr(hfss, "desktop_class", None)
    process_id = getattr(desktop_class, "aedt_process_id", None)
    if process_id is None:
        return None
    try:
        return int(process_id)
    except (TypeError, ValueError):
        return None


def _call_release_desktop(
    release_desktop: Callable[..., Any],
    *,
    close_projects: bool,
    close_desktop: bool,
) -> Any:
    try:
        parameters = inspect.signature(release_desktop).parameters
    except (TypeError, ValueError):
        parameters = {}
    if "close_desktop" in parameters:
        return release_desktop(close_projects=close_projects, close_desktop=close_desktop)
    if "close_on_exit" in parameters:
        return release_desktop(close_projects=close_projects, close_on_exit=close_desktop)
    return release_desktop(close_projects, close_desktop)


def _is_process_alive(process_id: int) -> bool:
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {process_id}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout.strip()
        return result.returncode == 0 and str(process_id) in output and "No tasks" not in output
    try:
        os.kill(process_id, 0)
    except OSError:
        return False
    return True


def _wait_for_process_exit(process_id: int, *, timeout_seconds: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _is_process_alive(process_id):
            return True
        time.sleep(0.5)
    return not _is_process_alive(process_id)


def _terminate_process_tree(process_id: int) -> dict[str, Any]:
    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/PID", str(process_id), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "method": "taskkill",
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    try:
        os.kill(process_id, 15)
    except OSError as exc:
        return {"method": "sigterm", "error": str(exc)}
    return {"method": "sigterm", "returncode": 0}


def _put_result(result_queue: queue.Queue[tuple[str, Any]], result: tuple[str, Any]) -> None:
    try:
        result_queue.put_nowait(result)
    except queue.Full:
        pass


def _release_late_hfss(hfss: Any) -> None:
    release_desktop = getattr(hfss, "release_desktop", None)
    if callable(release_desktop):
        try:
            release_desktop(close_projects=False, close_desktop=False)
        except Exception:
            pass


class _PyAedtWorkerClient:
    def __init__(self) -> None:
        self._ctx = mp.get_context("spawn")
        self._parent_conn: Connection | None = None
        self._process: mp.Process | None = None
        self._lock = threading.Lock()
        self._next_request_id = 0

    @property
    def is_alive(self) -> bool:
        return bool(self._process and self._process.is_alive())

    def call(
        self,
        command: str,
        args: dict[str, Any],
        timeout_seconds: float | None = _DEFAULT_WORKER_COMMAND_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_started()
            assert self._parent_conn is not None
            request_id = self._next_request_id
            self._next_request_id += 1
            try:
                self._parent_conn.send(
                    {
                        "id": request_id,
                        "command": command,
                        "args": args,
                    }
                )
            except (BrokenPipeError, EOFError, OSError) as exc:
                self._terminate()
                raise BackendUnavailableError("PyAEDT worker process is not reachable.") from exc

            if timeout_seconds is not None and not self._parent_conn.poll(timeout_seconds):
                self._terminate()
                raise SessionError(
                    f"PyAEDT worker command '{command}' timed out after {timeout_seconds:g} seconds."
                )
            if timeout_seconds is None:
                self._parent_conn.poll(None)

            try:
                response = self._parent_conn.recv()
            except (BrokenPipeError, EOFError, OSError) as exc:
                self._terminate()
                raise BackendUnavailableError("PyAEDT worker process exited before returning a response.") from exc

            if response.get("id") != request_id:
                raise BackendUnavailableError("PyAEDT worker returned an out-of-order response.")
            if response.get("status") == "ok":
                return response["data"]
            _raise_worker_error(command, response)

    def close(self) -> None:
        with self._lock:
            if self._parent_conn is not None and self.is_alive:
                try:
                    self._parent_conn.send({"id": -1, "command": "shutdown", "args": {}})
                    self._parent_conn.poll(_WORKER_SHUTDOWN_TIMEOUT_SECONDS)
                except (BrokenPipeError, EOFError, OSError):
                    pass
            self._terminate()

    def _ensure_started(self) -> None:
        if self.is_alive and self._parent_conn is not None:
            return
        self._terminate()
        parent_conn, child_conn = self._ctx.Pipe()
        process = self._ctx.Process(
            target=_pyaedt_worker_main,
            args=(child_conn,),
            name="hfss-agent-pyaedt-worker",
            daemon=False,
        )
        process.start()
        child_conn.close()
        self._parent_conn = parent_conn
        self._process = process

    def _terminate(self) -> None:
        process = self._process
        if process is not None and process.is_alive():
            process.terminate()
            process.join(timeout=_WORKER_SHUTDOWN_TIMEOUT_SECONDS)
            if process.is_alive():
                process.kill()
                process.join(timeout=_WORKER_SHUTDOWN_TIMEOUT_SECONDS)
        if self._parent_conn is not None:
            try:
                self._parent_conn.close()
            except OSError:
                pass
        self._parent_conn = None
        self._process = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def _pyaedt_worker_main(conn: Connection) -> None:
    backend = PyAedtBackend(use_process_worker=False)
    while True:
        try:
            request = conn.recv()
        except EOFError:
            break
        request_id = request.get("id")
        command = request.get("command")
        args = request.get("args", {})
        if command == "shutdown":
            conn.send({"id": request_id, "status": "ok", "data": {"shutdown": True}})
            break
        try:
            data = _execute_worker_command(backend, command, args)
        except BaseException as exc:
            details = backend._error_details()
            conn.send(
                {
                    "id": request_id,
                    "status": "error",
                    "error_type": exc.__class__.__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                    "hfss_messages": details.get("hfss_messages", []),
                }
            )
            continue
        conn.send({"id": request_id, "status": "ok", "data": data})


def _execute_worker_command(backend: Any, command: str, args: dict[str, Any]) -> dict[str, Any]:
    if command == "connect":
        spec = replace(ConnectionSpec(**args["spec"]), connect_timeout_seconds=None)
        return backend.connect(spec)
    if command == "get_project_info":
        return backend.get_project_info()
    if command == "create_project":
        return backend.create_project(ProjectSpec(**args["spec"]))
    if command == "open_project":
        return backend.open_project(Path(args["path"]))
    if command == "save_project":
        path = args.get("path")
        return backend.save_project(Path(path) if path is not None else None)
    if command == "close_project":
        return backend.close_project(save=bool(args.get("save", False)))
    if command == "disconnect":
        return backend.disconnect(
            save_project=bool(args.get("save_project", True)),
            close_projects=bool(args.get("close_projects", True)),
            close_desktop=bool(args.get("close_desktop", True)),
        )
    if command == "create_design":
        return backend.create_design(DesignSpec(**args["spec"]))
    if command == "set_active_design":
        return backend.set_active_design(args["design_name"])
    if command == "get_design_summary":
        return backend.get_design_summary(args.get("design_name"))
    if command == "create_model_box":
        return backend.create_model_box(BoxSpec(**args["spec"]))
    if command == "create_model_sheet":
        return backend.create_model_sheet(SheetSpec(**args["spec"]))
    if command == "set_object_material":
        return backend.set_object_material(MaterialAssignmentSpec(**args["spec"]))
    if command == "assign_boundary":
        return backend.assign_boundary(BoundarySpec(**args["spec"]))
    if command == "create_lumped_port":
        return backend.create_lumped_port(LumpedPortSpec(**args["spec"]))
    if command == "delete_model_objects":
        return backend.delete_model_objects(DeleteObjectsSpec(**args["spec"]))
    if command == "create_patch_antenna":
        return backend.create_patch_antenna(PatchAntennaSpec(**args["spec"]))
    if command == "create_dipole_antenna":
        return backend.create_dipole_antenna(DipoleAntennaSpec(**args["spec"]))
    if command == "set_design_variable":
        return backend.set_design_variable(args["name"], args["value"])
    if command == "create_setup":
        return backend.create_setup(SetupSpec(**args["spec"]))
    if command == "create_frequency_sweep":
        return backend.create_frequency_sweep(SweepSpec(**args["spec"]))
    if command == "validate_design":
        return backend.validate_design()
    if command == "run_simulation":
        return backend.run_simulation(args["setup_name"])
    if command == "get_s_parameters":
        return backend.get_s_parameters(
            args["setup_name"],
            args.get("sweep_name"),
            args["expression"],
        )
    if command == "export_touchstone":
        return backend.export_touchstone(Path(args["path"]))
    raise BackendUnavailableError(f"Unsupported PyAEDT worker command: {command}")


def _solution_data_to_points(solution: Any, expression: str) -> list[dict[str, float]]:
    """Convert PyAEDT SolutionData into transport-safe frequency samples."""
    raw_frequencies = getattr(solution, "primary_sweep_values", None)
    frequencies = [] if raw_frequencies is None else list(raw_frequencies)
    if not frequencies:
        raise BackendUnavailableError("PyAEDT returned solution data without a primary frequency sweep.")

    is_db_expression = expression.strip().lower().startswith("db(")
    db_formula = "real" if is_db_expression else "db20"
    try:
        _, db_values = solution.get_expression_data(expression, formula=db_formula)
    except Exception as exc:
        raise BackendUnavailableError(
            f"Unable to extract dB values for expression {expression!r}: {exc}"
        ) from exc

    real_values: list[Any] = []
    imag_values: list[Any] = []
    try:
        _, real_values = solution.get_expression_data(expression, formula="real")
        _, imag_values = solution.get_expression_data(expression, formula="imag")
    except Exception:
        # Some AEDT report expressions are real-only; dB data remains usable.
        real_values = []
        imag_values = []

    points: list[dict[str, float]] = []
    for index, frequency in enumerate(frequencies):
        point = {
            "frequency_ghz": _finite_result_number(
                _frequency_to_ghz(frequency), "frequency_ghz", index
            ),
            "value_db": _finite_result_number(db_values[index], "value_db", index),
        }
        if index < len(real_values) and index < len(imag_values):
            real = _finite_result_number(real_values[index], "real", index)
            imag = _finite_result_number(imag_values[index], "imag", index)
            point["real"] = real
            point["imag"] = imag
            if expression.strip().lower().startswith("z("):
                point["real_ohms"] = real
                point["imag_ohms"] = imag
        points.append(point)
    return points


def _finite_result_number(value: Any, field_name: str, index: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise BackendUnavailableError(
            f"PyAEDT returned non-numeric {field_name} at sample index {index}."
        ) from exc
    if not isfinite(number):
        raise BackendUnavailableError(
            f"PyAEDT returned non-finite {field_name} at sample index {index}."
        )
    return number


def _frequency_to_ghz(value: Any) -> float:
    text = str(value).strip()
    units = (("ghz", 1.0), ("mhz", 1e-3), ("khz", 1e-6), ("hz", 1e-9))
    lowered = text.lower()
    for suffix, scale in units:
        if lowered.endswith(suffix):
            return float(lowered[: -len(suffix)].strip()) * scale
    return float(value)


def _raise_worker_error(command: str, response: dict[str, Any]) -> None:
    message = response.get("message") or f"PyAEDT worker command '{command}' failed."
    error_type = response.get("error_type")
    details: dict[str, Any] = {}
    if response.get("hfss_messages"):
        details["hfss_messages"] = list(response["hfss_messages"])
    if response.get("traceback"):
        details["worker_traceback"] = response["traceback"]
    if error_type == "SessionError":
        raise SessionError(message, details=details)
    if error_type in {"BackendUnavailableError", "InputValidationError"}:
        raise BackendUnavailableError(message, details=details)
    raise BackendUnavailableError(
        f"PyAEDT worker command '{command}' failed: {message}",
        details=details,
    )


@contextmanager
def _student_grpc_detection_patch(
    enabled: bool,
    *,
    desktop_module: Any | None = None,
    active_sessions: Callable[..., dict[int, int]] | None = None,
) -> Iterator[None]:
    """Let PyAEDT's launch wait see Student AEDT gRPC ports on Windows."""
    if not enabled:
        yield
        return

    if desktop_module is None or active_sessions is None:
        try:
            import ansys.aedt.core.desktop as desktop_module
            from ansys.aedt.core.generic.general_methods import active_sessions
        except Exception:
            yield
            return

    original_detector = getattr(desktop_module, "is_grpc_session_active", None)
    if not callable(original_detector):
        yield
        return

    def student_aware_detector(port: int, machine: str | None = None) -> bool:
        if original_detector(port, machine):
            return True
        try:
            student_sessions = active_sessions(student_version=True, non_graphical=None)
        except Exception:
            return False
        return port in student_sessions.values()

    with _PYAEDT_STUDENT_GRPC_PATCH_LOCK:
        desktop_module.is_grpc_session_active = student_aware_detector
        try:
            yield
        finally:
            desktop_module.is_grpc_session_active = original_detector
