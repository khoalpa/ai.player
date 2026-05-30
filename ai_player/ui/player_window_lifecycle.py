from __future__ import annotations

from PySide6.QtCore import QTimer


class PlayerLifecycleMixin:
    def closeEvent(self, event) -> None:
        self._save_settings()
        self._exit_video_fullscreen()
        if hasattr(self, "_runtime_timer"):
            self._runtime_timer.stop()
        if hasattr(self, "_subtitle_overlay"):
            self._subtitle_overlay.hide()
        stopped = True
        stopped = self._stop_dubbing() and stopped
        stopped = self._stop_meeting(wait_ms=15000) and stopped
        stopped = self._stop_worker_attr("_telegram_worker", wait_ms=5000) and stopped
        stopped = self._stop_worker_attr("_telegram_translation_worker", wait_ms=5000) and stopped
        stopped = self._stop_video_url(wait_ms=5000) and stopped
        stopped = self._stop_worker_attr("_document_worker", wait_ms=5000) and stopped
        stopped = self._stop_runtime_warmup(wait_ms=5000) and stopped
        stopped = self._stop_worker_attr("_source_filter_worker", wait_ms=5000) and stopped
        stopped = self._stop_worker_attr("_playback_compat_worker", wait_ms=5000) and stopped
        stopped = self._stop_worker_attr("_export_worker", wait_ms=15000) and stopped
        stopped = self._stop_offline_model_process(wait_ms=5000) and stopped
        if not stopped:
            self.statusBar().showMessage(self._tr("status_wait_background_stop"))
            event.ignore()
            QTimer.singleShot(500, self.close)
            return
        dispose_player = getattr(self._player, "dispose", None)
        if callable(dispose_player):
            dispose_player()
        else:
            self._player.stop()
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._clamp_window_to_screen()
        self._apply_media_aspect_ratio()
        QTimer.singleShot(0, self._apply_media_aspect_ratio)
        self._position_subtitle_overlay()
        if self._document_mode and self._document_pages:
            QTimer.singleShot(0, lambda: self._update_document_page(force=True))

    def _clamp_window_to_screen(self) -> None:
        if self._clamping_to_screen:
            return
        screen = self.screen()
        if screen is None:
            return
        available = screen.availableGeometry()
        target_width = min(self.width(), available.width())
        target_height = min(self.height(), available.height())
        if target_width == self.width() and target_height == self.height():
            return
        self._clamping_to_screen = True
        try:
            self.resize(target_width, target_height)
        finally:
            self._clamping_to_screen = False

    def _stop_worker_attr(self, attr_name: str, wait_ms: int = 5000) -> bool:
        worker = getattr(self, attr_name, None)
        if worker is None:
            return True
        stop = getattr(worker, "stop", None)
        if callable(stop):
            stop()
        else:
            request_interruption = getattr(worker, "requestInterruption", None)
            if callable(request_interruption):
                request_interruption()
            quit_worker = getattr(worker, "quit", None)
            if callable(quit_worker):
                quit_worker()
        if hasattr(worker, "wait") and not worker.wait(wait_ms):
            return False
        if hasattr(worker, "deleteLater"):
            worker.deleteLater()
        setattr(self, attr_name, None)
        return True
