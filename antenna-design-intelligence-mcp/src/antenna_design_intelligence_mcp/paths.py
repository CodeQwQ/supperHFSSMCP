from __future__ import annotations

import re
from pathlib import Path

from antenna_design_intelligence_mcp.errors import DomainError


SUPPORTED_INPUT_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg"}
ARTIFACT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,31}_[a-f0-9]{32}$")


class PathPolicy:
    def __init__(
        self,
        input_roots: tuple[Path, ...],
        output_root: Path,
        max_input_bytes: int = 50 * 1024 * 1024,
    ) -> None:
        self.input_roots = tuple(path.resolve() for path in input_roots)
        self.output_root = output_root.resolve()
        self.max_input_bytes = max_input_bytes

    def resolve_input(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser().resolve(strict=True)
        if not candidate.is_file() or not any(
            candidate.is_relative_to(root) for root in self.input_roots
        ):
            raise DomainError(
                "input_path_outside_allowed_roots",
                "输入文件不在允许的只读根目录内。",
                {"path": str(candidate)},
            )
        if candidate.suffix.lower() not in SUPPORTED_INPUT_SUFFIXES:
            raise DomainError(
                "unsupported_input_type",
                "输入文件类型不受支持，仅允许 PDF 或常见图像。",
                {"suffix": candidate.suffix.lower()},
            )
        if candidate.stat().st_size > self.max_input_bytes:
            raise DomainError(
                "input_too_large",
                "输入文件超过配置的大小限制。",
                {"size_bytes": candidate.stat().st_size, "limit": self.max_input_bytes},
            )
        return candidate

    def resolve_output(self, artifact_id: str) -> Path:
        if not ARTIFACT_ID_PATTERN.fullmatch(artifact_id):
            raise DomainError("invalid_artifact_id", "产物 ID 格式无效。", {"artifact_id": artifact_id})
        return self.output_root / "artifacts" / f"{artifact_id}.json"
