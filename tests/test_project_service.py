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


class ProjectServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="hfss-agent-project-"))
        self.service = HfssService(
            MockHfssBackend(),
            output_root=self.tmp,
            config=ServerConfig(backend="mock", output_root=self.tmp),
        )
        self.service.connect_hfss(owner="alice")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_project_tools_are_registered(self) -> None:
        app = create_app(ServerConfig(backend="mock"))
        tools = asyncio.run(app.list_tools())
        names = {tool.name for tool in tools}

        self.assertIn("create_project", names)
        self.assertIn("open_project", names)
        self.assertIn("save_project", names)
        self.assertIn("close_project", names)
        self.assertIn("set_active_design", names)
        self.assertIn("get_design_summary", names)

    def test_create_save_open_and_close_project_inside_managed_root(self) -> None:
        created = self.service.create_project(
            project_name="PatchTeamDemo",
            relative_path="team/PatchTeamDemo.aedt",
        )

        self.assertEqual("ok", created["status"])
        project_path = Path(created["data"]["project_path"])
        self.assertEqual(self.tmp / "projects" / "team" / "PatchTeamDemo.aedt", project_path)
        self.assertTrue(created["data"]["project_loaded"])

        saved = self.service.save_project()
        self.assertEqual("ok", saved["status"])
        self.assertTrue(project_path.exists())

        closed = self.service.close_project()
        self.assertEqual("ok", closed["status"])
        self.assertFalse(closed["data"]["project_loaded"])

        opened = self.service.open_project(relative_path="team/PatchTeamDemo.aedt")
        self.assertEqual("ok", opened["status"])
        self.assertEqual(str(project_path), opened["data"]["project_path"])
        self.assertEqual("PatchTeamDemo", opened["data"]["project_name"])

    def test_project_paths_cannot_escape_managed_project_root(self) -> None:
        blocked = self.service.create_project(
            project_name="Escape",
            relative_path="../Escape.aedt",
        )

        self.assertEqual("error", blocked["status"])
        self.assertEqual("InputValidationError", blocked["data"]["error_type"])

    def test_design_list_active_design_and_summary_are_managed_per_project(self) -> None:
        self.service.create_project(project_name="DesignDemo")

        first = self.service.create_hfss_design("PatchA", solution_type="DrivenModal")
        second = self.service.create_hfss_design("PatchB", solution_type="Terminal")

        self.assertEqual("ok", first["status"])
        self.assertEqual("ok", second["status"])
        self.assertEqual(["PatchA", "PatchB"], second["data"]["designs"])
        self.assertEqual("PatchB", second["data"]["active_design"])

        self.service.create_patch_antenna(name="B_Antenna", frequency_ghz=2.4)
        summary = self.service.get_design_summary()
        self.assertEqual("PatchB", summary["data"]["design_name"])
        self.assertEqual(7, summary["data"]["object_count"])

        switched = self.service.set_active_design("PatchA")
        self.assertEqual("ok", switched["status"])
        self.assertEqual("PatchA", switched["data"]["active_design"])

        empty_summary = self.service.get_design_summary()
        self.assertEqual("PatchA", empty_summary["data"]["design_name"])
        self.assertEqual(0, empty_summary["data"]["object_count"])

    def test_unknown_active_design_returns_structured_error(self) -> None:
        self.service.create_project(project_name="DesignDemo")

        result = self.service.set_active_design("MissingDesign")

        self.assertEqual("error", result["status"])
        self.assertEqual("BackendStateError", result["data"]["error_type"])


if __name__ == "__main__":
    unittest.main()
