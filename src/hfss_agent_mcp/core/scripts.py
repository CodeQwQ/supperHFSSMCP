from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_SCRIPT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


@dataclass
class ScriptDefinition:
    script_id: str
    path: Path
    description: str = ""


class ScriptRegistry:
    """Registry for scripts that the MCP service is allowed to execute."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self._scripts: dict[str, ScriptDefinition] = {}

    def register(self, script_id: str, relative_path: str, description: str = "") -> ScriptDefinition:
        if not _SCRIPT_ID.fullmatch(script_id):
            raise ValueError("script_id contains unsupported characters")
        path = (self.root / relative_path).resolve()
        self._ensure_inside_root(path)
        if path.suffix.lower() != ".py":
            raise ValueError("registered scripts must be Python files")
        definition = ScriptDefinition(script_id, path, description)
        self._scripts[script_id] = definition
        return definition

    def require(self, script_id: str) -> ScriptDefinition:
        try:
            definition = self._scripts[script_id]
        except KeyError as exc:
            raise ValueError(f"Unknown automation script: {script_id}") from exc
        self._ensure_inside_root(definition.path)
        if not definition.path.is_file():
            raise ValueError(f"Registered automation script does not exist: {definition.path}")
        return definition

    def list(self) -> list[dict[str, str]]:
        return [
            {"script_id": item.script_id, "path": str(item.path), "description": item.description}
            for item in self._scripts.values()
        ]

    def build_environment(self, definition: ScriptDefinition, arguments: dict[str, Any], output_path: Path) -> dict[str, str]:
        self._ensure_inside_root(definition.path)
        output_path = output_path.resolve()
        context_path = self.root / ".hfss-agent-context.json"
        context_path.write_text(
            json.dumps(
                {
                    "script_id": definition.script_id,
                    "arguments": arguments,
                    "output": str(output_path),
                },
                ensure_ascii=True,
            ),
            encoding="utf-8",
        )
        return {
            "HFSS_AGENT_SCRIPT_ID": definition.script_id,
            "HFSS_AGENT_SCRIPT_ARGS": json.dumps(arguments, ensure_ascii=True),
            "HFSS_AGENT_SCRIPT_OUTPUT": str(output_path),
            "HFSS_AGENT_SCRIPT_TARGET": str(definition.path),
        }

    def _ensure_inside_root(self, path: Path) -> None:
        if path != self.root and self.root not in path.parents:
            raise ValueError("automation script must stay inside the configured script root")
