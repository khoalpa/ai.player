from __future__ import annotations

from PySide6.QtCore import Signal

from ai_player.adapters import workflow_bindings
from ai_player.adapters.qt.workflow_thread import WorkflowThread
from ai_player.application.workflows import realtime as workflows


class DubbingWorker(WorkflowThread):
    task_name = "Realtime dubbing"
    dependencies_factory = staticmethod(workflow_bindings.realtime)
    workflow_type = workflows.DubbingWorker
    event_names = (
        "status_changed",
        "segment_ready",
        "subtitle_ready",
        "audio_started",
        "playback_pause_requested",
        "playback_resume_requested",
        "failed",
    )
    status_changed = Signal(str)
    segment_ready = Signal(str, str)
    subtitle_ready = Signal(float, float, str, str)
    audio_started = Signal(float)
    playback_pause_requested = Signal(str)
    playback_resume_requested = Signal(str)
    failed = Signal(str)
