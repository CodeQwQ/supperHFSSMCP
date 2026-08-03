from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from antenna_design_intelligence_mcp.errors import DomainError
from antenna_design_intelligence_mcp.models import (
    EvidenceItem,
    ExtractionRequest,
    ProviderHealth,
    ProviderStatus,
)


class HTTPPerceptionProvider:
    """调用与模型运行时解耦的 OCR/VLM HTTP 协议。"""

    requires_content = True

    def __init__(
        self,
        endpoint: str,
        timeout_seconds: float = 120.0,
        api_key: str | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key
        self.provider_id = "http_perception"
        self.provider_version = "protocol-1"

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            provider_id=self.provider_id,
            provider_version=self.provider_version,
            provider_kind="vision",
            capabilities=["ocr", "vision", "table_extraction", "figure_extraction"],
            health=ProviderHealth.AVAILABLE,
            message=f"已配置感知 sidecar endpoint: {self.endpoint}",
        )

    def extract(self, request: ExtractionRequest) -> list[EvidenceItem]:
        if not request.input_suffix or not request.content_base64:
            raise DomainError(
                "perception_payload_missing",
                "OCR/VLM Provider 缺少输入文件传输载荷。",
                {"input_digest": request.input_digest},
            )
        payload = json.dumps(
            {
                "protocol_version": "1",
                "input_digest": request.input_digest,
                "input_suffix": request.input_suffix,
                "content_base64": request.content_base64,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        http_request = Request(self.endpoint, data=payload, headers=headers, method="POST")
        try:
            with urlopen(http_request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise DomainError(
                "perception_http_error",
                "OCR/VLM sidecar 返回 HTTP 错误。",
                {"status": error.code, "endpoint": self.endpoint},
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise DomainError(
                "perception_unreachable",
                "无法连接 OCR/VLM sidecar。",
                {"endpoint": self.endpoint, "reason": str(error)},
            ) from error
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
            raise DomainError(
                "perception_invalid_response",
                "OCR/VLM sidecar 返回的不是有效 JSON。",
                {"endpoint": self.endpoint},
            ) from error

        if response_payload.get("protocol_version") != "1":
            raise DomainError(
                "perception_protocol_mismatch",
                "OCR/VLM sidecar 协议版本不兼容。",
                {"expected": "1", "actual": response_payload.get("protocol_version")},
            )
        try:
            records = [EvidenceItem.model_validate(item) for item in response_payload["evidence"]]
        except (KeyError, TypeError, ValueError) as error:
            raise DomainError(
                "perception_invalid_evidence",
                "OCR/VLM sidecar 返回的证据格式无效。",
                {"endpoint": self.endpoint},
            ) from error
        for record in records:
            if record.source.input_id != request.input_digest:
                raise DomainError(
                    "perception_input_mismatch",
                    "OCR/VLM sidecar 返回证据的输入摘要不匹配。",
                    {"expected": request.input_digest, "actual": record.source.input_id},
                )
        return records
