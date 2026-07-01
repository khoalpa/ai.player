from __future__ import annotations

from PySide6.QtWidgets import QStyle

from ai_player.services.telegram_channel import telegram_private_available


class PlayerChannelBrowserMixin:
    def _show_telegram_channel_browser(self, url: str, status: str = "") -> None:
        self._clear_active_telegram_channel_video()
        self._stop_dubbing()
        self._player.stop()
        self._reset_document_state_for_video()
        self._video_path = None
        self._video_source_http_headers = {}
        self._runtime_media_path = ""
        self._telegram_channel_state.reset_loaded_channel()
        self._telegram_channel_list.clear()
        self._telegram_channel_preview.clear()
        self._clear_telegram_channel_thumbnail()
        self._apply_telegram_browser_preferences(url)
        self._sync_channel_browser_texts()
        title_key = (
            "youtube_channel_browser_title"
            if self._current_channel_provider() == "youtube"
            else "telegram_channel_browser_title"
        )
        self._telegram_channel_title.setText(self._tr(title_key).format(url=url))
        self._telegram_channel_status.setText(status)
        self._telegram_channel_open_button.setEnabled(False)
        self._telegram_channel_login_button.setEnabled(
            self._current_channel_provider() == "telegram" and telegram_private_available()
        )
        self._telegram_channel_refresh_button.setEnabled(True)
        self._telegram_channel_load_more_button.setEnabled(True)
        self._telegram_channel_thumbnail.setText("")
        self._show_telegram_browser_media_output()
        self._media_stack.setCurrentWidget(self._telegram_channel_view)
        self._source_label.setText(url)
        self._sync_telegram_browser_button()
        self._sync_telegram_side_panel_toggle_button()
        self._set_telegram_side_panel_visible(self._telegram_side_panel_visible)
        self._apply_media_aspect_ratio()

    def _return_to_telegram_channel_browser(self) -> None:
        url = str(getattr(self, "_pending_telegram_url", "") or "")
        if not url:
            return
        self._telegram_browser_return_available = False
        self._stop_dubbing()
        self._player.stop()
        self._reset_document_state_for_video()
        self._video_path = None
        self._video_source_http_headers = {}
        self._runtime_media_path = ""
        title_key = (
            "youtube_channel_browser_title"
            if self._current_channel_provider() == "youtube"
            else "telegram_channel_browser_title"
        )
        ready_key = (
            "youtube_channel_browser_ready"
            if self._current_channel_provider() == "youtube"
            else "telegram_channel_browser_ready"
        )
        self._sync_channel_browser_texts()
        self._telegram_channel_title.setText(self._tr(title_key).format(url=url))
        self._telegram_channel_status.setText(
            self._tr(ready_key).format(count=len(self._telegram_channel_all_items))
        )
        current = self._current_telegram_channel_item_for_navigation()
        if current is not None:
            self._telegram_suppress_auto_open_selection = True
            try:
                self._select_telegram_channel_item(current)
            finally:
                self._telegram_suppress_auto_open_selection = False
        self._show_telegram_browser_media_output()
        self._media_stack.setCurrentWidget(self._telegram_channel_view)
        self._source_label.setText(url)
        self._sync_telegram_browser_button()
        self._sync_telegram_side_panel_toggle_button()
        self._apply_media_aspect_ratio()

    def _show_video_output(self) -> None:
        if self._should_embed_telegram_video_output():
            self._player.set_video_output(self._telegram_video_widget)
            self._telegram_channel_media_stack.setCurrentWidget(self._telegram_video_widget)
            self._media_stack.setCurrentWidget(self._telegram_channel_view)
        else:
            self._player.set_video_output(self._video_widget)
            self._media_stack.setCurrentWidget(self._video_widget)
        self._apply_media_aspect_ratio()

    def _show_telegram_browser_media_output(self) -> None:
        set_video_output = getattr(getattr(self, "_player", None), "set_video_output", None)
        if callable(set_video_output):
            set_video_output(self._video_widget)
        self._show_telegram_thumbnail_output()

    def _sync_channel_browser_texts(self) -> None:
        provider = self._current_channel_provider()
        search = getattr(self, "_telegram_channel_search", None)
        remote_search = getattr(self, "_telegram_channel_remote_search_button", None)
        if search is not None:
            search_key = "youtube_channel_search" if provider == "youtube" else "telegram_channel_search"
            search.setPlaceholderText(self._tr(search_key))
        if remote_search is not None:
            remote_key = (
                "youtube_channel_remote_search"
                if provider == "youtube"
                else "telegram_channel_remote_search"
            )
            remote_search.setText(self._tr(remote_key))

    def _should_embed_telegram_video_output(self) -> bool:
        return bool(
            getattr(self, "_current_telegram_channel_item", None) is not None
            and getattr(self, "_telegram_browser_return_available", False)
            and getattr(self, "_telegram_channel_view", None) is not None
        )

    def _show_telegram_thumbnail_output(self) -> None:
        telegram_stack = getattr(self, "_telegram_channel_media_stack", None)
        thumbnail = getattr(self, "_telegram_channel_thumbnail", None)
        if telegram_stack is not None and thumbnail is not None:
            telegram_stack.setCurrentWidget(thumbnail)

    def _video_widget_in_telegram_media(self) -> bool:
        telegram_stack = getattr(self, "_telegram_channel_media_stack", None)
        video_widget = getattr(self, "_telegram_video_widget", None)
        return bool(
            telegram_stack is not None
            and video_widget is not None
            and telegram_stack.currentWidget() is video_widget
        )

    def _telegram_video_output_is_visible(self) -> bool:
        telegram_stack = getattr(self, "_telegram_channel_media_stack", None)
        video_widget = getattr(self, "_telegram_video_widget", None)
        return bool(
            telegram_stack is not None
            and video_widget is not None
            and telegram_stack.currentWidget() is video_widget
            and self._media_stack.currentWidget() is self._telegram_channel_view
        )

    def _telegram_side_panel_toggled(self, visible: bool) -> None:
        self._set_telegram_side_panel_visible(visible)

    def _telegram_side_panel_splitter_moved(self, *_args) -> None:
        splitter = getattr(self, "_telegram_channel_splitter", None)
        side_panel = getattr(self, "_telegram_channel_side_panel", None)
        if splitter is None or side_panel is None or side_panel.isHidden():
            return
        sizes = splitter.sizes()
        if len(sizes) < 2:
            return
        visible = sizes[1] > 0
        self._telegram_side_panel_visible = visible
        if visible:
            self._telegram_side_panel_sizes = sizes[:2]
        self._sync_telegram_side_panel_toggle_button()
        self._queue_save_settings()

    def _set_telegram_side_panel_visible(self, visible: bool) -> None:
        splitter = getattr(self, "_telegram_channel_splitter", None)
        side_panel = getattr(self, "_telegram_channel_side_panel", None)
        if splitter is None or side_panel is None:
            return
        sizes = splitter.sizes()
        if len(sizes) < 2:
            sizes = [1, 1]
        visible = bool(visible)
        if visible:
            side_panel.setVisible(True)
            restore_sizes = list(getattr(self, "_telegram_side_panel_sizes", [1, 1]) or [1, 1])
            if len(restore_sizes) < 2 or restore_sizes[0] <= 0 or restore_sizes[1] <= 0:
                restore_sizes = [1, 1]
            splitter.setSizes(restore_sizes[:2])
        else:
            if not side_panel.isHidden() and sizes[1] > 0:
                self._telegram_side_panel_sizes = sizes[:2]
            side_panel.setVisible(False)
            splitter.setSizes([max(1, sum(sizes) or splitter.width() or 1), 0])
        self._telegram_side_panel_visible = visible
        self._sync_telegram_side_panel_toggle_button()
        self._apply_media_aspect_ratio()
        self._queue_save_settings()

    def _sync_telegram_side_panel_toggle_button(self) -> None:
        button = getattr(self, "_telegram_channel_side_toggle_button", None)
        if button is None:
            return
        visible = bool(getattr(self, "_telegram_side_panel_visible", True))
        icon = QStyle.StandardPixmap.SP_ArrowRight if visible else QStyle.StandardPixmap.SP_ArrowLeft
        button.setIcon(self.style().standardIcon(icon))
        tooltip_key = "telegram_channel_side_hide" if visible else "telegram_channel_side_show"
        button.setToolTip(self._tr(tooltip_key))
        button.setAccessibleName(self._tr(tooltip_key))
        was_blocked = button.blockSignals(True)
        button.setChecked(visible)
        button.blockSignals(was_blocked)

    def _sync_telegram_browser_button(self) -> None:
        button = getattr(self, "_telegram_browser_button", None)
        if button is None:
            return
        visible = (
            bool(getattr(self, "_telegram_browser_return_available", False))
            and getattr(self, "_media_stack", None) is not None
            and self._media_stack.currentWidget() is getattr(self, "_video_widget", None)
        )
        button.setVisible(visible)
        button.setEnabled(visible and bool(getattr(self, "_telegram_channel_all_items", [])))
