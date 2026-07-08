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
                "connect_hfss",
                "get_project_info",
                "create_hfss_design",
                "create_patch_antenna",
                "create_simulation_setup",
                "validate_design",
                "run_simulation",
                "get_s_parameters",
                "export_touchstone",
            },
            names,
        )


if __name__ == "__main__":
    unittest.main()
