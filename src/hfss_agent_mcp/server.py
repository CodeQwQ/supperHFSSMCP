from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from hfss_agent_mcp.backends.factory import create_backend
from hfss_agent_mcp.config import ServerConfig
from hfss_agent_mcp.core.service import HfssService
from hfss_agent_mcp.tools.registry import register_all_tools


def create_service(config: ServerConfig | None = None) -> HfssService:
    resolved_config = config or ServerConfig.from_env()
    backend = create_backend(resolved_config.backend)
    return HfssService(
        backend=backend,
        output_root=resolved_config.output_root,
        config=resolved_config,
    )


def create_app(
    config: ServerConfig | None = None,
    service: HfssService | None = None,
) -> FastMCP:
    resolved_config = config or ServerConfig.from_env()
    resolved_service = service or create_service(resolved_config)
    app = FastMCP(
        name=resolved_config.name,
        instructions=(
            "Use these tools to control HFSS through a bounded engineering workflow. "
            "Call health_check first, then connect_hfss, inspect project state, "
            "create or modify designs, validate, solve, and read results. "
            "Automation tools run only server-registered scripts; never submit arbitrary code."
        ),
        host=resolved_config.host,
        port=resolved_config.port,
        log_level=resolved_config.log_level,
    )
    register_all_tools(app, resolved_service)
    return app
