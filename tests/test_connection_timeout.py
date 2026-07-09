from __future__ import annotations

import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hfss_agent_mcp.backends.pyaedt import PyAedtBackend
from hfss_agent_mcp.config import ServerConfig
from hfss_agent_mcp.core.errors import SessionError
from hfss_agent_mcp.core.models import ConnectionSpec
from hfss_agent_mcp.core.service import HfssService


class SlowHfss:
    def __init__(self, **kwargs) -> None:
        time.sleep(0.2)


class ConnectionTimeoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="hfss-agent-timeout-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pyaedt_backend_times_out_hfss_initialization(self) -> None:
        backend = PyAedtBackend()
        spec = ConnectionSpec(connect_timeout_seconds=0.01)

        with patch.object(backend, "_load_hfss_class", return_value=SlowHfss):
            started = time.monotonic()
            with self.assertRaises(SessionError):
                backend.connect(spec)
            elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.15)
        self.assertIsNone(backend._hfss)

    def test_connect_hfss_timeout_marks_session_failed(self) -> None:
        backend = PyAedtBackend()
        service = HfssService(
            backend,
            output_root=self.tmp,
            config=ServerConfig(output_root=self.tmp, connect_timeout_seconds=0.01),
        )

        with patch.object(backend, "_load_hfss_class", return_value=SlowHfss):
            result = service.connect_hfss(owner="alice")

        self.assertEqual("error", result["status"])
        self.assertEqual("SessionError", result["data"]["error_type"])
        self.assertIn("timed out", result["message"])
        self.assertEqual("failed", result["data"]["session"]["status"])
        self.assertEqual("alice", result["data"]["session"]["owner"])
        self.assertIn("timed out", result["data"]["session"]["metadata"]["failure_reason"])


if __name__ == "__main__":
    unittest.main()
