"""Run a workflow off the UI thread and deliver only current-generation events."""

from __future__ import annotations

from inspect import signature

from PySide6.QtCore import QThread, Signal, Slot

from ai_player.application.events import Workflow
from ai_player.application.jobs import JobManager


class WorkflowThread(QThread):
    workflow_type: type[Workflow]
    dependencies_factory = None
    task_name: str = ""
    event_names: tuple[str, ...] = ()
    _delivery = Signal(str, object)

    def __init__(self, *args, manager: JobManager | None = None, **kwargs) -> None:
        if self.dependencies_factory is not None:
            kwargs.setdefault("dependencies", self.dependencies_factory())
        arguments = signature(self.workflow_type).bind(*args, **kwargs).arguments
        parent = arguments.pop("parent", None)
        super().__init__(parent)
        self.workflow = self.workflow_type(**arguments)
        inherited_manager = getattr(parent, "job_manager", None)
        self.manager = manager or inherited_manager or JobManager()
        self.job = self.manager.create(self.task_name or type(self).__name__)
        self.workflow.cancellation = self.job.token
        self._failure: str | None = None
        self._delivery.connect(self._dispatch)
        self.finished.connect(self._finish_job)
        for name in self.event_names:
            getattr(self.workflow, name).connect(self._relay(name))

    def _relay(self, name: str):
        return lambda *args: self._delivery.emit(name, args)

    @Slot(str, object)
    def _dispatch(self, name: str, args: tuple) -> None:
        if not self.manager.accepts_result(self.job.id):
            return
        if name == "failed":
            self._failure = str(args[-1])
        elif name == "progress_percent":
            self.manager.update(self.job.id, progress=args[0])
        elif name in {"status_changed", "progress_changed"} and args and isinstance(args[0], str):
            self.manager.update(self.job.id, detail=args[0])
        getattr(self, name).emit(*args)

    def run(self) -> None:
        if not self.manager.start(self.job.id):
            return
        try:
            self.workflow.run()
        except Exception as exc:
            self._delivery.emit("failed", self.workflow.failure_arguments(exc))

    @Slot()
    def _finish_job(self) -> None:
        self.manager.finish(self.job.id, error=self._failure)

    def stop(self, **kwargs) -> None:
        self.manager.cancel(self.job.id)
        self.workflow.stop(**kwargs)

    def requestInterruption(self) -> None:
        self.stop()
        super().requestInterruption()

    def request_resync(self) -> None:
        self.workflow.request_resync()

    @property
    def started_at(self):
        return self.workflow.started_at
