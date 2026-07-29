from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ServerConfig:
    name: str = "antenna-design-intelligence-mcp"
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 8010

    @classmethod
    def from_env(cls) -> "ServerConfig":
        return cls(
            name=os.getenv("ANTENNA_INTELLIGENCE_NAME", cls.name),
            transport=os.getenv("ANTENNA_INTELLIGENCE_TRANSPORT", cls.transport),
            host=os.getenv("ANTENNA_INTELLIGENCE_HOST", cls.host),
            port=int(os.getenv("ANTENNA_INTELLIGENCE_PORT", str(cls.port))),
        )
