from __future__ import annotations

from PySide6.QtCore import Signal

from ai_player.adapters import workflow_bindings
from ai_player.adapters.qt.workflow_thread import WorkflowThread
from ai_player.application.workflows import meeting as workflows


class MeetingWorker(WorkflowThread):
    task_name = "Meeting recorder"
    dependencies_factory = staticmethod(workflow_bindings.meeting)
    workflow_type = workflows.MeetingWorker
    event_names = ("status_changed", "elapsed_changed", "segment_ready", "finished_successfully", "failed")
    status_changed = Signal(str)
    elapsed_changed = Signal(str)
    segment_ready = Signal(str, str)
    finished_successfully = Signal(object)
    failed = Signal(str)
