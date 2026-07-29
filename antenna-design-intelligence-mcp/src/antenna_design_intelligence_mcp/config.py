from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServerConfig:
    name: str = "antenna-design-intelligence-mcp"
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 8010
    input_roots: tuple[Path, ...] = ()
    output_root: Path = Path("outputs")
    enable_verification_provider: bool = False
    max_input_bytes: int = 50 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "ServerConfig":
        roots_text = os.getenv("ANTENNA_INTELLIGENCE_INPUT_ROOTS", "inputs")
        roots = tuple(Path(item.strip()) for item in roots_text.split(";") if item.strip())
        return cls(
            name=os.getenv("ANTENNA_INTELLIGENCE_NAME", cls.name),
            transport=os.getenv("ANTENNA_INTELLIGENCE_TRANSPORT", cls.transport),
            host=os.getenv("ANTENNA_INTELLIGENCE_HOST", cls.host),
            port=int(os.getenv("ANTENNA_INTELLIGENCE_PORT", str(cls.port))),
            input_roots=roots,
            output_root=Path(os.getenv("ANTENNA_INTELLIGENCE_OUTPUT_ROOT", "outputs")),
            enable_verification_provider=os.getenv(
                "ANTENNA_INTELLIGENCE_ENABLE_VERIFICATION_PROVIDER", "false"
            ).lower() in {"1", "true", "yes", "on"},
            max_input_bytes=int(
                os.getenv("ANTENNA_INTELLIGENCE_MAX_INPUT_BYTES", str(cls.max_input_bytes))
            ),
        )
