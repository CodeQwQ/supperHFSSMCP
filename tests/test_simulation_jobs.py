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


class FailingRunBackend(MockHfssBackend):
    def run_simulation(self, setup_name: str) -> dict:
        self._active_design_state()
        return {
            "setup_name": setup_name,
            "status": "failed",
            "failure_reason": "Mock backend forced a solve failure.",
        }


class SimulationJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="hfss-agent-sim-"))
        self.service = HfssService(MockHfssBackend(), output_root=self.tmp)
        self.service.connect_hfss(owner="alice")
        self.service.create_project(project_name="SimulationDemo")
        self.service.create_hfss_design(design_name="Patch2G4")
        self.service.create_patch_antenna(name="Patch2G4", frequency_ghz=2.4)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_simulation_tools_are_registered(self) -> None:
        app = create_app(ServerConfig(backend="mock"))
        tools = asyncio.run(app.list_tools())
        names = {tool.name for tool in tools}

        self.assertIn("create_frequency_sweep", names)
        self.assertIn("get_simulation_job", names)

    def test_setup_and_frequency_sweep_are_managed_independently(self) -> None:
        setup = self.service.create_simulation_setup(
            setup_name="Setup1",
            frequency_ghz=2.4,
            max_delta_s=0.02,
            max_passes=8,
            min_passes=2,
        )

        self.assertEqual("ok", setup["status"])
        self.assertEqual("Setup1", setup["data"]["setup_name"])
        self.assertEqual(0.02, setup["data"]["adaptive"]["max_delta_s"])
        self.assertEqual(8, setup["data"]["adaptive"]["max_passes"])

        sweep = self.service.create_frequency_sweep(
            setup_name="Setup1",
            sweep_name="FineSweep",
            sweep_start_ghz=2.0,
            sweep_stop_ghz=3.0,
            sweep_points=501,
            sweep_type="Interpolating",
        )

        self.assertEqual("ok", sweep["status"])
        self.assertEqual("FineSweep", sweep["data"]["sweep_name"])
        self.assertEqual("Interpolating", sweep["data"]["sweep_type"])

        summary = self.service.get_design_summary()
        self.assertEqual(["Setup1"], summary["data"]["setups"])

    def test_validate_design_returns_structured_warnings_and_errors(self) -> None:
        validation = self.service.validate_design()

        self.assertEqual("ok", validation["status"])
        self.assertFalse(validation["data"]["valid"])
        self.assertEqual([], validation["data"]["errors"])
        self.assertTrue(validation["data"]["warnings"])

    def test_synchronous_run_creates_completed_job_record(self) -> None:
        self.service.create_simulation_setup("Setup1", frequency_ghz=2.4)
        self.service.create_frequency_sweep(
            setup_name="Setup1",
            sweep_name="Sweep1",
            sweep_start_ghz=2.0,
            sweep_stop_ghz=3.0,
            sweep_points=101,
        )

        run = self.service.run_simulation("Setup1", wait_for_completion=True)

        self.assertEqual("ok", run["status"])
        self.assertEqual("completed", run["data"]["job"]["status"])
        self.assertEqual("Setup1", run["data"]["job"]["setup_name"])
        self.assertIsNotNone(run["data"]["job"]["started_at"])
        self.assertIsNotNone(run["data"]["job"]["finished_at"])

        job_id = run["data"]["job"]["job_id"]
        job = self.service.get_simulation_job(job_id)
        self.assertEqual("completed", job["data"]["job"]["status"])

    def test_failed_backend_result_marks_job_failed(self) -> None:
        service = HfssService(FailingRunBackend(), output_root=self.tmp)
        service.connect_hfss(owner="alice")
        service.create_project(project_name="FailureDemo")
        service.create_hfss_design(design_name="Patch2G4")
        service.create_patch_antenna(name="Patch2G4", frequency_ghz=2.4)
        service.create_simulation_setup("Setup1", frequency_ghz=2.4)

        run = service.run_simulation("Setup1", wait_for_completion=True)

        self.assertEqual("ok", run["status"])
        self.assertEqual("failed", run["data"]["status"])
        self.assertEqual("failed", run["data"]["job"]["status"])
        self.assertEqual("Mock backend forced a solve failure.", run["data"]["job"]["failure_reason"])

    def test_async_run_creates_queryable_running_job_record(self) -> None:
        self.service.create_simulation_setup("Setup1", frequency_ghz=2.4)

        run = self.service.run_simulation("Setup1", wait_for_completion=False)

        self.assertEqual("ok", run["status"])
        self.assertEqual("running", run["data"]["job"]["status"])
        self.assertIn("get_simulation_job", run["next_actions"])

        job = self.service.get_simulation_job(run["data"]["job"]["job_id"])
        self.assertEqual("running", job["data"]["job"]["status"])

    def test_unknown_job_returns_structured_error(self) -> None:
        result = self.service.get_simulation_job("missing-job")

        self.assertEqual("error", result["status"])
        self.assertEqual("JobError", result["data"]["error_type"])


if __name__ == "__main__":
    unittest.main()
