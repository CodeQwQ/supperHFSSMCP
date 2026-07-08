from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from hfss_agent_mcp.core.errors import BackendStateError
from hfss_agent_mcp.core.models import (
    ConnectionSpec,
    DesignSpec,
    PatchAntennaSpec,
    SetupSpec,
)


class MockHfssBackend:
    name = "mock"

    def __init__(self) -> None:
        self.connected = False
        self.project_name = "MockProject"
        self.project_path: str | None = None
        self.design_name: str | None = None
        self.solution_type = "DrivenModal"
        self.objects: dict[str, dict[str, Any]] = {}
        self.setups: dict[str, SetupSpec] = {}
        self.solved_setups: set[str] = set()

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
            self.design_name = spec.design_name
        self.solution_type = spec.solution_type
        return self.get_project_info()

    def get_project_info(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "connected": self.connected,
            "project_name": self.project_name,
            "project_path": self.project_path,
            "design_name": self.design_name,
            "solution_type": self.solution_type,
            "object_count": len(self.objects),
            "objects": sorted(self.objects),
            "setups": sorted(self.setups),
            "solved_setups": sorted(self.solved_setups),
        }

    def create_design(self, spec: DesignSpec) -> dict[str, Any]:
        self._require_connection()
        self.project_name = spec.project_name or self.project_name
        self.design_name = spec.design_name
        self.solution_type = spec.solution_type
        return self.get_project_info()

    def create_patch_antenna(self, spec: PatchAntennaSpec) -> dict[str, Any]:
        self._require_connection()
        dimensions = _estimate_patch_dimensions(spec)
        object_names = {
            "substrate": f"{spec.name}_substrate",
            "ground": f"{spec.name}_ground",
            "patch": f"{spec.name}_patch",
            "feed": f"{spec.name}_feed",
            "airbox": f"{spec.name}_airbox",
        }
        for role, object_name in object_names.items():
            self.objects[object_name] = {
                "role": role,
                "antenna": spec.name,
                "material": spec.substrate_material if role == "substrate" else "pec",
            }
        self.objects[spec.name] = {
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
        self._require_connection()
        self.setups[spec.setup_name] = spec
        return {
            "setup_name": spec.setup_name,
            "frequency_ghz": spec.frequency_ghz,
            "sweep_name": spec.sweep_name,
            "sweep_start_ghz": spec.sweep_start_ghz,
            "sweep_stop_ghz": spec.sweep_stop_ghz,
            "sweep_points": spec.sweep_points,
        }

    def validate_design(self) -> dict[str, Any]:
        self._require_connection()
        warnings: list[str] = []
        if not any(item.get("role") == "patch_antenna" for item in self.objects.values()):
            warnings.append("No antenna workflow object has been created.")
        if not self.setups:
            warnings.append("No simulation setup has been created.")
        return {
            "valid": not warnings,
            "warnings": warnings,
            "object_count": len(self.objects),
            "setup_count": len(self.setups),
        }

    def run_simulation(self, setup_name: str) -> dict[str, Any]:
        self._require_connection()
        if setup_name not in self.setups:
            raise BackendStateError(f"Setup {setup_name!r} does not exist.")
        self.solved_setups.add(setup_name)
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
        self._require_connection()
        if setup_name not in self.setups:
            raise BackendStateError(f"Setup {setup_name!r} does not exist.")
        setup = self.setups[setup_name]
        solved = setup_name in self.solved_setups
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
        self._require_connection()
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
