from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

from hfss_agent_mcp.core.errors import BackendStateError
from hfss_agent_mcp.core.models import (
    ConnectionSpec,
    DesignSpec,
    PatchAntennaSpec,
    ProjectSpec,
    SetupSpec,
)


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
        dimensions = _estimate_patch_dimensions(spec)
        object_names = {
            "substrate": f"{spec.name}_substrate",
            "ground": f"{spec.name}_ground",
            "patch": f"{spec.name}_patch",
            "feed": f"{spec.name}_feed",
            "airbox": f"{spec.name}_airbox",
        }
        for role, object_name in object_names.items():
            state["objects"][object_name] = {
                "role": role,
                "antenna": spec.name,
                "material": spec.substrate_material if role == "substrate" else "pec",
            }
        state["objects"][spec.name] = {
            "role": "patch_antenna",
            "frequency_ghz": spec.frequency_ghz,
            "substrate_material": spec.substrate_material,
            "dimensions_mm": dimensions,
        }
        return {
            "antenna_name": spec.name,
            "object_names": object_names,
            "dimensions_mm": dimensions,
        }

    def create_setup(self, spec: SetupSpec) -> dict[str, Any]:
        state = self._active_design_state()
        state["setups"][spec.setup_name] = spec
        return {
            "setup_name": spec.setup_name,
            "frequency_ghz": spec.frequency_ghz,
            "sweep_name": spec.sweep_name,
            "sweep_start_ghz": spec.sweep_start_ghz,
            "sweep_stop_ghz": spec.sweep_stop_ghz,
            "sweep_points": spec.sweep_points,
        }

    def validate_design(self) -> dict[str, Any]:
        state = self._active_design_state()
        warnings: list[str] = []
        if not any(item.get("role") == "patch_antenna" for item in state["objects"].values()):
            warnings.append("No antenna workflow object has been created.")
        if not state["setups"]:
            warnings.append("No simulation setup has been created.")
        return {
            "valid": not warnings,
            "warnings": warnings,
            "object_count": len(state["objects"]),
            "setup_count": len(state["setups"]),
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


def _estimate_patch_dimensions(spec: PatchAntennaSpec) -> dict[str, float]:
    er = _relative_permittivity(spec.substrate_material)
    frequency_hz = spec.frequency_ghz * 1e9
    c = 299_792_458.0
    width_mm = c / (2 * frequency_hz) * math.sqrt(2 / (er + 1)) * 1000
    eps_eff = (er + 1) / 2 + (er - 1) / 2 / math.sqrt(1 + 12 * spec.substrate_height_mm / width_mm)
    delta_l = (
        0.412
        * spec.substrate_height_mm
        * ((eps_eff + 0.3) * (width_mm / spec.substrate_height_mm + 0.264))
        / ((eps_eff - 0.258) * (width_mm / spec.substrate_height_mm + 0.8))
    )
    length_mm = c / (2 * frequency_hz * math.sqrt(eps_eff)) * 1000 - 2 * delta_l
    patch_width = spec.patch_width_mm or width_mm
    patch_length = spec.patch_length_mm or length_mm
    ground_width = spec.ground_width_mm or patch_width + 6 * spec.substrate_height_mm
    ground_length = spec.ground_length_mm or patch_length + 6 * spec.substrate_height_mm
    return {
        "patch_width_mm": round(patch_width, 3),
        "patch_length_mm": round(patch_length, 3),
        "ground_width_mm": round(ground_width, 3),
        "ground_length_mm": round(ground_length, 3),
        "substrate_height_mm": round(spec.substrate_height_mm, 3),
        "feed_width_mm": round(spec.feed_width_mm, 3),
        "feed_offset_mm": round(spec.feed_offset_mm, 3),
    }


def _relative_permittivity(material: str) -> float:
    lookup = {
        "fr4": 4.4,
        "fr4_epoxy": 4.4,
        "rogers4350": 3.48,
        "rogers_ro4350": 3.48,
        "air": 1.0,
    }
    return lookup.get(material.strip().lower(), 4.4)


def _serialize_design_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "solution_type": state["solution_type"],
        "objects": state["objects"],
        "setups": {
            name: asdict(setup)
            for name, setup in state["setups"].items()
        },
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
        "solved_setups": set(state.get("solved_setups", [])),
    }
