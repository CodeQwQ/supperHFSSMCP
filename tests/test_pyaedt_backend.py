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
    _student_grpc_detection_patch,
)
from hfss_agent_mcp.config import ServerConfig
from hfss_agent_mcp.core.models import ConnectionSpec
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
