from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServerConfig:
    name: str = "HFSS Agent MCP"
    backend: str = "mock"
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    output_root: Path = Path("outputs")

    @classmethod
    def from_env(cls) -> "ServerConfig":
        return cls(
            name=os.getenv("HFSS_AGENT_MCP_NAME", cls.name),
            backend=os.getenv("HFSS_AGENT_BACKEND", cls.backend),
            transport=os.getenv("HFSS_AGENT_MCP_TRANSPORT", cls.transport),
            host=os.getenv("HFSS_AGENT_MCP_HOST", cls.host),
            port=int(os.getenv("HFSS_AGENT_MCP_PORT", str(cls.port))),
            log_level=os.getenv("HFSS_AGENT_LOG_LEVEL", cls.log_level),
            output_root=Path(os.getenv("HFSS_AGENT_OUTPUT_ROOT", str(cls.output_root))),
        )
