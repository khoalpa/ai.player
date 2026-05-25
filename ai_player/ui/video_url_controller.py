from __future__ import annotations

from typing import Any

from ai_player.workers.player_window_workers import VideoSourceWorker


class VideoUrlController:
    def __init__(self, owner: Any) -> None:
        self._owner = owner
        self._worker: VideoSourceWorker | None = None

    def start(self, url: str, playback_quality: str, *, full_cache: bool, language_id: str | None = None) -> bool:
        if self.is_opening():
            return False
        self.set_opening_controls(False)
        worker = VideoSourceWorker(
            url,
            playback_quality,
            full_cache=full_cache,
            language_id=language_id,
            parent=self._owner,
        )
        self._worker = worker
        worker.progress_changed.connect(self._owner._video_cache_progress_changed)
        worker.resolved.connect(self._owner._video_url_resolved)
        worker.failed.connect(self._owner._video_url_failed)
        worker.finished.connect(self.finished)
        worker.start()
        return True

    def stop(self, wait_ms: int = 5000) -> bool:
        worker = self._worker
        if worker is None:
            self.set_opening_controls(True)
            return True
        stop = getattr(worker, "stop", None)
        if callable(stop):
            stop()
        else:
            worker.requestInterruption()
        if not worker.wait(wait_ms):
            return False
        worker.deleteLater()
        self._worker = None
        self.set_opening_controls(True)
        return True

    def is_opening(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        self.set_opening_controls(True)

    def set_opening_controls(self, enabled: bool) -> None:
        button = getattr(self._owner, "_open_url_button", None)
        if button is not None:
            button.setEnabled(enabled)
