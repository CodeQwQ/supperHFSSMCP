from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any

from hfss_agent_mcp.core.errors import JobError


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobRecord:
    job_id: str
    setup_name: str
    owner: str | None = None
    status: str = "queued"
    created_at: str = field(default_factory=_utc_now)
    started_at: str | None = None
    finished_at: str | None = None
    log_summary: str | None = None
    failure_reason: str | None = None
    result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobManager:
    def __init__(self, storage_path: Path | str | None = None) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._counter = 0
        self._lock = threading.RLock()
        self._storage_path = Path(storage_path).resolve() if storage_path else None
        self._load()

    def create(self, setup_name: str, owner: str | None = None) -> JobRecord:
        with self._lock:
            self._counter += 1
            job = JobRecord(
                job_id=f"job-{self._counter:04d}",
                setup_name=setup_name,
                owner=owner,
            )
            self._jobs[job.job_id] = job
            self._persist()
            return job

    def require(self, job_id: str, owner: str | None = None) -> JobRecord:
        with self._lock:
            try:
                job = self._jobs[job_id]
            except KeyError as exc:
                raise JobError(f"Simulation job {job_id!r} does not exist.") from exc
            if owner is not None and job.owner not in {None, owner}:
                raise JobError(f"Simulation job {job_id!r} belongs to another owner.")
            return job

    def snapshot(self, job_id: str, owner: str | None = None) -> dict[str, Any]:
        with self._lock:
            return self.require(job_id, owner=owner).to_dict()

    def running(self, owner: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            return [
                job.to_dict()
                for job in self._jobs.values()
                if job.status in {"queued", "running"}
                and (owner is None or job.owner in {None, owner})
            ]

    def start(self, job_id: str, log_summary: str | None = None, owner: str | None = None) -> JobRecord:
        with self._lock:
            job = self.require(job_id, owner=owner)
            job.status = "running"
            job.started_at = _utc_now()
            job.log_summary = log_summary or "Simulation job started."
            self._persist()
            return job

    def complete(
        self,
        job_id: str,
        result: dict[str, Any],
        log_summary: str | None = None,
        owner: str | None = None,
    ) -> JobRecord:
        with self._lock:
            job = self.require(job_id, owner=owner)
            job.status = "completed"
            job.finished_at = _utc_now()
            job.result = result
            job.log_summary = log_summary or "Simulation job completed."
            self._persist()
            return job

    def fail(
        self,
        job_id: str,
        failure_reason: str,
        owner: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> JobRecord:
        with self._lock:
            job = self.require(job_id, owner=owner)
            job.status = "failed"
            job.finished_at = _utc_now()
            job.failure_reason = failure_reason
            if result is not None:
                job.result = result
            job.log_summary = "Simulation job failed."
            self._persist()
            return job

    def _load(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return
        try:
            payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        for raw in payload.get("jobs", []) if isinstance(payload, dict) else []:
            if not isinstance(raw, dict):
                continue
            try:
                job = JobRecord(**raw)
            except TypeError:
                continue
            if job.status in {"queued", "running"}:
                job.status = "interrupted"
                job.finished_at = _utc_now()
                job.failure_reason = (
                    "MCP service restarted while this simulation was active; "
                    "completion must be re-established by a new solve."
                )
                job.log_summary = "Simulation job interrupted by MCP service restart."
            self._jobs[job.job_id] = job
            try:
                self._counter = max(self._counter, int(job.job_id.rsplit("-", 1)[1]))
            except (IndexError, ValueError):
                continue

    def _persist(self) -> None:
        if self._storage_path is None:
            return
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"jobs": [job.to_dict() for job in self._jobs.values()]}
            temp_path = self._storage_path.with_suffix(self._storage_path.suffix + ".tmp")
            temp_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
            temp_path.replace(self._storage_path)
        except OSError:
            # Job tracking must not make a real HFSS operation fail because a
            # diagnostic persistence file is temporarily unavailable.
            return
