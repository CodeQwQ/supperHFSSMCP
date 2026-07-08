from __future__ import annotations

from pathlib import Path

from hfss_agent_mcp.core.errors import InputValidationError


class ProjectPathPolicy:
    """Resolve AEDT project files into a controlled project workspace."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()

    def default_project_path(self, project_name: str) -> Path:
        _require_project_name(project_name)
        return self.resolve_relative(f"{project_name}.aedt")

    def resolve_relative(self, relative_path: str) -> Path:
        if not relative_path or not relative_path.strip():
            raise InputValidationError("relative_path must be a non-empty string.")
        candidate_path = Path(relative_path)
        if candidate_path.is_absolute():
            raise InputValidationError("relative_path must be relative to the managed project root.")
        candidate = (self.root / candidate_path).resolve()
        if self.root != candidate and self.root not in candidate.parents:
            raise InputValidationError("relative_path must stay inside the managed project root.")
        if candidate.suffix.lower() != ".aedt":
            raise InputValidationError("HFSS project paths must use the .aedt extension.")
        return candidate


def _require_project_name(project_name: str | None) -> None:
    if not project_name or not project_name.strip():
        raise InputValidationError("project_name must be a non-empty string.")
