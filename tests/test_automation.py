from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hfss_agent_mcp.backends.cli_runner import CliRunner
from hfss_agent_mcp.backends.com import ComAdapter
from hfss_agent_mcp.core.scripts import ScriptRegistry


class AutomationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="hfss-agent-automation-"))
        (self.tmp / "probe.py").write_text("print('probe')\n", encoding="utf-8")
        self.registry = ScriptRegistry(self.tmp)
        self.registry.register("probe", "probe.py")

    def tearDown(self) -> None:
        for path in self.tmp.rglob("*"):
            if path.is_file():
                path.unlink()
        for path in sorted(self.tmp.rglob("*"), reverse=True):
            if path.is_dir():
                path.rmdir()
        self.tmp.rmdir()

    def test_registry_rejects_script_escape(self) -> None:
        with self.assertRaises(ValueError):
            self.registry.register("escape", "../outside.py")

    def test_cli_runner_uses_argument_list_without_shell(self) -> None:
        runner = CliRunner(Path("ansysedt.exe"), self.tmp)
        definition = self.registry.require("probe")

        with patch("hfss_agent_mcp.backends.cli_runner.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "ok"
            run.return_value.stderr = ""
            result = runner.run_native(definition, {"project": "safe"})

        command = run.call_args.args[0]
        self.assertIsInstance(command, list)
        self.assertIn("-RunScriptAndExit", command)
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertEqual(0, result["return_code"])

    def test_pyaedt_runner_uses_ironpython_to_enter_aedt(self) -> None:
        runner = CliRunner(Path("pyaedt.exe"), self.tmp)
        definition = self.registry.require("probe")

        with patch("hfss_agent_mcp.backends.cli_runner.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "ok"
            run.return_value.stderr = ""
            runner.run_pyaedt(definition, {}, 50051, registry=self.registry)

        command = run.call_args.args[0]
        self.assertIn("--ironpython", command)

    def test_cli_runner_rejects_unregistered_script_definition(self) -> None:
        runner = CliRunner(Path("ansysedt.exe"), self.tmp)
        definition = self.registry.require("probe")
        definition.path = self.tmp / "outside.py"

        with self.assertRaises(ValueError):
            runner.run_native(definition, {})

    def test_com_adapter_calls_registered_script(self) -> None:
        class FakeDesktop:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def RunScript(self, path: str) -> bool:
                self.calls.append(path)
                return True

        desktop = FakeDesktop()
        result = ComAdapter(self.tmp).run(desktop, self.registry.require("probe"), {})

        self.assertTrue(result["success"])
        self.assertEqual([str(self.tmp / "probe.py")], desktop.calls)


if __name__ == "__main__":
    unittest.main()
