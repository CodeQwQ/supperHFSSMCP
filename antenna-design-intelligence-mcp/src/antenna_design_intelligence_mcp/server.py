from __future__ import annotations

from importlib.resources import files

from mcp.server.fastmcp import FastMCP

from antenna_design_intelligence_mcp.config import ServerConfig
from antenna_design_intelligence_mcp.artifacts import ArtifactStore
from antenna_design_intelligence_mcp.paths import PathPolicy
from antenna_design_intelligence_mcp.providers.registry import ProviderRegistry
from antenna_design_intelligence_mcp.service import IntelligenceService
from antenna_design_intelligence_mcp.tools.registry import register_all_tools


def create_app(config: ServerConfig | None = None) -> FastMCP:
    resolved = config or ServerConfig.from_env()
    app = FastMCP(
        name=resolved.name,
        instructions=(
            "从本地论文或截图提取带证据的天线设计规格。"
            "不得把 inferred 或 unknown 字段直接用于 HFSS 建模；"
            "建模后必须使用 HFSS MCP 的 validate_design，再运行求解。"
        ),
        host=resolved.host,
        port=resolved.port,
    )
    service = IntelligenceService(
        path_policy=PathPolicy(
            input_roots=resolved.input_roots,
            output_root=resolved.output_root,
            max_input_bytes=resolved.max_input_bytes,
        ),
        artifacts=ArtifactStore(resolved.output_root),
        providers=ProviderRegistry(
            enable_verification=resolved.enable_verification_provider,
            output_root=resolved.output_root,
        ),
    )
    register_all_tools(app, service)

    @app.resource(
        "antenna://handbook/extraction-workflow",
        name="extraction-workflow",
        title="天线设计信息提取工作手册",
        description="小模型使用的本地论文/截图提取与 HFSS 交接流程。",
        mime_type="text/markdown",
    )
    def extraction_workflow() -> str:
        return files("antenna_design_intelligence_mcp.resources").joinpath(
            "extraction-workflow.md"
        ).read_text(encoding="utf-8")

    @app.resource(
        "antenna://handbook/spec-fields",
        name="spec-fields",
        title="AntennaDesignSpec 字段说明",
        description="规格字段、状态和证据要求。",
        mime_type="text/markdown",
    )
    def spec_fields() -> str:
        return files("antenna_design_intelligence_mcp.resources").joinpath(
            "antenna-spec-fields.md"
        ).read_text(encoding="utf-8")

    return app
