from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hfss_agent_mcp.core.scripts import ScriptDefinition, ScriptRegistry


class ComAdapter:
    """Minimal late-bound AEDT COM adapter for registered native scripts."""

    def __init__(
        self,
        script_root: Path | str,
        output_root: Path | str | None = None,
        progid: str | None = None,
    ) -> None:
        self.script_root = Path(script_root).resolve()
        self.output_root = Path(output_root or self.script_root.parent / "outputs").resolve()
        self.progid = progid

    def connect(self) -> Any:
        try:
            import win32com.client

            errors: list[str] = []
            for candidate in self._progid_candidates():
                try:
                    return win32com.client.GetActiveObject(candidate)
                except Exception as exc:
                    errors.append(f"{candidate}: {exc}")
            raise RuntimeError("No active AEDT COM object was found. Tried " + "; ".join(errors))
        except Exception as exc:
            raise RuntimeError(f"Unable to attach to active AEDT COM application: {exc}") from exc

    def _progid_candidates(self) -> list[str]:
        candidates: list[str] = []
        configured = self.progid or os.getenv("HFSS_AGENT_COM_PROGID")
        if configured:
            candidates.append(configured)
        version = os.getenv("HFSS_AGENT_AEDT_VERSION")
        if version:
            candidates.append("Ansoft.ElectronicsDesktop." + version.replace("SV", ""))
        candidates.extend(["Ansoft.ElectronicsDesktop", "Ansoft.ElectronicsDesktop.2025.2"])
        return list(dict.fromkeys(candidates))

    def run(
        self,
        desktop: Any,
        definition: ScriptDefinition,
        arguments: dict[str, Any],
        registry: ScriptRegistry | None = None,
        output_path: Path | None = None,
    ) -> dict[str, Any]:
        if registry is not None:
            registry.require(definition.script_id)
        self._ensure_inside_root(definition.path)
        if not definition.path.is_file():
            raise ValueError(f"Automation script does not exist: {definition.path}")
        if output_path is not None:
            output_path = output_path.resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
        environment = {
            "HFSS_AGENT_SCRIPT_ID": definition.script_id,
            "HFSS_AGENT_SCRIPT_ARGS": _json(arguments),
            "HFSS_AGENT_SCRIPT_OUTPUT": str(output_path) if output_path else "",
        }
        previous = {key: os.environ.get(key) for key in environment}
        os.environ.update(environment)
        try:
            run_script = getattr(desktop, "RunScript", None)
            if not callable(run_script):
                raise RuntimeError("AEDT COM object does not expose RunScript")
            raw_result = run_script(str(definition.path))
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        return {
            "success": raw_result is not False,
            "command": ["COM", "RunScript", str(definition.path)],
            "return_code": 0 if raw_result is not False else 1,
            "stdout": "",
            "stderr": "" if raw_result is not False else "AEDT COM RunScript returned False",
            "artifact": _read_json(output_path),
            "log_path": str(self._write_log(definition, raw_result)),
        }

    def _write_log(self, definition: ScriptDefinition, raw_result: Any) -> Path:
        log_dir = self.output_root / "scripts" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = log_dir / f"{stamp}-com.log"
        path.write_text(
            f"script={definition.path}\nreturn_code={0 if raw_result is not False else 1}\n",
            encoding="utf-8",
        )
        return path

    def _ensure_inside_root(self, path: Path) -> None:
        if path != self.script_root and self.script_root not in path.parents:
            raise ValueError("automation script must stay inside the configured script root")


def _json(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, ensure_ascii=True)


def _read_json(path: Path | None) -> Any:
    if path is None or not path.is_file():
        return None
    import json

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
