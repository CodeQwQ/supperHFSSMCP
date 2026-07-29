from __future__ import annotations

from pathlib import Path

from antenna_design_intelligence_mcp.models import ProviderHealth, ProviderStatus
from antenna_design_intelligence_mcp.providers.base import EvidenceProvider
from antenna_design_intelligence_mcp.providers.verification import VerificationEvidenceProvider


class ProviderRegistry:
    def __init__(self, enable_verification: bool, output_root: Path) -> None:
        self._providers: dict[str, EvidenceProvider] = {}
        self._statuses: dict[str, ProviderStatus] = {
            "verification_evidence": ProviderStatus(
                provider_id="verification_evidence",
                provider_version="0.1.0",
                provider_kind="verification",
                capabilities=["manual_evidence"],
                health=ProviderHealth.UNAVAILABLE,
                message="首版未配置 OCR/VLM；仅启用开发/测试验证 provider 后可读取人工证据。",
            )
        }
        if enable_verification:
            self.register(VerificationEvidenceProvider(output_root))

    def register(self, provider: EvidenceProvider) -> None:
        if provider.provider_id in self._providers:
            raise ValueError(f"重复注册 provider: {provider.provider_id}")
        self._providers[provider.provider_id] = provider
        self._statuses[provider.provider_id] = provider.status()

    def list_status(self) -> list[dict[str, str]]:
        return [status.model_dump(mode="json") for status in self._statuses.values()]

    def available(self) -> list[EvidenceProvider]:
        return list(self._providers.values())
