from __future__ import annotations

from PySide6.QtCore import Signal

from ai_player.adapters import workflow_bindings
from ai_player.adapters.qt.workflow_thread import WorkflowThread
from ai_player.application.workflows import export as workflows


class DubbingExportWorker(WorkflowThread):
    task_name = "Export"
    dependencies_factory = staticmethod(workflow_bindings.export)
    workflow_type = workflows.DubbingExportWorker
    event_names = (
        "progress_changed",
        "progress_percent",
        "segment_ready",
        "export_finished",
        "partial_finished",
        "failed",
    )
    progress_changed = Signal(str)
    progress_percent = Signal(int)
    segment_ready = Signal(str, str)
    export_finished = Signal(str)
    partial_finished = Signal(str)
    failed = Signal(str)


class StagedDubbingExportWorker(WorkflowThread):
    task_name = "Export"
    dependencies_factory = staticmethod(workflow_bindings.export)
    workflow_type = workflows.StagedDubbingExportWorker
    event_names = (
        "progress_changed",
        "progress_percent",
        "segment_ready",
        "export_finished",
        "partial_finished",
        "failed",
    )
    progress_changed = Signal(str)
    progress_percent = Signal(int)
    segment_ready = Signal(str, str)
    export_finished = Signal(str)
    partial_finished = Signal(str)
    failed = Signal(str)
