from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from antenna_design_intelligence_mcp.config import ServerConfig
from antenna_design_intelligence_mcp.server import create_app


class McpRegistrationTests(unittest.TestCase):
    def test_expected_tools_are_registered(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            config = ServerConfig(input_roots=(root / "inputs",), output_root=root / "outputs")
            tools = asyncio.run(create_app(config).list_tools())
            self.assertEqual(
                {tool.name for tool in tools},
                {
                    "inspect_input",
                    "list_providers",
                    "extract_document_evidence",
                    "extract_antenna_design_spec",
                    "get_extraction_artifact",
                },
            )

    def test_chinese_workbook_resources_are_registered(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            config = ServerConfig(input_roots=(root / "inputs",), output_root=root / "outputs")
            resources = asyncio.run(create_app(config).list_resources())
            uris = {str(resource.uri) for resource in resources}
            self.assertIn("antenna://handbook/extraction-workflow", uris)
            self.assertIn("antenna://handbook/spec-fields", uris)

    def test_direct_tool_and_resource_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            config = ServerConfig(input_roots=(root / "inputs",), output_root=root / "outputs")
            app = create_app(config)

            async def invoke() -> None:
                _, payload = await app.call_tool("list_providers", {})
                self.assertTrue(payload["success"])
                contents = await app.read_resource("antenna://handbook/extraction-workflow")
                self.assertIn("validate_design", str(contents))

            asyncio.run(invoke())


if __name__ == "__main__":
    unittest.main()
