from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hfss_agent_mcp.config import ServerConfig
from hfss_agent_mcp.server import create_app


class McpRegistrationTests(unittest.TestCase):
    def test_expected_tools_are_registered(self) -> None:
        app = create_app(ServerConfig(backend="mock"))
        tools = asyncio.run(app.list_tools())
        names = {tool.name for tool in tools}
        self.assertEqual(
            {
                "health_check",
                "env_check",
                "list_aedt_sessions",
                "launch_aedt",
                "get_session_info",
                "release_connection",
                "connect_hfss",
                "get_project_info",
                "create_project",
                "open_project",
                "save_project",
                "close_project",
                "create_hfss_design",
                "set_active_design",
                "get_design_summary",
                "create_model_box",
                "create_model_sheet",
                "set_object_material",
                "assign_perfect_e",
                "assign_radiation_boundary",
                "create_lumped_port",
                "delete_model_objects",
                "create_patch_antenna",
                "create_dipole_antenna",
                "set_design_variable",
                "optimize_design_variable",
                "create_simulation_setup",
                "create_frequency_sweep",
                "validate_design",
                "run_simulation",
                "get_simulation_job",
                "get_s_parameters",
                "export_touchstone",
                "analyze_s_parameters",
                "analyze_input_impedance",
                "export_result_report",
                "list_automation_scripts",
                "run_automation_script",
            },
            names,
        )


if __name__ == "__main__":
    unittest.main()
