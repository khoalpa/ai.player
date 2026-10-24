from __future__ import annotations

from PySide6.QtCore import Signal

from ai_player.adapters import workflow_bindings
from ai_player.adapters.qt.workflow_thread import WorkflowThread
from ai_player.application.workflows import document as workflows


class DocumentReviewExportWorker(WorkflowThread):
    task_name = "Export"
    dependencies_factory = staticmethod(workflow_bindings.document)
    workflow_type = workflows.DocumentReviewExportWorker
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
