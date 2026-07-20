from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
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
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._counter = 0

    def create(self, setup_name: str, owner: str | None = None) -> JobRecord:
        self._counter += 1
        job = JobRecord(
            job_id=f"job-{self._counter:04d}",
            setup_name=setup_name,
            owner=owner,
        )
        self._jobs[job.job_id] = job
        return job

    def require(self, job_id: str, owner: str | None = None) -> JobRecord:
        try:
            job = self._jobs[job_id]
        except KeyError as exc:
            raise JobError(f"Simulation job {job_id!r} does not exist.") from exc
        if owner is not None and job.owner not in {None, owner}:
            raise JobError(f"Simulation job {job_id!r} belongs to another owner.")
        return job

    def start(self, job_id: str, log_summary: str | None = None, owner: str | None = None) -> JobRecord:
        job = self.require(job_id, owner=owner)
        job.status = "running"
        job.started_at = _utc_now()
        job.log_summary = log_summary or "Simulation job started."
        return job

    def complete(
        self,
        job_id: str,
        result: dict[str, Any],
        log_summary: str | None = None,
        owner: str | None = None,
    ) -> JobRecord:
        job = self.require(job_id, owner=owner)
        job.status = "completed"
        job.finished_at = _utc_now()
        job.result = result
        job.log_summary = log_summary or "Simulation job completed."
        return job

    def fail(self, job_id: str, failure_reason: str, owner: str | None = None) -> JobRecord:
        job = self.require(job_id, owner=owner)
        job.status = "failed"
        job.finished_at = _utc_now()
        job.failure_reason = failure_reason
        job.log_summary = "Simulation job failed."
        return job
