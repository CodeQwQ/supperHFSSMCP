from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hfss_agent_mcp.backends.pyaedt import (
    PyAedtBackend,
    _execute_worker_command,
    _solution_data_to_points,
    _student_grpc_detection_patch,
)
from hfss_agent_mcp.config import ServerConfig
from hfss_agent_mcp.core.errors import BackendUnavailableError
from hfss_agent_mcp.core.models import ConnectionSpec
from hfss_agent_mcp.core.models import SweepSpec
from hfss_agent_mcp.core.service import HfssService


class CapturingBackend:
    name = "capture"

    def __init__(self) -> None:
        self.spec: ConnectionSpec | None = None

    def health(self) -> dict:
        return {"backend": self.name, "connected": False, "hfss_available": True}

    def connect(self, spec: ConnectionSpec) -> dict:
        self.spec = spec
        return {"backend": self.name, "connected": True}


class PyAedtBackendTests(unittest.TestCase):
    def test_validate_design_uses_pyaedt_full_design_validation(self) -> None:
        calls: list[str] = []

        class FakeHfss:
            def validate_full_design(self):
                calls.append("validate_full_design")
                return (["Design validation check PASSED."], True)

        backend = PyAedtBackend(use_process_worker=False)
        backend._hfss = FakeHfss()

        result = backend.validate_design()

        self.assertTrue(result["valid"])
        self.assertEqual(["Design validation check PASSED."], result["messages"])
        self.assertEqual(["validate_full_design"], calls)

    def test_create_geometry_uses_port_sheet_orientation(self) -> None:
        calls: list[dict] = []

        class FakeModeler:
            def create_rectangle(self, **kwargs):
                calls.append(kwargs)

        backend = PyAedtBackend(use_process_worker=False)
        backend._hfss = type("FakeHfss", (), {"modeler": FakeModeler()})()

        name = backend._create_geometry_primitive(
            {
                "name": "PortSheet",
                "kind": "sheet",
                "origin_mm": [0.0, 0.0, 0.0],
                "size_mm": [3.0, 1.6, 0.0],
                "material": "air",
                "metadata": {"orientation": "XZ"},
            }
        )

        self.assertEqual("PortSheet", name)
        self.assertEqual("XZ", calls[0]["orientation"])
        self.assertEqual([3.0, 1.6], calls[0]["sizes"])

    def test_assign_port_passes_single_port_sheet_as_scalar(self) -> None:
        calls: list[dict] = []

        class FakeHfss:
            def lumped_port(self, **kwargs):
                calls.append(kwargs)

        backend = PyAedtBackend(use_process_worker=False)
        backend._hfss = FakeHfss()
        backend._assign_port(
            {
                "port_type": "lumped",
                "objects": ["PortSheet"],
                "integration_line_mm": ((0.0, 0.0, 1.6), (0.0, 0.0, 0.0)),
                "impedance_ohm": 50.0,
                "name": "Port1",
            }
        )

        self.assertEqual("PortSheet", calls[0]["assignment"])

    def test_run_simulation_uses_direct_setup_analysis(self) -> None:
        calls: list[tuple[str, str]] = []

        class FakeHfss:
            def analyze_setup(self, name: str, blocking: bool) -> bool:
                calls.append(("analyze_setup", name))
                return True

            def analyze(self, **kwargs):
                raise AssertionError("run_simulation must not invoke analyze()")

        backend = PyAedtBackend(use_process_worker=False)
        backend._hfss = FakeHfss()

        result = backend.run_simulation("Setup1")

        self.assertEqual({"setup_name": "Setup1", "status": "completed"}, result)
        self.assertEqual([("analyze_setup", "Setup1")], calls)

    def test_run_simulation_reports_solver_failure(self) -> None:
        class FakeHfss:
            def analyze_setup(self, name: str, blocking: bool) -> bool:
                return False

        backend = PyAedtBackend(use_process_worker=False)
        backend._hfss = FakeHfss()

        result = backend.run_simulation("Setup1")

        self.assertEqual("failed", result["status"])

    def test_solution_data_rejects_nonfinite_values_at_backend_boundary(self) -> None:
        class FakeSolutionData:
            primary_sweep_values = ["2.4GHz"]

            def get_expression_data(self, expression: str, formula: str):
                values = {"db20": [float("nan")], "real": [0.1], "imag": [0.2]}
                return self.primary_sweep_values, values[formula]

        with self.assertRaisesRegex(BackendUnavailableError, "non-finite"):
            _solution_data_to_points(FakeSolutionData(), "S(1,1)")

    def test_frequency_sweep_uses_current_pyaedt_unit_keyword(self) -> None:
        calls: list[dict] = []

        class FakeHfss:
            def create_linear_count_sweep(self, **kwargs):
                calls.append(kwargs)
                return True

        backend = PyAedtBackend(use_process_worker=False)
        backend._hfss = FakeHfss()
        result = backend.create_frequency_sweep(
            SweepSpec(
                setup_name="Setup1",
                sweep_name="Sweep1",
                sweep_start_ghz=2.0,
                sweep_stop_ghz=3.0,
                sweep_points=101,
            )
        )

        self.assertEqual("Sweep1", result["sweep_name"])
        self.assertEqual("GHz", calls[0]["unit"])
        self.assertNotIn("units", calls[0])
        self.assertEqual("Discrete", calls[0]["sweep_type"])

    def test_solution_data_is_converted_to_transport_safe_points(self) -> None:
        class FakeSolutionData:
            primary_sweep_values = ["2.0GHz", "2.4GHz"]

            def get_expression_data(self, expression: str, formula: str):
                values = {
                    "db20": [-5.0, -18.0],
                    "real": [0.1, 0.05],
                    "imag": [-0.2, 0.01],
                }
                return self.primary_sweep_values, values[formula]

        points = _solution_data_to_points(FakeSolutionData(), "S(1,1)")

        self.assertEqual(2.4, points[1]["frequency_ghz"])
        self.assertEqual(-18.0, points[1]["value_db"])
        self.assertEqual(0.05, points[1]["real"])

    def test_solution_data_accepts_array_like_frequency_values(self) -> None:
        class ArrayLike:
            def __iter__(self):
                return iter(["2.0GHz", "2.4GHz"])

            def __bool__(self):
                raise ValueError("array truth value is ambiguous")

        class FakeSolutionData:
            primary_sweep_values = ArrayLike()

            def get_expression_data(self, expression: str, formula: str):
                values = {"db20": [-5.0, -18.0], "real": [0.1, 0.05], "imag": [-0.2, 0.01]}
                return self.primary_sweep_values, values[formula]

        points = _solution_data_to_points(FakeSolutionData(), "S(1,1)")

        self.assertEqual(2, len(points))

    def test_solution_data_preserves_complex_impedance_fields(self) -> None:
        class FakeSolutionData:
            primary_sweep_values = ["2.4GHz"]

            def get_expression_data(self, expression: str, formula: str):
                values = {"db20": [34.0], "real": [48.0], "imag": [3.0]}
                return self.primary_sweep_values, values[formula]

        points = _solution_data_to_points(FakeSolutionData(), "Z(1,1)")

        self.assertEqual(48.0, points[0]["real_ohms"])
        self.assertEqual(3.0, points[0]["imag_ohms"])

    def test_student_executable_sets_student_environment_variable(self) -> None:
        executable = Path(r"D:\Ansys\ANSYS Inc\ANSYS Student\v252\AnsysEM\ansysedtsv.exe")
        spec = ConnectionSpec(student_version=True, aedt_executable=str(executable))

        with patch.dict(os.environ, {"ANSYSEM_ROOT252": str(executable.parent)}, clear=False):
            PyAedtBackend()._prepare_pyaedt_environment(spec)

            self.assertEqual(str(executable.parent), os.environ["ANSYSEMSV_ROOT252"])
            self.assertNotIn("ANSYSEM_ROOT252", os.environ)

    def test_regular_executable_sets_regular_environment_variable(self) -> None:
        executable = Path(r"C:\Program Files\AnsysEM\v252\Win64\ansysedt.exe")
        spec = ConnectionSpec(student_version=False, aedt_executable=str(executable))

        with patch.dict(os.environ, {}, clear=True):
            PyAedtBackend()._prepare_pyaedt_environment(spec)

            self.assertEqual(str(executable.parent), os.environ["ANSYSEM_ROOT252"])
            self.assertNotIn("ANSYSEMSV_ROOT252", os.environ)

    def test_service_infers_student_version_and_desktop_version_from_configured_executable(self) -> None:
        backend = CapturingBackend()
        executable = Path(r"D:\Ansys\ANSYS Inc\ANSYS Student\v252\AnsysEM\ansysedtsv.exe")
        with tempfile.TemporaryDirectory(prefix="hfss-agent-pyaedt-") as tmp:
            service = HfssService(
                backend,
                output_root=Path(tmp),
                config=ServerConfig(output_root=Path(tmp), aedt_executable=executable),
            )

            service.connect_hfss()

        self.assertIsNotNone(backend.spec)
        self.assertTrue(backend.spec.student_version)
        self.assertEqual("2025.2", backend.spec.desktop_version)
        self.assertEqual(str(executable), backend.spec.aedt_executable)

    def test_student_grpc_detection_patch_finds_student_session_port(self) -> None:
        desktop_module = types.SimpleNamespace(
            is_grpc_session_active=lambda port, machine=None: False,
        )
        calls: list[tuple[bool, object]] = []

        def active_sessions(*, student_version: bool = False, non_graphical: object = None) -> dict[int, int]:
            calls.append((student_version, non_graphical))
            return {1234: 50051} if student_version else {}

        with _student_grpc_detection_patch(
            True,
            desktop_module=desktop_module,
            active_sessions=active_sessions,
        ):
            self.assertTrue(desktop_module.is_grpc_session_active(50051))
            self.assertFalse(desktop_module.is_grpc_session_active(50052))

        self.assertFalse(desktop_module.is_grpc_session_active(50051))
        self.assertIn((True, None), calls)

    def test_student_grpc_detection_patch_is_disabled_for_regular_aedt(self) -> None:
        desktop_module = types.SimpleNamespace(
            is_grpc_session_active=lambda port, machine=None: False,
        )
        calls: list[tuple[bool, object]] = []

        def active_sessions(*, student_version: bool = False, non_graphical: object = None) -> dict[int, int]:
            calls.append((student_version, non_graphical))
            return {1234: 50051}

        with _student_grpc_detection_patch(
            False,
            desktop_module=desktop_module,
            active_sessions=active_sessions,
        ):
            self.assertFalse(desktop_module.is_grpc_session_active(50051))

        self.assertEqual([], calls)

    def test_connect_delegates_to_process_worker(self) -> None:
        calls: list[tuple[str, dict, float | None]] = []

        class FakeWorker:
            def call(self, command: str, args: dict, timeout_seconds: float | None = None) -> dict:
                calls.append((command, args, timeout_seconds))
                return {"backend": "pyaedt", "connected": True}

        spec = ConnectionSpec(student_version=True, connect_timeout_seconds=12.5)
        with patch("hfss_agent_mcp.backends.pyaedt._PyAedtWorkerClient", return_value=FakeWorker()):
            result = PyAedtBackend().connect(spec)

        self.assertEqual({"backend": "pyaedt", "connected": True}, result)
        self.assertEqual("connect", calls[0][0])
        self.assertTrue(calls[0][1]["spec"]["student_version"])
        self.assertEqual(12.5, calls[0][1]["spec"]["connect_timeout_seconds"])
        self.assertEqual(12.5, calls[0][2])

    def test_worker_connect_runs_without_thread_timeout(self) -> None:
        captured: list[ConnectionSpec] = []

        class FakeDirectBackend:
            def connect(self, spec: ConnectionSpec) -> dict:
                captured.append(spec)
                return {"backend": "pyaedt", "connected": True}

        result = _execute_worker_command(
            FakeDirectBackend(),
            "connect",
            {"spec": ConnectionSpec(student_version=True, connect_timeout_seconds=12.5).__dict__},
        )

        self.assertEqual({"backend": "pyaedt", "connected": True}, result)
        self.assertIsNone(captured[0].connect_timeout_seconds)
        self.assertTrue(captured[0].student_version)


if __name__ == "__main__":
    unittest.main()
