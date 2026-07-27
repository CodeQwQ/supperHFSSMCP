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
    _raise_worker_error,
    _call_release_desktop,
    _solution_data_to_points,
    _student_grpc_detection_patch,
)
from hfss_agent_mcp.config import ServerConfig
from hfss_agent_mcp.core.errors import BackendUnavailableError
from hfss_agent_mcp.core.models import (
    BoxSpec,
    ConnectionSpec,
    DeleteObjectsSpec,
    LumpedPortSpec,
    MaterialAssignmentSpec,
    SheetSpec,
)
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
        self.assertEqual("validate_full_design", result["api"])
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

    def test_create_model_box_and_sheet_call_pyaedt_modeler(self) -> None:
        calls: list[tuple[str, dict]] = []

        class FakeModeler:
            def create_box(self, **kwargs):
                calls.append(("box", kwargs))

            def create_rectangle(self, **kwargs):
                calls.append(("sheet", kwargs))

        backend = PyAedtBackend(use_process_worker=False)
        backend._hfss = type("FakeHfss", (), {"modeler": FakeModeler()})()

        box = backend.create_model_box(
            BoxSpec(
                name="Airbox",
                origin_mm=(-1.0, -1.0, -1.0),
                size_mm=(2.0, 2.0, 2.0),
                material="air",
                role="airbox",
            )
        )
        sheet = backend.create_model_sheet(
            SheetSpec(
                name="Patch",
                orientation="XY",
                origin_mm=(0.0, 0.0, 0.0),
                size_mm=(10.0, 8.0),
                material="copper",
                role="patch",
            )
        )

        self.assertEqual("Airbox", box["name"])
        self.assertEqual("Patch", sheet["name"])
        self.assertEqual("box", calls[0][0])
        self.assertEqual([-1.0, -1.0, -1.0], calls[0][1]["origin"])
        self.assertEqual("sheet", calls[1][0])
        self.assertEqual("XY", calls[1][1]["orientation"])

    def test_set_object_material_uses_modeler_object_when_available(self) -> None:
        class FakeObject:
            material_name = "air"

        fake_object = FakeObject()

        class FakeModeler:
            def __getitem__(self, name: str):
                if name != "Patch":
                    raise KeyError(name)
                return fake_object

        backend = PyAedtBackend(use_process_worker=False)
        backend._hfss = type("FakeHfss", (), {"modeler": FakeModeler()})()

        result = backend.set_object_material(
            MaterialAssignmentSpec(object_name="Patch", material="copper")
        )

        self.assertEqual("Patch", result["object_name"])
        self.assertEqual("copper", fake_object.material_name)

    def test_delete_model_objects_calls_modeler_delete_with_explicit_names(self) -> None:
        calls: list[list[str]] = []

        class FakeModeler:
            object_names = ["Patch", "Airbox"]

            def delete(self, assignment):
                calls.append(list(assignment))
                self.object_names = [name for name in self.object_names if name not in assignment]
                return True

        backend = PyAedtBackend(use_process_worker=False)
        backend._hfss = type("FakeHfss", (), {"modeler": FakeModeler()})()

        result = backend.delete_model_objects(DeleteObjectsSpec(object_names=("Patch",)))

        self.assertEqual(["Patch"], calls[0])
        self.assertEqual(["Patch"], result["deleted_objects"])
        self.assertEqual(["Airbox"], result["after_objects"])

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

    def test_create_lumped_port_reuses_pyaedt_port_assignment(self) -> None:
        calls: list[dict] = []

        class FakeHfss:
            def lumped_port(self, **kwargs):
                calls.append(kwargs)

        backend = PyAedtBackend(use_process_worker=False)
        backend._hfss = FakeHfss()

        result = backend.create_lumped_port(
            LumpedPortSpec(
                name="FeedPort",
                sheet_name="PortSheet",
                integration_start_mm=(0.0, 0.0, 0.0),
                integration_end_mm=(0.0, 1.0, 0.0),
                impedance_ohm=50.0,
            )
        )

        self.assertEqual("FeedPort", result["name"])
        self.assertEqual("PortSheet", calls[0]["assignment"])

    def test_run_simulation_starts_solver_and_polls_until_aedt_is_idle(self) -> None:
        calls: list[tuple[str, str | bool]] = []

        class FakeHfss:
            def analyze_setup(self, name: str, blocking: bool) -> bool:
                calls.append(("analyze_setup", name))
                calls.append(("blocking", blocking))
                return True

            _running = [True, True, False]

            @property
            def are_there_simulations_running(self) -> bool:
                value = self._running.pop(0)
                calls.append(("running", value))
                return value

            def analyze(self, **kwargs):
                raise AssertionError("run_simulation must not invoke analyze()")

        backend = PyAedtBackend(use_process_worker=False)
        backend._simulation_poll_interval_seconds = 0.0
        backend._hfss = FakeHfss()

        result = backend.run_simulation("Setup1")

        self.assertEqual("completed", result["status"])
        self.assertEqual(3, result["simulation_status_checks"])
        self.assertTrue(result["observed_running"])
        self.assertIn(("blocking", False), calls)
        self.assertEqual(("running", True), calls[2])

    def test_run_simulation_reports_solver_failure(self) -> None:
        class FakeHfss:
            project_name = "Project1"
            design_name = "Design1"

            class Logger:
                def get_messages(self, level: int = 0):
                    return ["[error] Port has no conductors touching it."]

            logger = Logger()

            def analyze_setup(self, name: str, blocking: bool) -> bool:
                return False

            @property
            def are_there_simulations_running(self) -> bool:
                return False

        backend = PyAedtBackend(use_process_worker=False)
        backend._hfss = FakeHfss()

        result = backend.run_simulation("Setup1")

        self.assertEqual("failed", result["status"])
        self.assertIn("Port has no conductors", result["failure_reason"])
        self.assertIn("Port has no conductors", result["hfss_messages"][0])

    def test_assign_boundary_supports_perfecte_sheets(self) -> None:
        calls: list[dict] = []

        class FakeHfss:
            def assign_perfecte_to_sheets(self, assignment, name, is_infinite_ground=False):
                calls.append(
                    {
                        "assignment": assignment,
                        "name": name,
                        "is_infinite_ground": is_infinite_ground,
                    }
                )

        backend = PyAedtBackend(use_process_worker=False)
        backend._hfss = FakeHfss()

        backend._assign_boundary(
            {
                "name": "Dipole_perfect_e",
                "boundary_type": "perfect_e",
                "objects": ["arm_negative", "arm_positive"],
            }
        )

        self.assertEqual(["arm_negative", "arm_positive"], calls[0]["assignment"])
        self.assertEqual("Dipole_perfect_e", calls[0]["name"])

    def test_release_desktop_uses_hfss_close_desktop_keyword(self) -> None:
        calls: list[dict] = []

        def release_desktop(*, close_projects=True, close_desktop=True):
            calls.append({"close_projects": close_projects, "close_desktop": close_desktop})
            return True

        result = _call_release_desktop(
            release_desktop,
            close_projects=True,
            close_desktop=False,
        )

        self.assertTrue(result)
        self.assertEqual([{"close_projects": True, "close_desktop": False}], calls)

    def test_disconnect_terminates_controlled_process_when_release_leaves_it_running(self) -> None:
        calls: list[tuple[str, int]] = []

        class FakeDesktop:
            aedt_process_id = 12345

        class FakeHfss:
            desktop_class = FakeDesktop()

            def release_desktop(self, *, close_projects=True, close_desktop=True):
                calls.append(("release", int(close_desktop)))
                return True

        backend = PyAedtBackend(use_process_worker=False)
        backend._hfss = FakeHfss()

        with patch(
            "hfss_agent_mcp.backends.pyaedt._wait_for_process_exit",
            side_effect=[False, True],
        ) as wait_for_exit:
            with patch(
                "hfss_agent_mcp.backends.pyaedt._terminate_process_tree",
                return_value={"method": "taskkill", "returncode": 0},
            ) as terminate:
                result = backend.disconnect(save_project=False, close_projects=True, close_desktop=True)

        self.assertEqual([("release", 1)], calls)
        self.assertEqual(12345, result["aedt_process_id"])
        self.assertTrue(result["process_closed"])
        self.assertEqual({"method": "taskkill", "returncode": 0}, result["forced_termination"])
        terminate.assert_called_once_with(12345)
        self.assertEqual(2, wait_for_exit.call_count)

    def test_worker_error_preserves_hfss_messages_in_exception_details(self) -> None:
        response = {
            "status": "error",
            "error_type": "BackendUnavailableError",
            "message": "solve failed",
            "hfss_messages": ["[error] Sheet is not assigned Perfect E."],
        }

        with self.assertRaises(BackendUnavailableError) as raised:
            _raise_worker_error("run_simulation", response)

        self.assertIn("Sheet is not assigned", raised.exception.details["hfss_messages"][0])

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
