from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hfss_agent_mcp.backends.mock import MockHfssBackend
from hfss_agent_mcp.core.service import HfssService


class ModelingAtomTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="hfss-agent-modeling-"))
        self.service = HfssService(MockHfssBackend(), output_root=self.tmp)
        self.service.connect_hfss(owner="alice")
        self.service.create_project(project_name="ModelingAtoms")
        self.service.create_hfss_design(design_name="Atoms")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_box_and_sheet_are_visible_in_design_summary(self) -> None:
        box = self.service.create_model_box(
            name="Substrate",
            origin_mm=[-20.0, -15.0, 0.0],
            size_mm=[40.0, 30.0, 1.6],
            material="FR4_epoxy",
            role="substrate",
        )
        sheet = self.service.create_model_sheet(
            name="Patch",
            orientation="XY",
            origin_mm=[-10.0, -8.0, 1.6],
            size_mm=[20.0, 16.0],
            material="copper",
            role="patch",
        )

        summary = self.service.get_design_summary()

        self.assertEqual("ok", box["status"])
        self.assertEqual("ok", sheet["status"])
        objects = summary["data"]["object_details"]
        self.assertEqual("FR4_epoxy", objects["Substrate"]["material"])
        self.assertEqual("substrate", objects["Substrate"]["role"])
        self.assertEqual("sheet", objects["Patch"]["kind"])
        self.assertEqual("patch", objects["Patch"]["role"])

    def test_boundaries_and_lumped_port_are_visible_in_summary(self) -> None:
        self.service.create_model_sheet(
            name="ArmPositive",
            orientation="XY",
            origin_mm=[1.0, -1.0, 0.0],
            size_mm=[30.0, 2.0],
            material="copper",
            role="radiator",
        )
        self.service.create_model_sheet(
            name="PortSheet",
            orientation="XZ",
            origin_mm=[0.0, -1.0, 0.0],
            size_mm=[1.0, 2.0],
            material="air",
            role="port",
        )
        self.service.create_model_box(
            name="Airbox",
            origin_mm=[-40.0, -40.0, -40.0],
            size_mm=[80.0, 80.0, 80.0],
            material="air",
            role="airbox",
        )

        perfect = self.service.assign_perfect_e(
            name="ArmPerfectE",
            object_names=["ArmPositive"],
        )
        radiation = self.service.assign_radiation_boundary(
            name="AirRadiation",
            object_names=["Airbox"],
        )
        port = self.service.create_lumped_port(
            name="FeedPort",
            sheet_name="PortSheet",
            integration_start_mm=[0.0, 0.0, 0.0],
            integration_end_mm=[0.0, 1.0, 0.0],
        )

        summary = self.service.get_design_summary()

        self.assertEqual("ok", perfect["status"])
        self.assertEqual("ok", radiation["status"])
        self.assertEqual("ok", port["status"])
        self.assertEqual("perfect_e", summary["data"]["boundaries"]["ArmPerfectE"]["boundary_type"])
        self.assertEqual("radiation", summary["data"]["boundaries"]["AirRadiation"]["boundary_type"])
        self.assertEqual("lumped", summary["data"]["ports"]["FeedPort"]["port_type"])
        self.assertEqual("PortSheet", summary["data"]["ports"]["FeedPort"]["objects"][0])

    def test_set_material_and_delete_explicit_object_names(self) -> None:
        self.service.create_model_box(
            name="TunableBlock",
            origin_mm=[0.0, 0.0, 0.0],
            size_mm=[1.0, 1.0, 1.0],
            material="air",
        )

        material = self.service.set_object_material("TunableBlock", "FR4_epoxy")
        deleted = self.service.delete_model_objects(["TunableBlock"])
        missing = self.service.delete_model_objects(["TunableBlock"])

        self.assertEqual("ok", material["status"])
        self.assertEqual("FR4_epoxy", material["data"]["material"])
        self.assertEqual("ok", deleted["status"])
        self.assertEqual(["TunableBlock"], deleted["data"]["deleted_objects"])
        self.assertEqual("error", missing["status"])
        self.assertEqual("BackendStateError", missing["data"]["error_type"])

    def test_atomic_modeling_can_pass_mock_validation_after_setup(self) -> None:
        self.service.create_model_sheet(
            name="Radiator",
            orientation="XY",
            origin_mm=[-10.0, -1.0, 0.0],
            size_mm=[20.0, 2.0],
            material="copper",
            role="radiator",
        )
        self.service.create_model_sheet(
            name="PortSheet",
            orientation="XZ",
            origin_mm=[0.0, -1.0, 0.0],
            size_mm=[1.0, 2.0],
            material="air",
            role="port",
        )
        self.service.create_model_box(
            name="Airbox",
            origin_mm=[-30.0, -30.0, -30.0],
            size_mm=[60.0, 60.0, 60.0],
            material="air",
            role="airbox",
        )
        self.service.assign_perfect_e("RadiatorPerfectE", ["Radiator"])
        self.service.assign_radiation_boundary("AirRadiation", ["Airbox"])
        self.service.create_lumped_port(
            "FeedPort",
            "PortSheet",
            [0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        )
        self.service.create_simulation_setup("Setup1", frequency_ghz=2.4)

        validation = self.service.validate_design()

        self.assertTrue(validation["data"]["valid"])

    def test_missing_port_radiation_or_setup_blocks_simulation(self) -> None:
        self.service.create_model_sheet(
            name="Radiator",
            orientation="XY",
            origin_mm=[-10.0, -1.0, 0.0],
            size_mm=[20.0, 2.0],
            material="copper",
            role="radiator",
        )
        self.service.create_simulation_setup("Setup1", frequency_ghz=2.4)

        validation = self.service.validate_design()
        run = self.service.run_simulation("Setup1")

        self.assertFalse(validation["data"]["valid"])
        self.assertTrue(any("port" in item.lower() for item in validation["data"]["warnings"]))
        self.assertTrue(any("radiation" in item.lower() for item in validation["data"]["warnings"]))
        self.assertEqual("failed", run["data"]["status"])
        self.assertIn("validation", run["data"])


if __name__ == "__main__":
    unittest.main()
