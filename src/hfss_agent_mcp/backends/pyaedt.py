from __future__ import annotations

from pathlib import Path
from typing import Any

from hfss_agent_mcp.core.errors import BackendUnavailableError
from hfss_agent_mcp.core.models import (
    ConnectionSpec,
    DesignSpec,
    PatchAntennaSpec,
    ProjectSpec,
    SetupSpec,
)


class PyAedtBackend:
    name = "pyaedt"

    def __init__(self) -> None:
        self._hfss: Any | None = None

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
        Hfss = self._load_hfss_class()
        kwargs: dict[str, Any] = {
            "new_desktop": spec.new_desktop,
            "non_graphical": spec.non_graphical,
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
        self._hfss = Hfss(**kwargs)
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
        raise BackendUnavailableError(
            "PyAEDT patch antenna workflow is not implemented in this skeleton yet. "
            "Use the mock backend for offline tests, or add the workflow in backends/pyaedt.py."
        )

    def create_setup(self, spec: SetupSpec) -> dict[str, Any]:
        self._require_connection()
        setup = self._hfss.create_setup(name=spec.setup_name)
        setup.props["Frequency"] = f"{spec.frequency_ghz}GHz"
        self._hfss.create_linear_count_sweep(
            setup=spec.setup_name,
            units="GHz",
            start_frequency=spec.sweep_start_ghz,
            stop_frequency=spec.sweep_stop_ghz,
            num_of_freq_points=spec.sweep_points,
            name=spec.sweep_name,
        )
        return {
            "setup_name": spec.setup_name,
            "frequency_ghz": spec.frequency_ghz,
            "sweep_name": spec.sweep_name,
        }

    def validate_design(self) -> dict[str, Any]:
        self._require_connection()
        result = self._hfss.validate_design()
        return {"valid": bool(result), "raw_result": str(result)}

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


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if callable(value):
        value = value()
    if isinstance(value, (list, tuple, set)):
        return sorted(str(item) for item in value)
    return [str(value)]
