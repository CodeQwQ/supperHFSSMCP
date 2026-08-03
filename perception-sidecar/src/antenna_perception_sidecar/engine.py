from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Protocol


class Engine(Protocol):
    engine_id: str
    engine_version: str
    capabilities: list[str]

    def extract(self, input_digest: str, suffix: str, content: bytes) -> list[dict[str, Any]]:
        ...


@dataclass
class DemoEngine:
    engine_id: str = "demo_perception"
    engine_version: str = "0.1.0"
    capabilities: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.capabilities is None:
            self.capabilities = ["protocol_smoke_test", "manual_review"]

    def extract(self, input_digest: str, suffix: str, content: bytes) -> list[dict[str, Any]]:
        return [
            {
                "evidence_id": "demo_1",
                "source": {
                    "input_id": input_digest,
                    "quote": "演示感知引擎已接收输入；尚未配置真实 OCR/VLM 模型。",
                    "kind": "operator",
                },
                "provider_id": self.engine_id,
                "provider_version": self.engine_version,
                "confidence": 1.0,
                "observation": "该证据仅用于验证 sidecar 和 MCP 链路，不代表论文事实。",
            }
        ]


def load_engine(spec: str) -> Engine:
    module_name, separator, factory_name = spec.partition(":")
    if not separator or not module_name or not factory_name:
        raise ValueError("引擎模块必须使用 package.module:create_engine 格式")
    factory = getattr(import_module(module_name), factory_name)
    engine = factory()
    for name in ("engine_id", "engine_version", "capabilities", "extract"):
        if not hasattr(engine, name):
            raise TypeError(f"引擎缺少接口字段或方法: {name}")
    return engine


class CompositeEngine:
    def __init__(self, engines: list[Engine]) -> None:
        self.engines = engines
        self.engine_id = "+".join(engine.engine_id for engine in engines)
        self.engine_version = "+".join(engine.engine_version for engine in engines)
        self.capabilities = sorted({cap for engine in engines for cap in engine.capabilities})

    def extract(self, input_digest: str, suffix: str, content: bytes) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for engine in self.engines:
            for index, record in enumerate(engine.extract(input_digest, suffix, content), start=1):
                item = dict(record)
                item["evidence_id"] = f"{engine.engine_id}_{index}"
                records.append(item)
        return records
