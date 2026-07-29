from __future__ import annotations

import json
from pathlib import Path

from antenna_design_intelligence_mcp.errors import DomainError
from antenna_design_intelligence_mcp.models import (
    EvidenceItem,
    ExtractionRequest,
    ProviderHealth,
    ProviderStatus,
)


class VerificationEvidenceProvider:
    provider_id = "verification_evidence"
    provider_version = "0.1.0"

    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root.resolve()

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            provider_id=self.provider_id,
            provider_version=self.provider_version,
            health=ProviderHealth.AVAILABLE,
            message="仅用于开发/测试的人工核对证据，不执行 OCR 或视觉推理。",
        )

    def extract(self, request: ExtractionRequest) -> list[EvidenceItem]:
        fixture = self.output_root / "verification-evidence" / f"{request.input_digest}.json"
        if not fixture.is_file():
            raise DomainError(
                "verification_evidence_not_found",
                "没有找到与输入摘要匹配的人工核对证据。",
                {"input_digest": request.input_digest},
            )
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        if payload.get("input_digest") != request.input_digest:
            raise DomainError(
                "verification_evidence_digest_mismatch",
                "验证证据摘要与请求不一致。",
                {"input_digest": request.input_digest},
            )
        return [EvidenceItem.model_validate(item) for item in payload.get("evidence", [])]
