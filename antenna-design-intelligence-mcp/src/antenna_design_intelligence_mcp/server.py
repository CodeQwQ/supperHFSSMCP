from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from antenna_design_intelligence_mcp.config import ServerConfig


def create_app(config: ServerConfig | None = None) -> FastMCP:
    resolved = config or ServerConfig.from_env()
    app = FastMCP(
        name=resolved.name,
        instructions="提取带证据的天线设计规格；首版不内置 OCR/VLM。",
        host=resolved.host,
        port=resolved.port,
    )

    @app.tool()
    def inspect_input(path: str) -> dict[str, object]:
        """检查输入文件；完整路径安全校验将在后续任务加入。"""
        return {"success": True, "path": path}

    return app
