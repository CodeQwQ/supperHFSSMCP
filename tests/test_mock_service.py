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


class MockServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="hfss-agent-mcp-"))
        self.service = HfssService(MockHfssBackend(), output_root=self.tmp)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_patch_antenna_workflow_runs_offline(self) -> None:
        connected = self.service.connect_hfss(design_name="PatchDemo")
        self.assertEqual("ok", connected["status"])

        design = self.service.create_hfss_design(design_name="PatchDemo")
        self.assertEqual("PatchDemo", design["data"]["design_name"])

        antenna = self.service.create_patch_antenna(
            name="Patch2G4",
            frequency_ghz=2.4,
            substrate_material="FR4_epoxy",
            substrate_height_mm=1.6,
        )
        self.assertEqual("ok", antenna["status"])
        self.assertIn("Patch2G4_patch", antenna["data"]["object_names"].values())
        self.assertGreater(antenna["data"]["dimensions_mm"]["patch_width_mm"], 0)

        setup = self.service.create_simulation_setup(
            setup_name="Setup1",
            frequency_ghz=2.4,
            sweep_start_ghz=1.5,
            sweep_stop_ghz=3.5,
            sweep_points=401,
        )
        self.assertEqual("Setup1", setup["data"]["setup_name"])

        validation = self.service.validate_design()
        self.assertTrue(validation["data"]["valid"])

        run = self.service.run_simulation("Setup1")
        self.assertEqual("completed", run["data"]["status"])

        s_params = self.service.get_s_parameters("Setup1")
        self.assertTrue(s_params["data"]["solved"])
        self.assertLess(s_params["data"]["min_value_db"], -10)

    def test_export_touchstone_is_restricted_to_output_root(self) -> None:
        self.service.connect_hfss(design_name="PatchDemo")
        exported = self.service.export_touchstone("demo/result.s1p")
        self.assertEqual("ok", exported["status"])
        self.assertTrue((self.tmp / "demo" / "result.s1p").exists())

        blocked = self.service.export_touchstone("../escape.s1p")
        self.assertEqual("error", blocked["status"])
        self.assertEqual("InputValidationError", blocked["data"]["error_type"])

    def test_dipole_workflow_runs_offline(self) -> None:
        self.service.connect_hfss(design_name="DipoleDemo")
        antenna = self.service.create_dipole_antenna(
            name="Dipole2G4",
            frequency_ghz=2.4,
        )

        self.assertEqual("ok", antenna["status"])
        self.assertEqual("dipole", antenna["data"]["antenna_type"])
        self.assertIn("Dipole2G4_arm_positive", antenna["data"]["object_names"].values())

    def test_design_variable_optimization_runs_bounded_loop(self) -> None:
        self.service.connect_hfss(design_name="OptimizationDemo")
        self.service.create_patch_antenna(name="OptimizationPatch", frequency_ghz=2.4)
        self.service.create_simulation_setup(
            setup_name="Setup1",
            frequency_ghz=2.4,
            sweep_start_ghz=2.0,
            sweep_stop_ghz=2.8,
            sweep_points=5,
        )

        result = self.service.optimize_design_variable(
            variable_name="feed_offset",
            candidate_values=["-1mm", "0mm", "1mm"],
            setup_name="Setup1",
            target_frequency_ghz=2.4,
            max_evaluations=2,
        )

        self.assertEqual("ok", result["status"])
        self.assertEqual(2, result["data"]["evaluation_count"])
        self.assertEqual("max_evaluations", result["data"]["stopped_reason"])
        self.assertIn("feed_offset", self.service.backend.designs["OptimizationDemo"]["variables"])


if __name__ == "__main__":
    unittest.main()
