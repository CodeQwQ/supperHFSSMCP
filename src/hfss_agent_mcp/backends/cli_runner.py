from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hfss_agent_mcp.core.scripts import ScriptDefinition, ScriptRegistry


class CliRunner:
    def __init__(self, executable: Path | str, output_root: Path | str, timeout_seconds: float = 300.0) -> None:
        self.executable = Path(executable)
        self.output_root = Path(output_root).resolve()
        self.timeout_seconds = timeout_seconds

    def run_native(
        self,
        definition: ScriptDefinition,
        arguments: dict[str, Any],
        registry: ScriptRegistry | None = None,
        output_path: Path | None = None,
    ) -> dict[str, Any]:
        self._validate_script(definition, registry)
        return self._run(
            [str(self.executable), "-RunScriptAndExit", str(definition.path)],
            definition,
            arguments,
            registry,
            output_path,
        )

    def run_pyaedt(
        self,
        definition: ScriptDefinition,
        arguments: dict[str, Any],
        port: int,
        registry: ScriptRegistry | None = None,
        output_path: Path | None = None,
        student_version: bool = False,
        student_bridge: Path | None = None,
    ) -> dict[str, Any]:
        self._validate_script(definition, registry)
        if student_version and student_bridge is not None:
            command = [sys.executable, str(student_bridge), "--port", str(port)]
        else:
            command = [
                str(self.executable),
                "run",
                str(definition.path),
                "--port",
                str(port),
                "--ironpython",
            ]
        return self._run(
            command,
            definition,
            arguments,
            registry,
            output_path,
        )

    def run_batch_solve(self, project_path: Path) -> dict[str, Any]:
        project = project_path.resolve()
        if project.suffix.lower() != ".aedt" or not project.is_file():
            raise ValueError("BatchSolve requires an existing .aedt project file")
        return self._run_command([str(self.executable), "-BatchSolve", str(project)])

    def _run(
        self,
        command: list[str],
        definition: ScriptDefinition,
        arguments: dict[str, Any],
        registry: ScriptRegistry | None,
        output_path: Path | None,
    ) -> dict[str, Any]:
        output = (output_path or self.output_root / "scripts" / f"{definition.script_id}.json").resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        if registry is not None:
            environment.update(registry.build_environment(definition, arguments, output))
        return self._run_command(command, environment=environment, artifact_path=output)

    def _run_command(
        self,
        command: list[str],
        environment: dict[str, str] | None = None,
        artifact_path: Path | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        log_path = self._log_path(command)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                shell=False,
                check=False,
                timeout=self.timeout_seconds,
                env=environment,
            )
            result = {
                "success": completed.returncode == 0,
                "command": command,
                "return_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "duration_seconds": round(time.monotonic() - started, 3),
                "log_path": str(log_path),
                "artifact": self._read_artifact(artifact_path),
            }
            self._write_log(log_path, result["stdout"], result["stderr"], result["return_code"])
            return result
        except subprocess.TimeoutExpired as exc:
            stdout = _text(exc.stdout)
            stderr = _text(exc.stderr)
            result = {
                "success": False,
                "command": command,
                "return_code": None,
                "stdout": stdout,
                "stderr": stderr,
                "duration_seconds": round(time.monotonic() - started, 3),
                "timed_out": True,
                "log_path": str(log_path),
                "artifact": self._read_artifact(artifact_path),
            }
            self._write_log(log_path, stdout, stderr, None)
            return result

    def _log_path(self, command: list[str]) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        label = Path(command[0]).stem or "command"
        return self.output_root / "scripts" / "logs" / f"{stamp}-{label}.log"

    @staticmethod
    def _write_log(path: Path, stdout: str, stderr: str, return_code: int | None) -> None:
        path.write_text(
            f"return_code={return_code}\n\n[stdout]\n{stdout}\n\n[stderr]\n{stderr}\n",
            encoding="utf-8",
        )

    @staticmethod
    def _read_artifact(path: Path | None) -> Any:
        if path is None or not path.is_file():
            return None
        try:
            import json

            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"path": str(path), "readable": False}

    @staticmethod
    def _validate_script(definition: ScriptDefinition, registry: ScriptRegistry | None) -> None:
        if registry is not None:
            registry.require(definition.script_id)
        if not definition.path.is_file():
            raise ValueError(f"Automation script does not exist: {definition.path}")


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)
