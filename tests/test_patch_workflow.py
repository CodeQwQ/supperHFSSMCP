from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hfss_agent_mcp.backends.mock import MockHfssBackend
from hfss_agent_mcp.core.models import PatchAntennaSpec
from hfss_agent_mcp.core.service import HfssService
from hfss_agent_mcp.workflows.patch import build_patch_antenna


class PatchWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="hfss-agent-patch-"))
        self.service = HfssService(MockHfssBackend(), output_root=self.tmp)
        self.service.connect_hfss(owner="alice")
        self.service.create_project(project_name="PatchWorkflow")
        self.service.create_hfss_design(design_name="Patch2G4")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_patch_workflow_returns_complete_geometry_recipe(self) -> None:
        recipe = build_patch_antenna(
            PatchAntennaSpec(
                name="Patch2G4",
                frequency_ghz=2.4,
                substrate_material="FR4_epoxy",
                substrate_height_mm=1.6,
            )
        )

        self.assertEqual("Patch2G4", recipe["antenna_name"])
        self.assertEqual("lumped", recipe["ports"][0]["port_type"])
        self.assertEqual("radiation", recipe["boundaries"][0]["boundary_type"])
        self.assertEqual("FR4_epoxy", recipe["materials"]["substrate"])
        self.assertEqual("copper", recipe["materials"]["conductor"])
        self.assertEqual(
            {
                "substrate",
                "ground",
                "patch",
                "feed",
                "airbox",
                "port",
            },
            set(recipe["object_names"]),
        )
        self.assertGreater(recipe["dimensions_mm"]["patch_width_mm"], 35)
        self.assertLess(recipe["dimensions_mm"]["patch_width_mm"], 40)
        self.assertGreater(recipe["dimensions_mm"]["patch_length_mm"], 28)
        self.assertLess(recipe["dimensions_mm"]["patch_length_mm"], 32)
        self.assertGreater(recipe["dimensions_mm"]["airbox_height_mm"], 30)
        self.assertEqual(6, len(recipe["geometry"]))
        port_sheet = next(item for item in recipe["geometry"] if item["role"] == "port")
        self.assertEqual("XZ", port_sheet["metadata"]["orientation"])
        self.assertEqual(("Patch2G4_lumped_port",), recipe["ports"][0]["objects"])

    def test_create_patch_antenna_persists_recipe_on_active_mock_design(self) -> None:
        result = self.service.create_patch_antenna(
            name="Patch2G4",
            frequency_ghz=2.4,
            substrate_material="FR4_epoxy",
            substrate_height_mm=1.6,
            feed_width_mm=3.0,
        )

        self.assertEqual("ok", result["status"])
        self.assertEqual("Patch2G4_lumped_port", result["data"]["object_names"]["port"])
        self.assertEqual("lumped", result["data"]["ports"][0]["port_type"])
        self.assertIn("Patch2G4_airbox", result["data"]["boundaries"][0]["objects"])

        summary = self.service.get_design_summary()
        self.assertEqual(7, summary["data"]["object_count"])
        self.assertIn("Patch2G4", summary["data"]["objects"])
        self.assertIn("Patch2G4_lumped_port", summary["data"]["objects"])

    def test_create_patch_antenna_accepts_manual_dimensions(self) -> None:
        result = self.service.create_patch_antenna(
            name="ManualPatch",
            frequency_ghz=5.8,
            substrate_material="Rogers4350",
            substrate_height_mm=0.762,
            patch_length_mm=12.0,
            patch_width_mm=16.0,
            ground_length_mm=28.0,
            ground_width_mm=32.0,
        )

        dimensions = result["data"]["dimensions_mm"]
        self.assertEqual(12.0, dimensions["patch_length_mm"])
        self.assertEqual(16.0, dimensions["patch_width_mm"])
        self.assertEqual(28.0, dimensions["ground_length_mm"])
        self.assertEqual(32.0, dimensions["ground_width_mm"])


if __name__ == "__main__":
    unittest.main()
