from __future__ import annotations

import os
import queue
import re
import threading
from pathlib import Path
from typing import Any

from hfss_agent_mcp.core.errors import BackendUnavailableError, SessionError
from hfss_agent_mcp.core.models import (
    ConnectionSpec,
    DesignSpec,
    PatchAntennaSpec,
    ProjectSpec,
    SetupSpec,
    SweepSpec,
)
from hfss_agent_mcp.core.simulation import setup_to_dict, sweep_to_dict
from hfss_agent_mcp.workflows.patch import build_patch_antenna


class PyAedtBackend:
    name = "pyaedt"

    def __init__(self) -> None:
        self._hfss: Any | None = None
        self._student_version = False

    def health(self) -> dict[str, Any]:
        try:
            self._load_hfss_class()
            available = True
            error = None
        except BackendUnavailableError as exc:
            available = False
            error = str(exc)
        return {
            "backend": self.name,
            "connected": self._hfss is not None,
            "hfss_available": available,
            "error": error,
        }

    def connect(self, spec: ConnectionSpec) -> dict[str, Any]:
        self._prepare_pyaedt_environment(spec)
        Hfss = self._load_hfss_class()
        kwargs: dict[str, Any] = {
            "new_desktop": spec.new_desktop,
            "non_graphical": spec.non_graphical,
            "student_version": spec.student_version,
        }
        self._student_version = spec.student_version
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
        )
        return self.get_project_info()

    def get_project_info(self) -> dict[str, Any]:
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
        Hfss = self._load_hfss_class()
        self._hfss = Hfss(
            project=spec.project_path,
            new_desktop=True,
            non_graphical=True,
            student_version=self._student_version,
        )
        save_project = getattr(self._hfss, "save_project", None)
        if callable(save_project):
            save_project(spec.project_path)
        return self.get_project_info()

    def open_project(self, path: Path) -> dict[str, Any]:
        return self.connect(ConnectionSpec(project_path=str(path)))

    def save_project(self, path: Path | None = None) -> dict[str, Any]:
        self._require_connection()
        save_project = getattr(self._hfss, "save_project", None)
        if not callable(save_project):
            raise BackendUnavailableError("The active PyAEDT object does not expose save_project.")
        result = save_project(str(path)) if path is not None else save_project()
        data = self.get_project_info()
        data.update({"saved": bool(result) if result is not None else True})
        return data

    def close_project(self, save: bool = False) -> dict[str, Any]:
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

    def create_design(self, spec: DesignSpec) -> dict[str, Any]:
        self._require_connection()
        insert_design = getattr(self._hfss, "insert_design", None)
        if not callable(insert_design):
            raise BackendUnavailableError("The active PyAEDT object does not expose insert_design.")
        insert_design(spec.design_name, solution_type=spec.solution_type)
        return self.get_project_info()

    def set_active_design(self, design_name: str) -> dict[str, Any]:
        self._require_connection()
        set_active_design = getattr(self._hfss, "set_active_design", None)
        if not callable(set_active_design):
            raise BackendUnavailableError("The active PyAEDT object does not expose set_active_design.")
        set_active_design(design_name)
        return self.get_project_info()

    def get_design_summary(self, design_name: str | None = None) -> dict[str, Any]:
        if design_name:
            self.set_active_design(design_name)
        data = self.get_project_info()
        data["setup_count"] = len(_coerce_list(getattr(self._hfss, "setup_names", None)))
        data["setups"] = _coerce_list(getattr(self._hfss, "setup_names", None))
        return data

    def create_patch_antenna(self, spec: PatchAntennaSpec) -> dict[str, Any]:
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

    def create_setup(self, spec: SetupSpec) -> dict[str, Any]:
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
        self._require_connection()
        self._hfss.create_linear_count_sweep(
            setup=spec.setup_name,
            units="GHz",
            start_frequency=spec.sweep_start_ghz,
            stop_frequency=spec.sweep_stop_ghz,
            num_of_freq_points=spec.sweep_points,
            name=spec.sweep_name,
            sweep_type=spec.sweep_type,
        )
        return sweep_to_dict(spec)

    def validate_design(self) -> dict[str, Any]:
        self._require_connection()
        result = self._hfss.validate_design()
        valid = bool(result)
        return {
            "valid": valid,
            "errors": [] if valid else [str(result)],
            "warnings": [],
            "raw_result": str(result),
        }

    def run_simulation(self, setup_name: str) -> dict[str, Any]:
        self._require_connection()
        result = self._hfss.analyze(setup=setup_name)
        return {"setup_name": setup_name, "status": "completed" if result else "failed"}

    def get_s_parameters(
        self,
        setup_name: str,
        sweep_name: str | None,
        expression: str,
    ) -> dict[str, Any]:
        raise BackendUnavailableError(
            "PyAEDT S-parameter extraction will be implemented after the first real HFSS smoke test."
        )

    def export_touchstone(self, path: Path) -> dict[str, Any]:
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
        create_rectangle(
            orientation="XY",
            origin=origin,
            sizes=[size[0], size[1]],
            name=name,
            material=material,
        )
        return name

    def _assign_boundary(self, boundary: dict[str, Any]) -> None:
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

    def _assign_port(self, port: dict[str, Any]) -> None:
        if port["port_type"] != "lumped":
            raise BackendUnavailableError(f"Unsupported port type: {port['port_type']}")
        lumped_port = getattr(self._hfss, "lumped_port", None)
        if not callable(lumped_port):
            raise BackendUnavailableError("The active PyAEDT object does not expose lumped_port.")
        start, end = port["integration_line_mm"]
        lumped_port(
            assignment=list(port["objects"]),
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
    ) -> Any:
        if timeout_seconds is None:
            return hfss_class(**kwargs)

        result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)
        timed_out = threading.Event()

        def worker() -> None:
            try:
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


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if callable(value):
        value = value()
    if isinstance(value, (list, tuple, set)):
        return sorted(str(item) for item in value)
    return [str(value)]


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
