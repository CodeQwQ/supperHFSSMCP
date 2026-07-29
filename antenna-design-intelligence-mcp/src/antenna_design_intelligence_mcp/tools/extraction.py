from __future__ import annotations

from collections.abc import Callable

from mcp.server.fastmcp import FastMCP

from antenna_design_intelligence_mcp.errors import DomainError
from antenna_design_intelligence_mcp.service import IntelligenceService


def _safe_call(operation: Callable[[], dict[str, object]]) -> dict[str, object]:
    try:
        return operation()
    except DomainError as error:
        return error.to_payload()
    except Exception:
        return {
            "success": False,
            "error": {"code": "internal_error", "message": "服务内部错误。", "details": {}},
        }


def register(mcp: FastMCP, service: IntelligenceService) -> None:
    @mcp.tool()
    def inspect_input(path: str) -> dict[str, object]:
        """检查受控输入文件并返回摘要。"""
        return _safe_call(lambda: service.inspect_input(path))

    @mcp.tool()
    def list_providers() -> dict[str, object]:
        """列出 provider 的能力和健康状态。"""
        return _safe_call(service.list_providers)

    @mcp.tool()
    def extract_document_evidence(input_id: str) -> dict[str, object]:
        """从已检查输入提取结构化证据。"""
        return _safe_call(lambda: service.extract_document_evidence(input_id))

    @mcp.tool()
    def extract_antenna_design_spec(evidence_artifact_id: str) -> dict[str, object]:
        """把证据合并为带状态和来源的天线设计规格。"""
        return _safe_call(lambda: service.extract_antenna_design_spec(evidence_artifact_id))

    @mcp.tool()
    def get_extraction_artifact(artifact_id: str) -> dict[str, object]:
        """按不透明 ID 读取受控提取产物。"""
        return _safe_call(lambda: service.get_extraction_artifact(artifact_id))
