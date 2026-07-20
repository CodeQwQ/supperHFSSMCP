from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hfss_agent_mcp.backends.mock import MockHfssBackend
from hfss_agent_mcp.core.results import analyze_s_parameter_points
from hfss_agent_mcp.core.service import HfssService


class ResultsAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="hfss-agent-results-"))
        self.service = HfssService(MockHfssBackend(), output_root=self.tmp)
        self.service.connect_hfss(owner="alice")
        self.service.create_project(project_name="ResultsDemo")
        self.service.create_hfss_design(design_name="Patch2G4")
        self.service.create_patch_antenna(name="Patch2G4", frequency_ghz=2.4)
        self.service.create_simulation_setup(
            setup_name="Setup1",
            frequency_ghz=2.4,
            sweep_start_ghz=2.0,
            sweep_stop_ghz=3.0,
            sweep_points=101,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_analysis_finds_resonance_bandwidth_vswr_and_target_judgment(self) -> None:
        result = analyze_s_parameter_points(
            [
                {"frequency_ghz": 2.0, "value_db": -5.0},
                {"frequency_ghz": 2.3, "value_db": -11.0},
                {"frequency_ghz": 2.4, "value_db": -18.0},
                {"frequency_ghz": 2.5, "value_db": -12.0},
                {"frequency_ghz": 3.0, "value_db": -4.0},
            ],
            target_frequency_ghz=2.4,
            threshold_db=-10.0,
        )

        self.assertEqual(2.4, result["resonance_frequency_ghz"])
        self.assertEqual(-18.0, result["minimum_value_db"])
        self.assertEqual(2.4, result["target"]["frequency_ghz"])
        self.assertTrue(result["target"]["passed"])
        self.assertGreater(result["bandwidth_ghz"], 0.0)
        self.assertGreater(result["vswr_at_resonance"], 1.0)

    def test_service_exposes_analysis_and_report_export(self) -> None:
        self.service.run_simulation("Setup1")

        analysis = self.service.analyze_s_parameters(
            setup_name="Setup1",
            target_frequency_ghz=2.4,
            threshold_db=-10.0,
        )

        self.assertEqual("ok", analysis["status"])
        self.assertTrue(analysis["data"]["analysis"]["target"]["passed"])

        report = self.service.export_result_report(
            setup_name="Setup1",
            relative_path="results/patch2g4.json",
            target_frequency_ghz=2.4,
        )

        self.assertEqual("ok", report["status"])
        report_path = self.tmp / "results" / "patch2g4.json"
        self.assertTrue(report_path.exists())
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual("Setup1", payload["result"]["setup_name"])

    def test_report_export_supports_csv(self) -> None:
        self.service.run_simulation("Setup1")
        report = self.service.export_result_report(
            setup_name="Setup1",
            relative_path="results/patch2g4.csv",
        )

        self.assertEqual("ok", report["status"])
        with (self.tmp / "results" / "patch2g4.csv").open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual("2.4", rows[1]["frequency_ghz"])
        self.assertEqual("-18.0", rows[1]["value_db"])

    def test_service_analyzes_input_impedance_expression(self) -> None:
        result = self.service.analyze_input_impedance(
            setup_name="Setup1",
            target_frequency_ghz=2.4,
        )

        self.assertEqual("ok", result["status"])
        target = result["data"]["analysis"]["target"]
        self.assertEqual(48.0, target["real_ohms"])
        self.assertEqual(3.0, target["imag_ohms"])


if __name__ == "__main__":
    unittest.main()
