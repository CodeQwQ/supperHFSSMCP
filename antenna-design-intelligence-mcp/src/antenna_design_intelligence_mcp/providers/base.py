from __future__ import annotations

from typing import Protocol

from antenna_design_intelligence_mcp.models import (
    EvidenceItem,
    ExtractionRequest,
    ProviderStatus,
)


class EvidenceProvider(Protocol):
    provider_id: str
    provider_version: str

    def status(self) -> ProviderStatus:
        ...

    def extract(self, request: ExtractionRequest) -> list[EvidenceItem]:
        ...
