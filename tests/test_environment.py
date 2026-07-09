from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hfss_agent_mcp.backends.mock import MockHfssBackend
from hfss_agent_mcp.config import ServerConfig
from hfss_agent_mcp.core.service import HfssService
from hfss_agent_mcp.server import create_app


class EnvironmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="hfss-agent-env-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_env_check_tool_is_registered(self) -> None:
        app = create_app(ServerConfig(backend="mock"))
        tools = asyncio.run(app.list_tools())
        names = {tool.name for tool in tools}
        self.assertIn("env_check", names)

    def test_env_check_reports_runtime_backend_and_missing_aedt(self) -> None:
        service = HfssService(
            MockHfssBackend(),
            output_root=self.tmp,
            config=ServerConfig(backend="mock", transport="streamable-http", output_root=self.tmp),
        )

        result = service.env_check()

        self.assertEqual("ok", result["status"])
        self.assertEqual("mock", result["data"]["backend"]["configured_backend"])
        self.assertEqual("streamable-http", result["data"]["server"]["transport"])
        self.assertTrue(result["data"]["output"]["exists"])
        self.assertEqual(str(self.tmp.resolve()), result["data"]["output"]["root"])
        self.assertGreaterEqual(result["data"]["python"]["major"], 3)
        self.assertIn("mcp", result["data"]["packages"])
        self.assertIn("pydantic", result["data"]["packages"])
        self.assertIn("pyaedt", result["data"]["packages"])
        self.assertFalse(result["data"]["aedt"]["available"])
        self.assertTrue(any("AEDT executable" in item for item in result["warnings"]))

    def test_health_check_includes_environment_summary(self) -> None:
        service = HfssService(
            MockHfssBackend(),
            output_root=self.tmp,
            config=ServerConfig(backend="mock", transport="stdio", output_root=self.tmp),
        )

        result = service.health_check()

        self.assertEqual("ok", result["status"])
        self.assertIn("environment", result["data"])
        self.assertEqual("stdio", result["data"]["environment"]["server"]["transport"])
        self.assertIn("env_check", result["next_actions"])

    def test_server_config_reads_environment_variables(self) -> None:
        with patch.dict(
            os.environ,
            {
                "HFSS_AGENT_BACKEND": "pyaedt",
                "HFSS_AGENT_MCP_TRANSPORT": "streamable-http",
                "HFSS_AGENT_MCP_HOST": "0.0.0.0",
                "HFSS_AGENT_MCP_PORT": "9001",
                "HFSS_AGENT_LOG_LEVEL": "DEBUG",
                "HFSS_AGENT_OUTPUT_ROOT": str(self.tmp / "out"),
                "HFSS_AGENT_AEDT_EXECUTABLE": "C:\\Program Files\\AnsysEM\\v252\\Win64\\ansysedt.exe",
                "HFSS_AGENT_CONNECT_TIMEOUT_SECONDS": "12.5",
            },
            clear=False,
        ):
            config = ServerConfig.from_env()

        self.assertEqual("pyaedt", config.backend)
        self.assertEqual("streamable-http", config.transport)
        self.assertEqual("0.0.0.0", config.host)
        self.assertEqual(9001, config.port)
        self.assertEqual("DEBUG", config.log_level)
        self.assertEqual(self.tmp / "out", config.output_root)
        self.assertEqual(
            Path("C:\\Program Files\\AnsysEM\\v252\\Win64\\ansysedt.exe"),
            config.aedt_executable,
        )
        self.assertEqual(12.5, config.connect_timeout_seconds)


if __name__ == "__main__":
    unittest.main()
