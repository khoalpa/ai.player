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
        stopped = self._stop_provider_preview(wait_ms=5000) and stopped
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
        self._sync_responsive_layout()
        self._apply_media_aspect_ratio()
        QTimer.singleShot(0, self._apply_media_aspect_ratio)
        self._position_subtitle_overlay()
        if self._document_mode and self._document_pages:
            QTimer.singleShot(0, lambda: self._update_document_page(force=True))

    def _sync_responsive_layout(self) -> None:
        if getattr(self, "_focus_media_enabled", False) or getattr(self, "_video_fullscreen", False):
            return
        if not hasattr(self, "_settings_scroll") or not hasattr(self, "_splitter"):
            return
        narrow = self.width() < 1040
        wide = self.width() > 1220
        if narrow and not self._sidebar_panel_hidden:
            sizes = self._splitter.sizes()
            if len(sizes) >= 2 and sizes[1] > 0:
                self._sidebar_panel_sizes = sizes
            self._settings_scroll.hide()
            self._sidebar_panel_hidden = True
            self._responsive_sidebar_hidden = True
            self._splitter.setSizes([max(1, sum(sizes) if sizes else self.width()), 0])
            self._sync_panel_visibility_buttons()
        elif wide and getattr(self, "_responsive_sidebar_hidden", False):
            self._settings_scroll.show()
            self._sidebar_panel_hidden = False
            self._responsive_sidebar_hidden = False
            self._splitter.setSizes(self._sidebar_panel_sizes or [max(1, self.width() - 380), 380])
            self._sync_panel_visibility_buttons()
        compact_header = self.width() < 900
        for widget_name in ("_source_label", "_ui_language_combo"):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.setVisible(not compact_header)

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
        return self._worker_lifecycle_state.stop_owner_worker(self, attr_name, wait_ms=wait_ms)
