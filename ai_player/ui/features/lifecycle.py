from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMainWindow

from ai_player.ui.features.base import Feature


class PlayerLifecycleFeature(Feature):
    def closeEvent(self, event) -> None:
        if not self.context.get("_closing", False):
            self.context.lifecycle._closing = True
            self.context.jobs.cancel_all()
            self.context.settings._save_settings()
            self.context.media._exit_video_fullscreen()
            self.context.media._cancel_delayed_video_playback()
            self.context.window.centralWidget().setEnabled(False)
            for name in ("_timer", "_runtime_timer", "_settings_save_timer", "_task_stop_timer"):
                timer = self.context.get(name, None)
                if timer is not None:
                    timer.stop()
            if self.context.has("_subtitle_overlay"):
                self.context.layout._subtitle_overlay.hide()
            self.context.lifecycle._close_retry_timer = QTimer(self.context.window)
            self.context.lifecycle._close_retry_timer.setSingleShot(True)
            self.context.lifecycle._close_retry_timer.timeout.connect(self.context.window.close)
            self.context.media.document.started_at = None
            self.context.layout._player.stop()
        # Never wait for a worker on the GUI thread. Keep its owner alive until
        # cancellation has completed and let Qt deliver queued finished signals.
        stopped = True
        stopped = self.context.dubbing._stop_dubbing() and stopped
        stopped = self.context.meeting._stop_meeting(wait_ms=0) and stopped
        stopped = self.context.lifecycle._stop_worker_attr("_telegram_worker", wait_ms=0) and stopped
        stopped = self.context.lifecycle._stop_worker_attr("_telegram_translation_worker", wait_ms=0) and stopped
        stopped = self.context.sources._stop_video_url(wait_ms=0) and stopped
        stopped = self.context.lifecycle._stop_worker_attr("_document_worker", wait_ms=0) and stopped
        stopped = self.context.runtime._stop_runtime_warmup(wait_ms=0) and stopped
        stopped = self.context.provider_preview._stop_provider_preview(wait_ms=0) and stopped
        stopped = self.context.lifecycle._stop_worker_attr("_source_filter_worker", wait_ms=0) and stopped
        stopped = self.context.lifecycle._stop_worker_attr("_playback_compat_worker", wait_ms=0) and stopped
        stopped = self.context.lifecycle._stop_worker_attr("_export_worker", wait_ms=0) and stopped
        stopped = self.context.offline_models._stop_offline_model_process(wait_ms=0) and stopped
        if not stopped:
            self.context.window.statusBar().showMessage(self.context.settings._tr("status_wait_background_stop"))
            event.ignore()
            self.context.lifecycle._close_retry_timer.start(100)
            return
        self.context.lifecycle._close_retry_timer.stop()
        dispose_player = getattr(self.context.layout._player, "dispose", None)
        if callable(dispose_player):
            dispose_player()
        else:
            self.context.layout._player.stop()
        event.accept()

    def resizeEvent(self, event) -> None:
        QMainWindow.resizeEvent(self.context.window, event)
        self.context.lifecycle._clamp_window_to_screen()
        self.context.lifecycle._sync_responsive_layout()
        self.context.media._apply_media_aspect_ratio()
        QTimer.singleShot(0, self.context.media._apply_media_aspect_ratio)
        self.context.media._position_subtitle_overlay()
        if self.context.media.document.mode and self.context.media.document.pages:
            QTimer.singleShot(0, lambda: self.context.media._update_document_page(force=True))

    def _sync_responsive_layout(self) -> None:
        if self.context.get("_focus_media_enabled", False) or self.context.get("_video_fullscreen", False):
            return
        if not self.context.has("_settings_scroll") or not self.context.has("_splitter"):
            return
        narrow = self.context.window.width() < 1040
        wide = self.context.window.width() > 1220
        if narrow and not self.context.media.playback.sidebar_panel_hidden:
            sizes = self.context.layout._splitter.sizes()
            if len(sizes) >= 2 and sizes[1] > 0:
                self.context.media.playback.sidebar_panel_sizes = sizes
            self.context.layout._settings_scroll.hide()
            self.context.media.playback.sidebar_panel_hidden = True
            self.context.lifecycle._responsive_sidebar_hidden = True
            self.context.layout._splitter.setSizes([max(1, sum(sizes) if sizes else self.context.window.width()), 0])
            self.context.media._sync_panel_visibility_buttons()
        elif wide and self.context.get("_responsive_sidebar_hidden", False):
            self.context.layout._settings_scroll.show()
            self.context.media.playback.sidebar_panel_hidden = False
            self.context.lifecycle._responsive_sidebar_hidden = False
            self.context.layout._splitter.setSizes(
                self.context.media.playback.sidebar_panel_sizes or [max(1, self.context.window.width() - 380), 380]
            )
            self.context.media._sync_panel_visibility_buttons()
        compact_header = self.context.window.width() < 900
        for widget_name in ("_source_label", "_ui_language_combo"):
            widget = self.context.get(widget_name, None)
            if widget is not None:
                widget.setVisible(not compact_header)

    def _clamp_window_to_screen(self) -> None:
        if self.context.lifecycle._clamping_to_screen:
            return
        screen = self.context.window.screen()
        if screen is None:
            return
        available = screen.availableGeometry()
        target_width = min(self.context.window.width(), available.width())
        target_height = min(self.context.window.height(), available.height())
        if target_width == self.context.window.width() and target_height == self.context.window.height():
            return
        self.context.lifecycle._clamping_to_screen = True
        try:
            self.context.window.resize(target_width, target_height)
        finally:
            self.context.lifecycle._clamping_to_screen = False

    def _stop_worker_attr(self, attr_name: str, wait_ms: int = 5000) -> bool:
        worker = self.context.get(attr_name, None)
        if worker is None:
            return True
        if not self.context.lifecycle.workers.stop_worker(worker, wait_ms=wait_ms):
            return False
        self.context.set(attr_name, None)
        return True
