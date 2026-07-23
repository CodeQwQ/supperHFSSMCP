from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hfss_agent_mcp.backends.mock import MockHfssBackend
from hfss_agent_mcp.config import ServerConfig
from hfss_agent_mcp.core.service import HfssService
from hfss_agent_mcp.server import create_app


class SessionManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="hfss-agent-session-"))
        self.service = HfssService(
            MockHfssBackend(),
            output_root=self.tmp,
            config=ServerConfig(backend="mock", output_root=self.tmp),
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_session_tools_are_registered(self) -> None:
        app = create_app(ServerConfig(backend="mock"))
        tools = asyncio.run(app.list_tools())
        names = {tool.name for tool in tools}
        self.assertIn("list_aedt_sessions", names)
        self.assertIn("launch_aedt", names)
        self.assertIn("get_session_info", names)
        self.assertIn("release_connection", names)

    def test_launch_connect_list_and_release_session(self) -> None:
        launched = self.service.launch_aedt(owner="alice", desktop_version="2025.2", port=50051)
        self.assertEqual("ok", launched["status"])
        session_id = launched["data"]["session"]["session_id"]
        self.assertEqual("launched", launched["data"]["session"]["status"])
        self.assertEqual("alice", launched["data"]["session"]["owner"])

        connected = self.service.connect_hfss(
            session_id=session_id,
            owner="alice",
            design_name="PatchDemo",
            port=50051,
        )
        self.assertEqual("ok", connected["status"])
        self.assertEqual(session_id, connected["data"]["session"]["session_id"])
        self.assertEqual("connected", connected["data"]["session"]["status"])
        self.assertEqual("PatchDemo", connected["data"]["project"]["design_name"])

        listed = self.service.list_aedt_sessions()
        self.assertEqual("ok", listed["status"])
        self.assertEqual(1, listed["data"]["count"])
        self.assertEqual(session_id, listed["data"]["sessions"][0]["session_id"])

        info = self.service.get_session_info(session_id)
        self.assertEqual("ok", info["status"])
        self.assertEqual("connected", info["data"]["session"]["status"])

        released = self.service.release_connection(session_id)
        self.assertEqual("ok", released["status"])
        self.assertEqual("released", released["data"]["session"]["status"])

    def test_connect_without_session_creates_explicit_session_record(self) -> None:
        connected = self.service.connect_hfss(owner="bob", design_name="PatchDemo")

        self.assertEqual("ok", connected["status"])
        self.assertEqual("bob", connected["data"]["session"]["owner"])
        self.assertEqual("connected", connected["data"]["session"]["status"])
        self.assertTrue(connected["data"]["session"]["session_id"].startswith("mock-"))

    def test_unknown_session_returns_structured_error(self) -> None:
        result = self.service.get_session_info("missing-session")

        self.assertEqual("error", result["status"])
        self.assertEqual("SessionError", result["data"]["error_type"])
        self.assertIn("missing-session", result["message"])

    def test_repeated_connect_reuses_same_session_id(self) -> None:
        first = self.service.connect_hfss(owner="alice", design_name="One")
        session_id = first["data"]["session"]["session_id"]

        second = self.service.connect_hfss(
            session_id=session_id,
            owner="alice",
            design_name="Two",
        )

        self.assertEqual("ok", second["status"])
        self.assertEqual(session_id, second["data"]["session"]["session_id"])
        self.assertEqual(1, self.service.list_aedt_sessions()["data"]["count"])

    def test_connect_defaults_to_graphical_mode(self) -> None:
        connected = self.service.connect_hfss(owner="alice", design_name="GraphicalDemo")

        session = connected["data"]["session"]

        self.assertEqual("ok", connected["status"])
        self.assertFalse(session["metadata"]["non_graphical"])

    def test_release_connection_closes_backend_by_default(self) -> None:
        connected = self.service.connect_hfss(owner="alice", design_name="ReleaseDemo")
        session_id = connected["data"]["session"]["session_id"]

        released = self.service.release_connection(session_id)

        self.assertEqual("ok", released["status"])
        self.assertTrue(released["data"]["release"]["save_project"])
        self.assertTrue(released["data"]["release"]["close_desktop"])
        self.assertFalse(self.service.backend.connected)

    def test_release_connection_can_keep_desktop_process_for_manual_work(self) -> None:
        connected = self.service.connect_hfss(owner="alice", design_name="KeepDesktopDemo")
        session_id = connected["data"]["session"]["session_id"]

        released = self.service.release_connection(session_id, close_desktop=False)

        self.assertEqual("ok", released["status"])
        self.assertFalse(released["data"]["release"]["close_desktop"])
        self.assertFalse(self.service.backend.connected)


if __name__ == "__main__":
    unittest.main()
