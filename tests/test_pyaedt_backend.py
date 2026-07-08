from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hfss_agent_mcp.backends.pyaedt import PyAedtBackend
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


if __name__ == "__main__":
    unittest.main()
