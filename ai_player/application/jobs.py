"""Thread-safe task lifecycle independent of Qt and inference providers."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
from enum import Enum
from threading import Event, RLock
from time import monotonic
from uuid import uuid4


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


TERMINAL_STATUSES = frozenset({JobStatus.CANCELLED, JobStatus.SUCCEEDED, JobStatus.FAILED})


class JobCancelled(RuntimeError):
    """The caller no longer wants the result of this operation."""


class CancellationToken:
    def __init__(self) -> None:
        self._event = Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def check(self) -> None:
        if self.cancelled:
            raise JobCancelled("Operation cancelled")

    def wait(self, seconds: float) -> bool:
        return self._event.wait(max(0.0, seconds))


@dataclass(frozen=True)
class JobSnapshot:
    id: str
    name: str
    status: JobStatus
    created_at: float
    progress: int = 0
    detail: str = ""
    finished_at: float | None = None


@dataclass(frozen=True)
class JobHandle:
    id: str
    name: str
    token: CancellationToken


class JobManager:
    """Own active jobs and bounded history; stale generations cannot update a slot.

    Only snapshots are exposed. Callers poll on their UI thread; worker threads
    never invoke UI callbacks while holding the manager's lock.
    """

    def __init__(self, history_limit: int = 128) -> None:
        self._lock = RLock()
        self._history_limit = max(0, history_limit)
        self._jobs: OrderedDict[str, JobSnapshot] = OrderedDict()
        self._handles: dict[str, JobHandle] = {}
        self._current: dict[str, str] = {}

    def create(self, name: str) -> JobHandle:
        with self._lock:
            previous = self._current.get(name)
            if previous is not None:
                self.cancel(previous)
            handle = JobHandle(uuid4().hex, name, CancellationToken())
            self._handles[handle.id] = handle
            self._jobs[handle.id] = JobSnapshot(handle.id, name, JobStatus.QUEUED, monotonic())
            self._current[name] = handle.id
            self._trim()
            return handle

    def start(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != JobStatus.QUEUED:
                return False
            self._jobs[job_id] = replace(job, status=JobStatus.RUNNING)
            return True

    def update(self, job_id: str, *, progress: int | None = None, detail: str | None = None) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or not self.accepts_result(job_id):
                return False
            changes = {}
            if progress is not None:
                changes["progress"] = max(0, min(100, int(progress)))
            if detail is not None:
                changes["detail"] = " ".join(str(detail).split())[:500]
            self._jobs[job_id] = replace(job, **changes)
            return True

    def accepts_result(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            return bool(
                job and self._current.get(job.name) == job_id and job.status in {JobStatus.QUEUED, JobStatus.RUNNING}
            )

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in TERMINAL_STATUSES:
                return False
            self._handles[job_id].token.cancel()
            self._jobs[job_id] = replace(job, status=JobStatus.CANCELLING)
            return True

    def cancel_all(self) -> None:
        with self._lock:
            for job_id in tuple(self._handles):
                self.cancel(job_id)

    def finish(self, job_id: str, *, error: str | None = None) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in TERMINAL_STATUSES:
                return False
            status = JobStatus.FAILED if error is not None else JobStatus.SUCCEEDED
            if self._handles[job_id].token.cancelled:
                status = JobStatus.CANCELLED
            self._jobs[job_id] = replace(
                job,
                status=status,
                finished_at=monotonic(),
                progress=100 if status == JobStatus.SUCCEEDED else job.progress,
                detail=job.detail if error is None else str(error)[:500],
            )
            self._handles.pop(job_id, None)
            self._trim()
            return True

    def snapshots(self) -> tuple[JobSnapshot, ...]:
        with self._lock:
            return tuple(self._jobs.values())

    def _trim(self) -> None:
        terminal = [key for key, job in self._jobs.items() if job.status in TERMINAL_STATUSES]
        for job_id in terminal[: max(0, len(terminal) - self._history_limit)]:
            job = self._jobs.pop(job_id)
            if self._current.get(job.name) == job_id:
                self._current.pop(job.name)
