from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_player.ui.features.context import WindowContext


from PySide6.QtWidgets import QApplication

from ai_player.runtime.runtime_warmup import has_runtime_warmup_stage
from ai_player.workers.player_window_workers import RuntimeWarmupWorker


class RuntimeWarmupController:
    def __init__(self, owner: WindowContext) -> None:
        self.context = owner
        self._worker: RuntimeWarmupWorker | None = None
        self._last_status = ""

    def start(self) -> None:
        config = self.context.config
        if not config.runtime_warmup_enabled:
            return
        if not has_runtime_warmup_stage(config):
            return
        app = QApplication.instance()
        if app is not None and app.platformName().lower() == "offscreen":
            return
        if self._worker is not None:
            return
        worker = RuntimeWarmupWorker(config, self.context.window)
        self._worker = worker
        worker.status_changed.connect(self.status_changed)
        worker.finished_successfully.connect(self.finished_successfully)
        worker.failed.connect(self.failed)
        worker.finished.connect(lambda worker=worker: self._worker_finished(worker))
        worker.start()

    def stop(self, wait_ms: int = 5000) -> bool:
        worker = self._worker
        if worker is None:
            return True
        worker.stop()
        if not worker.wait(wait_ms):
            return False
        worker.deleteLater()
        self._worker = None
        return True

    def is_running(self) -> bool:
        worker = self._worker
        if worker is None:
            return False
        is_running = getattr(worker, "isRunning", None)
        return bool(is_running()) if callable(is_running) else True

    def task_detail(self) -> str:
        return self._last_status or "Preloading runtime components."

    def status_changed(self, message: str) -> None:
        self.show_status(message)

    def finished_successfully(self, timings: object) -> None:
        if isinstance(timings, dict) and not timings:
            return
        self.show_status(self.context.settings._tr("status_runtime_warmup_ready"))

    def failed(self, message: str) -> None:
        self.show_status(self.context.settings._tr("status_runtime_warmup_failed").format(detail=message))

    def show_status(self, message: str) -> None:
        set_detail = self.context.get("_set_background_task_detail", None)
        if callable(set_detail):
            set_detail("Runtime preloading", message, log_detail=self._log_detail_for_status(message))
        if self.can_replace_status():
            self._last_status = message
            self.context.window.statusBar().showMessage(message)

    def can_replace_status(self) -> bool:
        current = self.context.window.statusBar().currentMessage()
        warmup_messages = {
            self.context.settings._tr("warmup_loading_whisper"),
            self.context.settings._tr("warmup_loading_translation"),
            self.context.settings._tr("warmup_loading_transcript_cleanup"),
            self.context.settings._tr("warmup_loading_tts"),
            self.context.settings._tr("warmup_loaded_whisper"),
            self.context.settings._tr("warmup_loaded_translation"),
            self.context.settings._tr("warmup_loaded_transcript_cleanup"),
            self.context.settings._tr("warmup_loaded_tts"),
            self.context.settings._tr("status_runtime_warmup_ready"),
        }
        warmup_failed_prefix = self.context.settings._tr("status_runtime_warmup_failed").split("{detail}", 1)[0]
        return (
            not current
            or current == self._last_status
            or current == self.context.runtime._runtime_startup_status_message()
            or current in warmup_messages
            or (bool(warmup_failed_prefix) and current.startswith(warmup_failed_prefix))
        )

    def _log_detail_for_status(self, message: str) -> str:
        started_messages = {
            self.context.settings._tr("warmup_loading_whisper"): self.context.settings._tr("warmup_started_whisper"),
            self.context.settings._tr("warmup_loading_translation"): self.context.settings._tr(
                "warmup_started_translation"
            ),
            self.context.settings._tr("warmup_loading_transcript_cleanup"): self.context.settings._tr(
                "warmup_started_transcript_cleanup"
            ),
            self.context.settings._tr("warmup_loading_tts"): self.context.settings._tr("warmup_started_tts"),
        }
        return started_messages.get(message, message)

    def _worker_finished(self, worker: RuntimeWarmupWorker) -> None:
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()
