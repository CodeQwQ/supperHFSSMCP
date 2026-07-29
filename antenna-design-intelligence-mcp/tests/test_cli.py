from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_list_tools_exits_zero_and_lists_inspection_tool(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "antenna_design_intelligence_mcp", "list-tools"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("inspect_input", completed.stdout.splitlines())


class DeploymentDocumentTests(unittest.TestCase):
    def test_deployment_guide_declares_no_bundled_model(self) -> None:
        guide = (ROOT / "docs" / "部署指南.md").read_text(encoding="utf-8")
        self.assertIn("首版不包含 OCR/VLM 模型", guide)
        self.assertIn("ANTENNA_INTELLIGENCE_ENABLE_VERIFICATION_PROVIDER", guide)


if __name__ == "__main__":
    unittest.main()
