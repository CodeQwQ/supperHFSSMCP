from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


class OllamaVLMEngine:
    """HTTP-only Ollama adapter; no CUDA or model-runtime dependency is required."""

    engine_id = "ollama_qwen2.5-vl-7b"
    engine_version = "1.0.0"
    capabilities = [
        "image_understanding",
        "antenna_geometry_extraction",
        "structured_json",
    ]

    def __init__(self) -> None:
        self.endpoint = os.getenv(
            "OLLAMA_API_ENDPOINT", "http://127.0.0.1:11434/api/chat"
        )
        self.model = os.getenv("OLLAMA_VLM_MODEL", "qwen2.5vl:7b")
        self.timeout = float(os.getenv("OLLAMA_API_TIMEOUT_SECONDS", "300"))

    def extract(
        self, input_digest: str, suffix: str, content: bytes
    ) -> list[dict[str, Any]]:
        normalized_suffix = suffix.lower()
        if normalized_suffix not in _IMAGE_SUFFIXES:
            return [
                self._manual_review(
                    input_digest,
                    "pdf_requires_page_render",
                    "PDF 需要先渲染为 PNG/JPG 页面后再调用 Ollama VLM。",
                )
            ]

        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {
                    "role": "user",
                    "content": self._prompt(),
                    "images": [base64.b64encode(content).decode("ascii")],
                }
            ],
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
            content_text = response_payload["message"]["content"]
            observation = json.loads(content_text)
            if not isinstance(observation, dict):
                raise ValueError("Ollama VLM JSON 顶层必须是对象")
        except (OSError, TimeoutError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            return [
                self._manual_review(
                    input_digest,
                    "ollama_vlm_error",
                    f"Ollama VLM 调用或 JSON 解析失败：{error}",
                )
            ]

        return [
            {
                "evidence_id": "ollama_vlm_1",
                "source": {
                    "input_id": input_digest,
                    "kind": "vlm",
                    "quote": content_text,
                },
                "provider_id": self.engine_id,
                "provider_version": self.engine_version,
                "confidence": 0.75,
                "observation": observation,
            }
        ]

    @staticmethod
    def _prompt() -> str:
        return """请分析这张天线设计图，只返回 JSON，不要返回 Markdown：
{
  "antenna_type": null,
  "substrate": {
    "material": null,
    "relative_permittivity": null,
    "thickness": null
  },
  "metal_layers": [],
  "dimensions": [],
  "feed": {"type": null, "position": null},
  "boundary_or_airbox": null,
  "design_intent": null,
  "unknowns": []
}

要求：只能提取图中能够确认的信息；无法确认的值必须为 null；所有无法确认的内容写入 unknowns；尺寸保留原始单位；不要猜测 HFSS 参数。"""

    @staticmethod
    def _manual_review(
        input_digest: str, code: str, message: str
    ) -> dict[str, Any]:
        return {
            "evidence_id": code,
            "source": {
                "input_id": input_digest,
                "kind": "operator",
                "quote": message,
            },
            "provider_id": "ollama_qwen2.5-vl-7b",
            "provider_version": "1.0.0",
            "confidence": 0.0,
            "observation": message,
        }


def create_engine() -> OllamaVLMEngine:
    return OllamaVLMEngine()
