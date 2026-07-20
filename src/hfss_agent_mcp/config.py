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
    script_root: Path = Path("scripts")
    aedt_executable: Path | None = None
    connect_timeout_seconds: float = 60.0
    cli_timeout_seconds: float = 300.0
    com_progid: str | None = None
    require_client_id: bool = False
    audit_log_path: Path | None = None
    lock_timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "ServerConfig":
        aedt_executable = os.getenv("HFSS_AGENT_AEDT_EXECUTABLE")
        return cls(
            name=os.getenv("HFSS_AGENT_MCP_NAME", cls.name),
            backend=os.getenv("HFSS_AGENT_BACKEND", cls.backend),
            transport=os.getenv("HFSS_AGENT_MCP_TRANSPORT", cls.transport),
            host=os.getenv("HFSS_AGENT_MCP_HOST", cls.host),
            port=int(os.getenv("HFSS_AGENT_MCP_PORT", str(cls.port))),
            log_level=os.getenv("HFSS_AGENT_LOG_LEVEL", cls.log_level),
            output_root=Path(os.getenv("HFSS_AGENT_OUTPUT_ROOT", str(cls.output_root))),
            script_root=Path(os.getenv("HFSS_AGENT_SCRIPT_ROOT", str(cls.script_root))),
            aedt_executable=Path(aedt_executable) if aedt_executable else None,
            connect_timeout_seconds=float(
                os.getenv("HFSS_AGENT_CONNECT_TIMEOUT_SECONDS", str(cls.connect_timeout_seconds))
            ),
            cli_timeout_seconds=float(
                os.getenv("HFSS_AGENT_CLI_TIMEOUT_SECONDS", str(cls.cli_timeout_seconds))
            ),
            com_progid=os.getenv("HFSS_AGENT_COM_PROGID") or None,
            require_client_id=_env_bool("HFSS_AGENT_REQUIRE_CLIENT_ID", cls.require_client_id),
            audit_log_path=(
                Path(os.getenv("HFSS_AGENT_AUDIT_LOG"))
                if os.getenv("HFSS_AGENT_AUDIT_LOG")
                else None
            ),
            lock_timeout_seconds=float(
                os.getenv("HFSS_AGENT_LOCK_TIMEOUT_SECONDS", str(cls.lock_timeout_seconds))
            ),
        )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
