from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from hfss_agent_mcp.core.errors import BackendStateError
from hfss_agent_mcp.core.models import (
    ConnectionSpec,
    DesignSpec,
    DipoleAntennaSpec,
    PatchAntennaSpec,
    ProjectSpec,
    SetupSpec,
    SweepSpec,
)
from hfss_agent_mcp.core.simulation import setup_to_dict, sweep_to_dict
from hfss_agent_mcp.workflows.patch import build_patch_antenna
from hfss_agent_mcp.workflows.dipole import build_dipole_antenna


class MockHfssBackend:
    name = "mock"

    def __init__(self) -> None:
        self.connected = False
        self.project_name: str | None = "MockProject"
        self.project_path: str | None = None
        self.design_name: str | None = None
        self.solution_type = "DrivenModal"
        self.designs: dict[str, dict[str, Any]] = {}

    def health(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "connected": self.connected,
            "hfss_available": False,
            "mode": "offline-simulation",
        }

    def connect(self, spec: ConnectionSpec) -> dict[str, Any]:
        self.connected = True
        if spec.project_path:
            self.project_path = spec.project_path
            self.project_name = Path(spec.project_path).stem
        if spec.design_name:
            self._ensure_design(spec.design_name, spec.solution_type)
        self.solution_type = spec.solution_type
        return self.get_project_info()

    def get_project_info(self) -> dict[str, Any]:
        active_state = self.designs.get(self.design_name or "")
        return {
            "backend": self.name,
            "connected": self.connected,
            "project_loaded": self.project_name is not None,
            "project_name": self.project_name,
            "project_path": self.project_path,
            "design_name": self.design_name,
            "active_design": self.design_name,
            "designs": sorted(self.designs),
            "solution_type": self.solution_type,
            "object_count": len(active_state["objects"]) if active_state else 0,
            "objects": sorted(active_state["objects"]) if active_state else [],
            "setups": sorted(active_state["setups"]) if active_state else [],
            "solved_setups": sorted(active_state["solved_setups"]) if active_state else [],
        }

    def create_project(self, spec: ProjectSpec) -> dict[str, Any]:
        self._require_connection()
        self.project_name = spec.project_name
        self.project_path = spec.project_path
        self.design_name = None
        self.solution_type = "DrivenModal"
        self.designs = {}
        return self.get_project_info()

    def open_project(self, path: Path) -> dict[str, Any]:
        self._require_connection()
        self.project_path = str(path)
        self.project_name = path.stem
        self.design_name = None
        self.designs = {}

        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
            self.project_name = data.get("project_name", self.project_name)
            self.design_name = data.get("active_design")
            self.designs = {
                name: _restore_design_state(state)
                for name, state in data.get("designs", {}).items()
            }
            if self.design_name and self.design_name in self.designs:
                self.solution_type = self.designs[self.design_name]["solution_type"]
        return self.get_project_info()

    def save_project(self, path: Path | None = None) -> dict[str, Any]:
        self._require_project()
        target = path or Path(self.project_path) if self.project_path else path
        if target is None:
            raise BackendStateError("Project path is not set. Provide a managed project path.")
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "backend": self.name,
            "project_name": self.project_name,
            "active_design": self.design_name,
            "designs": {
                name: _serialize_design_state(state)
                for name, state in self.designs.items()
            },
        }
        target.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        self.project_path = str(target)
        return {**self.get_project_info(), "saved": True, "bytes": target.stat().st_size}

    def close_project(self, save: bool = False) -> dict[str, Any]:
        self._require_project()
        if save:
            self.save_project()
        self.project_name = None
        self.project_path = None
        self.design_name = None
        self.solution_type = "DrivenModal"
        self.designs = {}
        return self.get_project_info()

    def create_design(self, spec: DesignSpec) -> dict[str, Any]:
        self._require_project()
        self.project_name = spec.project_name or self.project_name
        self._ensure_design(spec.design_name, spec.solution_type)
        return self.get_project_info()

    def set_active_design(self, design_name: str) -> dict[str, Any]:
        self._require_project()
        if design_name not in self.designs:
            raise BackendStateError(f"Design {design_name!r} does not exist.")
        self.design_name = design_name
        self.solution_type = self.designs[design_name]["solution_type"]
        return self.get_project_info()

    def get_design_summary(self, design_name: str | None = None) -> dict[str, Any]:
        self._require_project()
        target_name = design_name or self.design_name
        if not target_name:
            raise BackendStateError("No active design is selected.")
        if target_name not in self.designs:
            raise BackendStateError(f"Design {target_name!r} does not exist.")
        state = self.designs[target_name]
        return {
            "project_name": self.project_name,
            "design_name": target_name,
            "solution_type": state["solution_type"],
            "object_count": len(state["objects"]),
            "objects": sorted(state["objects"]),
            "setup_count": len(state["setups"]),
            "setups": sorted(state["setups"]),
            "solved_setups": sorted(state["solved_setups"]),
        }

    def create_patch_antenna(self, spec: PatchAntennaSpec) -> dict[str, Any]:
        state = self._active_design_state()
        recipe = build_patch_antenna(spec)
        for primitive in recipe["geometry"]:
            role = primitive["role"]
            object_name = primitive["name"]
            state["objects"][object_name] = {
                "role": role,
                "antenna": spec.name,
                "material": primitive["material"],
                "geometry": primitive,
            }
        for port in recipe["ports"]:
            state["objects"][port["name"]] = {
                "role": "port",
                "antenna": spec.name,
                "port_type": port["port_type"],
                "assignment": port,
            }
        state["objects"][spec.name] = {
            "role": "patch_antenna",
            "frequency_ghz": spec.frequency_ghz,
            "materials": recipe["materials"],
            "dimensions_mm": recipe["dimensions_mm"],
            "object_names": recipe["object_names"],
            "boundaries": recipe["boundaries"],
            "ports": recipe["ports"],
        }
        return recipe

    def create_dipole_antenna(self, spec: DipoleAntennaSpec) -> dict[str, Any]:
        state = self._active_design_state()
        recipe = build_dipole_antenna(spec)
        for primitive in recipe["geometry"]:
            state["objects"][primitive["name"]] = {
                "role": primitive["role"],
                "antenna": spec.name,
                "material": primitive["material"],
                "geometry": primitive,
            }
        for port in recipe["ports"]:
            state["objects"][port["name"]] = {
                "role": "port",
                "antenna": spec.name,
                "port_type": port["port_type"],
                "assignment": port,
            }
        state[spec.name] = {
            "role": "dipole_antenna",
            "frequency_ghz": spec.frequency_ghz,
            "materials": recipe["materials"],
            "dimensions_mm": recipe["dimensions_mm"],
            "object_names": recipe["object_names"],
            "boundaries": recipe["boundaries"],
            "ports": recipe["ports"],
        }
        return recipe

    def set_design_variable(self, name: str, value: str) -> dict[str, Any]:
        self._active_design_state()["variables"][name] = value
        return {"name": name, "value": value}

    def create_setup(self, spec: SetupSpec) -> dict[str, Any]:
        state = self._active_design_state()
        state["setups"][spec.setup_name] = spec
        sweep = SweepSpec(
            setup_name=spec.setup_name,
            sweep_name=spec.sweep_name,
            sweep_start_ghz=spec.sweep_start_ghz,
            sweep_stop_ghz=spec.sweep_stop_ghz,
            sweep_points=spec.sweep_points,
            sweep_type=spec.sweep_type,
        )
        self._store_sweep(state, sweep)
        data = setup_to_dict(spec)
        data["sweep"] = sweep_to_dict(sweep)
        return data

    def create_frequency_sweep(self, spec: SweepSpec) -> dict[str, Any]:
        state = self._active_design_state()
        if spec.setup_name not in state["setups"]:
            raise BackendStateError(f"Setup {spec.setup_name!r} does not exist.")
        self._store_sweep(state, spec)
        return sweep_to_dict(spec)

    def validate_design(self) -> dict[str, Any]:
        state = self._active_design_state()
        warnings: list[str] = []
        errors: list[str] = []
        if not any(item.get("role") == "patch_antenna" for item in state["objects"].values()):
            warnings.append("No antenna workflow object has been created.")
        if not state["setups"]:
            warnings.append("No simulation setup has been created.")
        if any(not state["sweeps"].get(setup_name) for setup_name in state["setups"]):
            warnings.append("At least one setup does not have a frequency sweep.")
        return {
            "valid": not errors and not warnings,
            "errors": errors,
            "warnings": warnings,
            "object_count": len(state["objects"]),
            "setup_count": len(state["setups"]),
            "sweep_count": sum(len(sweeps) for sweeps in state["sweeps"].values()),
        }

    def run_simulation(self, setup_name: str) -> dict[str, Any]:
        state = self._active_design_state()
        if setup_name not in state["setups"]:
            raise BackendStateError(f"Setup {setup_name!r} does not exist.")
        state["solved_setups"].add(setup_name)
        return {
            "setup_name": setup_name,
            "status": "completed",
            "backend_note": "Mock backend did not invoke AEDT.",
        }

    def get_s_parameters(
        self,
        setup_name: str,
        sweep_name: str | None,
        expression: str,
    ) -> dict[str, Any]:
        state = self._active_design_state()
        if setup_name not in state["setups"]:
            raise BackendStateError(f"Setup {setup_name!r} does not exist.")
        setup = state["setups"][setup_name]
        solved = setup_name in state["solved_setups"]
        resonance = setup.frequency_ghz
        min_s11 = -18.0 if solved else -3.0
        if expression.strip().lower().startswith("z("):
            impedance_points = [
                {"frequency_ghz": setup.sweep_start_ghz, "real_ohms": 35.0, "imag_ohms": -12.0},
                {"frequency_ghz": resonance, "real_ohms": 48.0, "imag_ohms": 3.0},
                {"frequency_ghz": setup.sweep_stop_ghz, "real_ohms": 62.0, "imag_ohms": 15.0},
            ]
            for point in impedance_points:
                point["value_db"] = 20.0
            return {
                "setup_name": setup_name,
                "sweep_name": sweep_name or setup.sweep_name,
                "expression": expression,
                "solved": solved,
                "sample_points": impedance_points,
            }
        return {
            "setup_name": setup_name,
            "sweep_name": sweep_name or setup.sweep_name,
            "expression": expression,
            "solved": solved,
            "resonance_frequency_ghz": resonance,
            "min_value_db": min_s11,
            "sample_points": [
                {"frequency_ghz": setup.sweep_start_ghz, "value_db": -4.5},
                {"frequency_ghz": resonance, "value_db": min_s11},
                {"frequency_ghz": setup.sweep_stop_ghz, "value_db": -5.2},
            ],
        }

    def export_touchstone(self, path: Path) -> dict[str, Any]:
        self._active_design_state()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# GHz S DB R 50\n"
            "! Mock Touchstone file generated by hfss-agent-mcp\n"
            "2.300 -8.0 0\n"
            "2.400 -18.0 0\n"
            "2.500 -9.0 0\n",
            encoding="utf-8",
        )
        return {"path": str(path), "bytes": path.stat().st_size}

    def _require_connection(self) -> None:
        if not self.connected:
            raise BackendStateError("HFSS session is not connected. Call connect_hfss first.")

    def _require_project(self) -> None:
        self._require_connection()
        if self.project_name is None:
            raise BackendStateError("No HFSS project is loaded. Create or open a project first.")

    def _ensure_design(self, design_name: str, solution_type: str) -> None:
        if design_name not in self.designs:
            self.designs[design_name] = {
                "solution_type": solution_type,
                "objects": {},
                "setups": {},
                "sweeps": {},
                "variables": {},
                "solved_setups": set(),
            }
        self.design_name = design_name
        self.solution_type = self.designs[design_name]["solution_type"]

    def _active_design_state(self) -> dict[str, Any]:
        self._require_project()
        if not self.design_name:
            raise BackendStateError("No active design is selected. Create or set an active design first.")
        if self.design_name not in self.designs:
            raise BackendStateError(f"Design {self.design_name!r} does not exist.")
        return self.designs[self.design_name]

    @staticmethod
    def _store_sweep(state: dict[str, Any], spec: SweepSpec) -> None:
        state["sweeps"].setdefault(spec.setup_name, {})
        state["sweeps"][spec.setup_name][spec.sweep_name] = spec


def _serialize_design_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "solution_type": state["solution_type"],
        "objects": state["objects"],
        "setups": {
            name: asdict(setup)
            for name, setup in state["setups"].items()
        },
        "sweeps": {
            setup_name: {
                sweep_name: asdict(sweep)
                for sweep_name, sweep in sweeps.items()
            }
            for setup_name, sweeps in state["sweeps"].items()
        },
        "variables": dict(state.get("variables", {})),
        "solved_setups": sorted(state["solved_setups"]),
    }


def _restore_design_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "solution_type": state.get("solution_type", "DrivenModal"),
        "objects": dict(state.get("objects", {})),
        "setups": {
            name: SetupSpec(**setup)
            for name, setup in state.get("setups", {}).items()
        },
        "sweeps": {
            setup_name: {
                sweep_name: SweepSpec(**sweep)
                for sweep_name, sweep in sweeps.items()
            }
            for setup_name, sweeps in state.get("sweeps", {}).items()
        },
        "variables": dict(state.get("variables", {})),
        "solved_setups": set(state.get("solved_setups", [])),
    }
