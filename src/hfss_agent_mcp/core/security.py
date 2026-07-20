from __future__ import annotations

import asyncio
import contextvars
import json
import re
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from hfss_agent_mcp.core.errors import ConfigurationError, HfssAgentError


_CURRENT_IDENTITY: contextvars.ContextVar["RequestIdentity | None"] = contextvars.ContextVar(
    "hfss_agent_request_identity",
    default=None,
)
_OWNER_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


class SecurityError(HfssAgentError):
    """Raised when a request does not satisfy the server security policy."""


@dataclass(frozen=True)
class RequestIdentity:
    owner: str
    request_id: str
    client_id: str | None = None


def current_identity() -> RequestIdentity | None:
    return _CURRENT_IDENTITY.get()


@contextmanager
def request_scope(identity: RequestIdentity) -> Iterator[None]:
    token = _CURRENT_IDENTITY.set(identity)
    try:
        yield
    finally:
        _CURRENT_IDENTITY.reset(token)


class SecurityManager:
    def __init__(
        self,
        output_root: Path | str,
        *,
        audit_log_path: Path | str | None = None,
        require_client_id: bool = False,
        lock_timeout_seconds: float = 30.0,
    ) -> None:
        self.output_root = Path(output_root).resolve()
        self.require_client_id = require_client_id
        if lock_timeout_seconds <= 0:
            raise ConfigurationError("lock_timeout_seconds must be greater than zero.")
        self.lock_timeout_seconds = lock_timeout_seconds
        self.audit_log_path = Path(audit_log_path).resolve() if audit_log_path else self.output_root / "audit" / "requests.jsonl"
        self._audit_lock = threading.Lock()
        self._operation_lock = asyncio.Lock()

    def resolve(self, context: Any | None) -> RequestIdentity:
        client_id = getattr(context, "client_id", None) if context is not None else None
        client_id = str(client_id).strip() if client_id else None
        if self.require_client_id and not client_id:
            raise SecurityError("MCP request requires _meta.client_id when HFSS_AGENT_REQUIRE_CLIENT_ID=true.")
        request_id = getattr(context, "request_id", None) if context is not None else None
        owner = client_id or "anonymous"
        return RequestIdentity(
            owner=self._safe_owner(owner),
            request_id=str(request_id or uuid.uuid4()),
            client_id=client_id,
        )

    def workspace_root(self, identity: RequestIdentity | None = None) -> Path:
        identity = identity or current_identity()
        if identity is None:
            return self.output_root
        path = self.output_root / "workspaces" / self._safe_owner(identity.owner)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def record(
        self,
        *,
        identity: RequestIdentity,
        tool_name: str,
        arguments: dict[str, Any],
        status: str,
        duration_seconds: float,
        error: str | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "timestamp": time.time(),
            "request_id": identity.request_id,
            "owner": identity.owner,
            "client_id": identity.client_id,
            "tool": tool_name,
            "arguments": _redact(arguments),
            "status": status,
            "duration_seconds": round(duration_seconds, 3),
        }
        if error:
            entry["error"] = error[:1000]
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=True, separators=(",", ":")) + "\n"
        with self._audit_lock:
            with self.audit_log_path.open("a", encoding="utf-8") as stream:
                stream.write(line)

    async def acquire_operation_lock(self) -> None:
        try:
            await asyncio.wait_for(
                self._operation_lock.acquire(),
                timeout=self.lock_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise SecurityError(
                f"HFSS operation lock was busy for {self.lock_timeout_seconds:g} seconds."
            ) from exc

    def release_operation_lock(self) -> None:
        if self._operation_lock.locked():
            self._operation_lock.release()

    @staticmethod
    def _safe_owner(owner: str) -> str:
        value = _OWNER_PATTERN.sub("_", owner.strip()).strip("._")
        if not value:
            raise ConfigurationError("client_id must contain at least one safe workspace character.")
        return value[:80]


def _redact(value: Any, key: str = "") -> Any:
    if any(word in key.lower() for word in ("token", "password", "secret", "authorization")):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item, key) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)[:500]


def install_security_hooks(app: Any, service: Any) -> None:
    """Wrap FastMCP tool dispatch with request identity, audit, and serialization."""
    manager = service.security
    original_call_tool = app._tool_manager.call_tool

    async def audited_call_tool(
        name: str,
        arguments: dict[str, Any],
        context: Any | None = None,
        convert_result: bool = False,
    ) -> Any:
        identity = manager.resolve(context)
        started = time.monotonic()
        status = "ok"
        error: str | None = None
        acquired = False
        with request_scope(identity):
            try:
                await manager.acquire_operation_lock()
                acquired = True
                try:
                    return await original_call_tool(
                        name,
                        arguments,
                        context=context,
                        convert_result=convert_result,
                    )
                finally:
                    if acquired:
                        manager.release_operation_lock()
            except Exception as exc:
                status = "error"
                error = str(exc)
                raise
            finally:
                manager.record(
                    identity=identity,
                    tool_name=name,
                    arguments=arguments or {},
                    status=status,
                    duration_seconds=time.monotonic() - started,
                    error=error,
                )

    app._tool_manager.call_tool = audited_call_tool
