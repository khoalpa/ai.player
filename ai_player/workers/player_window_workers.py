from __future__ import annotations

from PySide6.QtCore import Signal

from ai_player.adapters import workflow_bindings
from ai_player.adapters.qt.workflow_thread import WorkflowThread
from ai_player.application.workflows import sources as workflows


class RuntimeWarmupWorker(WorkflowThread):
    task_name = "Runtime preloading"
    dependencies_factory = staticmethod(workflow_bindings.sources)
    workflow_type = workflows.RuntimeWarmupWorker
    event_names = ("status_changed", "finished_successfully", "failed")
    status_changed = Signal(str)
    finished_successfully = Signal(object)
    failed = Signal(str)


class ProviderPreviewWorker(WorkflowThread):
    task_name = "Provider preview"
    dependencies_factory = staticmethod(workflow_bindings.sources)
    workflow_type = workflows.ProviderPreviewWorker
    event_names = ("ready", "failed")
    ready = Signal(object)
    failed = Signal(str)


class VideoSourceWorker(WorkflowThread):
    task_name = "URL/cache loading"
    dependencies_factory = staticmethod(workflow_bindings.sources)
    workflow_type = workflows.VideoSourceWorker
    event_names = ("resolved", "failed", "progress_changed", "stream_ready")
    resolved = Signal(object)
    failed = Signal(str)
    progress_changed = Signal(object)
    stream_ready = Signal(object)


class DocumentTranscriptWorker(WorkflowThread):
    task_name = "Document import"
    dependencies_factory = staticmethod(workflow_bindings.sources)
    workflow_type = workflows.DocumentTranscriptWorker
    event_names = ("ready", "failed")
    ready = Signal(object, bool)
    failed = Signal(str)


class TelegramChannelWorker(WorkflowThread):
    task_name = "Telegram"
    dependencies_factory = staticmethod(workflow_bindings.sources)
    workflow_type = workflows.TelegramChannelWorker
    event_names = (
        "videos_ready",
        "login_request_ready",
        "login_ready",
        "password_required",
        "progress_changed",
        "video_ready",
        "failed",
    )
    videos_ready = Signal(object)
    login_request_ready = Signal(object)
    login_ready = Signal(object)
    password_required = Signal(object, str)
    progress_changed = Signal(object)
    video_ready = Signal(str)
    failed = Signal(str)


class TelegramContentTranslationWorker(WorkflowThread):
    task_name = "Telegram translation"
    dependencies_factory = staticmethod(workflow_bindings.sources)
    workflow_type = workflows.TelegramContentTranslationWorker
    event_names = ("ready", "failed")
    ready = Signal(object)
    failed = Signal(str)


class SourceAudioFilterWorker(WorkflowThread):
    task_name = "Source voice filter"
    dependencies_factory = staticmethod(workflow_bindings.sources)
    workflow_type = workflows.SourceAudioFilterWorker
    event_names = ("ready", "failed", "warning")
    ready = Signal(str, str, str)
    failed = Signal(str, str)
    warning = Signal(str, str)


class PlaybackCompatibilityWorker(WorkflowThread):
    task_name = "Playback compatibility"
    dependencies_factory = staticmethod(workflow_bindings.sources)
    workflow_type = workflows.PlaybackCompatibilityWorker
    event_names = ("ready", "failed")
    ready = Signal(str, str)
    failed = Signal(str, str)
