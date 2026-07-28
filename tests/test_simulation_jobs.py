from __future__ import annotations

import asyncio
import queue
import shutil
import sys
import tempfile
import threading
import time
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


class InvalidValidationBackend(MockHfssBackend):
    def __init__(self) -> None:
        super().__init__()
        self.run_called = False

    def validate_design(self) -> dict:
        return {
            "valid": False,
            "errors": ["HFSS validation: object has no excitation."],
            "warnings": [],
            "messages": ["HFSS validation: object has no excitation."],
        }

    def run_simulation(self, setup_name: str) -> dict:
        self.run_called = True
        return super().run_simulation(setup_name)


class UnprovenValidationBackend(MockHfssBackend):
    def __init__(self) -> None:
        super().__init__()
        self.run_called = False

    def validate_design(self) -> dict:
        return {
            "valid": True,
            "errors": [],
            "warnings": [],
            "messages": [],
        }

    def run_simulation(self, setup_name: str) -> dict:
        self.run_called = True
        return super().run_simulation(setup_name)


class BlockingSimulationBackend(MockHfssBackend):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def run_simulation(self, setup_name: str) -> dict:
        self.started.set()
        if not self.release.wait(timeout=5):
            raise AssertionError("test did not release the simulated solver")
        return super().run_simulation(setup_name)


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

    def test_run_simulation_tool_schema_has_no_fake_async_flag(self) -> None:
        app = create_app(ServerConfig(backend="mock"))
        tools = asyncio.run(app.list_tools())
        run_tool = next(tool for tool in tools if tool.name == "run_simulation")

        self.assertEqual(["setup_name"], sorted(run_tool.inputSchema["properties"]))

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

    def test_run_returns_trackable_job_record(self) -> None:
        self.service.create_simulation_setup("Setup1", frequency_ghz=2.4)
        self.service.create_frequency_sweep(
            setup_name="Setup1",
            sweep_name="Sweep1",
            sweep_start_ghz=2.0,
            sweep_stop_ghz=3.0,
            sweep_points=101,
        )

        run = self.service.run_simulation("Setup1")

        self.assertEqual("ok", run["status"])
        self.assertEqual("Setup1", run["data"]["job"]["setup_name"])
        self.assertIsNotNone(run["data"]["job"]["started_at"])

        job_id = run["data"]["job"]["job_id"]
        deadline = time.time() + 2
        while time.time() < deadline:
            job = self.service.get_simulation_job(job_id)
            if job["data"]["job"]["status"] == "completed":
                break
            time.sleep(0.01)
        job = self.service.get_simulation_job(job_id)
        self.assertEqual("completed", job["data"]["job"]["status"])
        self.assertIsNotNone(job["data"]["job"]["finished_at"])

    def test_failed_backend_result_marks_job_failed(self) -> None:
        service = HfssService(FailingRunBackend(), output_root=self.tmp)
        service.connect_hfss(owner="alice")
        service.create_project(project_name="FailureDemo")
        service.create_hfss_design(design_name="Patch2G4")
        service.create_patch_antenna(name="Patch2G4", frequency_ghz=2.4)
        service.create_simulation_setup("Setup1", frequency_ghz=2.4)

        run = service.run_simulation("Setup1")

        self.assertEqual("ok", run["status"])
        job_id = run["data"]["job"]["job_id"]
        deadline = time.time() + 2
        while time.time() < deadline:
            job = service.get_simulation_job(job_id)["data"]["job"]
            if job["status"] == "failed":
                break
            time.sleep(0.01)
        job = service.get_simulation_job(job_id)["data"]["job"]
        self.assertEqual("failed", job["status"])
        self.assertEqual("Mock backend forced a solve failure.", job["failure_reason"])

    def test_run_simulation_stops_before_solver_when_validation_fails(self) -> None:
        backend = InvalidValidationBackend()
        service = HfssService(backend, output_root=self.tmp)
        service.connect_hfss(owner="alice")
        service.create_project(project_name="InvalidBeforeSolve")
        service.create_hfss_design(design_name="DipoleInvalid")
        service.create_dipole_antenna(name="DipoleInvalid", frequency_ghz=2.4)
        service.create_simulation_setup("Setup1", frequency_ghz=2.4)

        run = service.run_simulation("Setup1")

        self.assertEqual("ok", run["status"])
        self.assertEqual("failed", run["data"]["status"])
        self.assertFalse(backend.run_called)
        self.assertIn("validation", run["data"])
        self.assertIn("object has no excitation", run["data"]["failure_reason"])

    def test_run_simulation_rejects_validation_without_execution_evidence(self) -> None:
        backend = UnprovenValidationBackend()
        service = HfssService(backend, output_root=self.tmp)
        service.connect_hfss(owner="alice")
        service.create_project(project_name="UnprovenValidation")
        service.create_hfss_design(design_name="DipoleUnproven")
        service.create_dipole_antenna(name="DipoleUnproven", frequency_ghz=2.4)
        service.create_simulation_setup("Setup1", frequency_ghz=2.4)

        run = service.run_simulation("Setup1")

        self.assertEqual("ok", run["status"])
        self.assertEqual("failed", run["data"]["status"])
        self.assertFalse(backend.run_called)
        self.assertIn("did not include execution evidence", run["data"]["failure_reason"])

    def test_run_simulation_always_invokes_backend_solver(self) -> None:
        self.service.create_simulation_setup("Setup1", frequency_ghz=2.4)

        run = self.service.run_simulation("Setup1")

        self.assertEqual("ok", run["status"])
        self.assertIn("Real HFSS solver execution was submitted", run["data"]["backend_note"])
        self.assertIn("get_simulation_job", run["next_actions"])

        job = self.service.get_simulation_job(run["data"]["job"]["job_id"])
        deadline = time.time() + 2
        while time.time() < deadline and job["data"]["job"]["status"] == "running":
            time.sleep(0.01)
            job = self.service.get_simulation_job(run["data"]["job"]["job_id"])
        self.assertEqual("completed", job["data"]["job"]["status"])
        self.assertEqual("Mock backend did not invoke AEDT.", job["data"]["job"]["result"]["backend_note"])

    def test_long_solver_runs_after_mcp_request_returns_and_job_can_be_recovered(self) -> None:
        backend = BlockingSimulationBackend()
        service = HfssService(backend, output_root=self.tmp)
        service.connect_hfss(owner="alice")
        service.create_project(project_name="LongSolve")
        service.create_hfss_design(design_name="LongSolveDesign")
        service.create_patch_antenna(name="LongSolveDesign", frequency_ghz=2.4)
        service.create_simulation_setup("Setup1", frequency_ghz=2.4)

        responses: queue.Queue[dict] = queue.Queue()
        request = threading.Thread(
            target=lambda: responses.put(service.run_simulation("Setup1")),
            daemon=True,
        )
        request.start()

        self.assertTrue(backend.started.wait(timeout=2), "real backend solver was not invoked")
        run = responses.get(timeout=2)
        self.assertEqual("ok", run["status"])
        self.assertEqual("running", run["data"]["job"]["status"])
        job_id = run["data"]["job"]["job_id"]
        self.assertFalse(request.is_alive(), "MCP request remained blocked by the solver")

        backend.release.set()
        request.join(timeout=2)
        deadline = time.time() + 2
        while time.time() < deadline:
            job = service.get_simulation_job(job_id)["data"]["job"]
            if job["status"] == "completed":
                break
            time.sleep(0.01)
        self.assertEqual("completed", service.get_simulation_job(job_id)["data"]["job"]["status"])

    def test_job_record_survives_service_recreation_for_reconnect(self) -> None:
        self.service.create_simulation_setup("Setup1", frequency_ghz=2.4)
        run = self.service.run_simulation("Setup1")
        job_id = run["data"]["job"]["job_id"]
        deadline = time.time() + 2
        while time.time() < deadline:
            job = self.service.get_simulation_job(job_id)["data"]["job"]
            if job["status"] == "completed":
                break
            time.sleep(0.01)

        recovered_service = HfssService(MockHfssBackend(), output_root=self.tmp)
        recovered = recovered_service.get_simulation_job(job_id)

        self.assertEqual("ok", recovered["status"])
        self.assertEqual("completed", recovered["data"]["job"]["status"])

    def test_release_connection_is_deferred_while_real_solver_is_running(self) -> None:
        backend = BlockingSimulationBackend()
        service = HfssService(backend, output_root=self.tmp)
        connected = service.connect_hfss(owner="alice")
        service.create_project(project_name="ReleaseGuard")
        service.create_hfss_design(design_name="ReleaseGuardDesign")
        service.create_patch_antenna(name="ReleaseGuardDesign", frequency_ghz=2.4)
        service.create_simulation_setup("Setup1", frequency_ghz=2.4)
        run = service.run_simulation("Setup1")
        self.assertTrue(backend.started.wait(timeout=2))

        release = service.release_connection(connected["data"]["session"]["session_id"])

        self.assertEqual("error", release["status"])
        self.assertIn("while a simulation is running", release["message"])
        backend.release.set()
        job_id = run["data"]["job"]["job_id"]
        deadline = time.time() + 2
        while time.time() < deadline and service.get_simulation_job(job_id)["data"]["job"]["status"] == "running":
            time.sleep(0.01)
        self.assertEqual("completed", service.get_simulation_job(job_id)["data"]["job"]["status"])

    def test_unknown_job_returns_structured_error(self) -> None:
        result = self.service.get_simulation_job("missing-job")

        self.assertEqual("error", result["status"])
        self.assertEqual("JobError", result["data"]["error_type"])


if __name__ == "__main__":
    unittest.main()
