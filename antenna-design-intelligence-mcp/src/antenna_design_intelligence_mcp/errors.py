from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DomainError(ValueError):
    """可安全返回给 MCP client 的领域错误。"""

    code: str
    message: str
    details: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def to_payload(self) -> dict[str, object]:
        return {
            "success": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
        }
