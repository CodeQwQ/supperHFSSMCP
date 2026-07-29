from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from antenna_design_intelligence_mcp.paths import PathPolicy


class ArtifactStore:
    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root.resolve()
        self.policy = PathPolicy(input_roots=(), output_root=self.output_root)
        (self.output_root / "artifacts").mkdir(parents=True, exist_ok=True)

    def write(self, kind: str, payload: dict[str, object]) -> str:
        artifact_id = f"{kind}_{uuid4().hex}"
        destination = self.policy.resolve_output(artifact_id)
        envelope = {
            "artifact_id": artifact_id,
            "kind": kind,
            "created_at": datetime.now(UTC).isoformat(),
            "payload": payload,
        }
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent, delete=False
        ) as temporary:
            json.dump(envelope, temporary, ensure_ascii=False, indent=2)
            temporary_path = Path(temporary.name)
        temporary_path.replace(destination)
        return artifact_id

    def read(self, artifact_id: str) -> dict[str, object]:
        destination = self.policy.resolve_output(artifact_id)
        if not destination.is_file():
            raise ValueError(f"artifact not found: {artifact_id}")
        return json.loads(destination.read_text(encoding="utf-8"))
