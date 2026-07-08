from __future__ import annotations

from pathlib import Path
from typing import Any

from hfss_agent_mcp.core.errors import BackendUnavailableError
from hfss_agent_mcp.core.models import (
    ConnectionSpec,
    DesignSpec,
    PatchAntennaSpec,
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
        return {
            "backend": self.name,
            "connected": True,
            "project_name": getattr(self._hfss, "project_name", None),
            "design_name": getattr(self._hfss, "design_name", None),
            "solution_type": getattr(self._hfss, "solution_type", None),
        }

    def create_design(self, spec: DesignSpec) -> dict[str, Any]:
        self._require_connection()
        insert_design = getattr(self._hfss, "insert_design", None)
        if not callable(insert_design):
            raise BackendUnavailableError("The active PyAEDT object does not expose insert_design.")
        insert_design(spec.design_name, solution_type=spec.solution_type)
        return self.get_project_info()

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
