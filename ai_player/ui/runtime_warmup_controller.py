from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QApplication

from ai_player.services.runtime_warmup import has_runtime_warmup_stage
from ai_player.workers.player_window_workers import RuntimeWarmupWorker


class RuntimeWarmupController:
    def __init__(self, owner: Any) -> None:
        self._owner = owner
        self._worker: RuntimeWarmupWorker | None = None
        self._last_status = ""

    def start(self) -> None:
        config = self._owner._config
        if not config.runtime_warmup_enabled:
            return
        if not has_runtime_warmup_stage(config):
            return
        app = QApplication.instance()
        if app is not None and app.platformName().lower() == "offscreen":
            return
        if self._worker is not None:
            return
        worker = RuntimeWarmupWorker(config, self._owner)
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

    def status_changed(self, message: str) -> None:
        self.show_status(message)

    def finished_successfully(self, timings: object) -> None:
        if isinstance(timings, dict) and not timings:
            return
        self.show_status(self._owner._tr("status_runtime_warmup_ready"))

    def failed(self, message: str) -> None:
        self.show_status(self._owner._tr("status_runtime_warmup_failed").format(detail=message))

    def show_status(self, message: str) -> None:
        if self.can_replace_status():
            self._last_status = message
            self._owner.statusBar().showMessage(message)

    def can_replace_status(self) -> bool:
        current = self._owner.statusBar().currentMessage()
        warmup_messages = {
            self._owner._tr("warmup_loading_whisper"),
            self._owner._tr("warmup_loading_translation"),
            self._owner._tr("warmup_loading_transcript_cleanup"),
            self._owner._tr("warmup_loading_tts"),
            self._owner._tr("status_runtime_warmup_ready"),
        }
        warmup_failed_prefix = self._owner._tr("status_runtime_warmup_failed").split("{detail}", 1)[0]
        return (
            not current
            or current == self._last_status
            or current == self._owner._runtime_startup_status_message()
            or current in warmup_messages
            or (bool(warmup_failed_prefix) and current.startswith(warmup_failed_prefix))
        )

    def _worker_finished(self, worker: RuntimeWarmupWorker) -> None:
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()
