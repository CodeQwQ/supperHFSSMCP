from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from hfss_agent_mcp.core.errors import SessionError
from hfss_agent_mcp.core.models import ConnectionSpec, SessionLaunchSpec


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SessionRecord:
    session_id: str
    backend: str
    status: str
    owner: str | None = None
    machine: str | None = None
    port: int | None = None
    project_path: str | None = None
    design_name: str | None = None
    desktop_version: str | None = None
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def update_from_connection(self, spec: ConnectionSpec) -> None:
        self.status = "connected"
        self.owner = spec.owner or self.owner
        self.machine = spec.machine or self.machine
        self.port = spec.port or self.port
        self.project_path = spec.project_path or self.project_path
        self.design_name = spec.design_name or self.design_name
        self.desktop_version = spec.desktop_version or self.desktop_version
        self.updated_at = _utc_now()

    def update_from_attempt(self, spec: ConnectionSpec) -> None:
        self.status = "connecting"
        self.owner = spec.owner or self.owner
        self.machine = spec.machine or self.machine
        self.port = spec.port or self.port
        self.project_path = spec.project_path or self.project_path
        self.design_name = spec.design_name or self.design_name
        self.desktop_version = spec.desktop_version or self.desktop_version
        if spec.connect_timeout_seconds is not None:
            self.metadata["connect_timeout_seconds"] = spec.connect_timeout_seconds
        self.metadata.pop("failure_reason", None)
        self.updated_at = _utc_now()

    def fail(self, reason: str) -> None:
        self.status = "failed"
        self.metadata["failure_reason"] = reason
        self.updated_at = _utc_now()

    def release(self) -> None:
        self.status = "released"
        self.updated_at = _utc_now()


class SessionManager:
    def __init__(self, backend_name: str) -> None:
        self.backend_name = backend_name
        self._records: dict[str, SessionRecord] = {}
        self._counter = 0
        self.active_session_id: str | None = None

    def launch(self, spec: SessionLaunchSpec) -> SessionRecord:
        record = SessionRecord(
            session_id=self._next_id(),
            backend=self.backend_name,
            status="launched",
            owner=spec.owner,
            machine=spec.machine,
            port=spec.port,
            project_path=spec.project_path,
            design_name=spec.design_name,
            desktop_version=spec.desktop_version,
            metadata={"non_graphical": spec.non_graphical},
        )
        self._records[record.session_id] = record
        self.active_session_id = record.session_id
        return record

    def connect(self, spec: ConnectionSpec) -> SessionRecord:
        record = self.begin_connect(spec)
        record.update_from_connection(spec)
        self.active_session_id = record.session_id
        return record

    def begin_connect(self, spec: ConnectionSpec) -> SessionRecord:
        if spec.session_id:
            record = self.require(spec.session_id)
            if record.status == "released":
                raise SessionError(f"Session {spec.session_id!r} has already been released.")
        else:
            record = SessionRecord(
                session_id=self._next_id(),
                backend=self.backend_name,
                status="created",
                owner=spec.owner,
            )
            self._records[record.session_id] = record
        record.update_from_attempt(spec)
        self.active_session_id = record.session_id
        return record

    def mark_connected(self, session_id: str, spec: ConnectionSpec) -> SessionRecord:
        record = self.require(session_id)
        if record.status == "released":
            raise SessionError(f"Session {session_id!r} has already been released.")
        record.update_from_connection(spec)
        self.active_session_id = session_id
        return record

    def mark_failed(self, session_id: str, reason: str) -> SessionRecord:
        record = self.require(session_id)
        record.fail(reason)
        self.active_session_id = session_id
        return record

    def list(self) -> list[SessionRecord]:
        return list(self._records.values())

    def require(self, session_id: str) -> SessionRecord:
        if session_id not in self._records:
            raise SessionError(f"Session {session_id!r} does not exist.")
        return self._records[session_id]

    def release(self, session_id: str) -> SessionRecord:
        record = self.require(session_id)
        record.release()
        if self.active_session_id == session_id:
            self.active_session_id = None
        return record

    def _next_id(self) -> str:
        self._counter += 1
        return f"{self.backend_name}-{self._counter:04d}"
