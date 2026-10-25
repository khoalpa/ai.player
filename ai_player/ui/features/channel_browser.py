from __future__ import annotations

from PySide6.QtWidgets import QStyle

from ai_player.adapters.sources.telegram_channel import telegram_private_available
from ai_player.ui.features.base import Feature


class PlayerChannelBrowserFeature(Feature):
    def _show_telegram_channel_browser(self, url: str, status: str = "") -> None:
        self.context.sources._clear_active_telegram_channel_video()
        self.context.dubbing._stop_dubbing()
        self.context.layout._player.stop()
        self.context.sources._reset_document_state_for_video()
        self.context.channel_browser._video_path = None
        self.context.channel_browser._video_source_http_headers = {}
        self.context.runtime.state.media_path = ""
        self.context.sources.channel.reset_loaded_channel()
        self.context.layout._telegram_channel_list.clear()
        self.context.layout._telegram_channel_preview.clear()
        self.context.sources._clear_telegram_channel_thumbnail()
        self.context.sources._apply_telegram_browser_preferences(url)
        self.context.channel_browser._sync_channel_browser_texts()
        title_key = (
            "youtube_channel_browser_title"
            if self.context.sources._current_channel_provider() == "youtube"
            else "telegram_channel_browser_title"
        )
        self.context.layout._telegram_channel_title.setText(self.context.settings._tr(title_key).format(url=url))
        self.context.layout._telegram_channel_status.setText(status)
        self.context.layout._telegram_channel_open_button.setEnabled(False)
        self.context.layout._telegram_channel_login_button.setEnabled(
            self.context.sources._current_channel_provider() == "telegram" and telegram_private_available()
        )
        self.context.layout._telegram_channel_refresh_button.setEnabled(True)
        self.context.layout._telegram_channel_load_more_button.setEnabled(True)
        self.context.layout._telegram_channel_thumbnail.setText("")
        self.context.channel_browser._show_telegram_browser_media_output()
        self.context.layout._media_stack.setCurrentWidget(self.context.layout._telegram_channel_view)
        self.context.layout._source_label.setText(url)
        self.context.channel_browser._sync_telegram_browser_button()
        self.context.channel_browser._sync_telegram_side_panel_toggle_button()
        self.context.channel_browser._set_telegram_side_panel_visible(self.context.sources.channel.side_panel_visible)
        self.context.media._apply_media_aspect_ratio()

    def _return_to_telegram_channel_browser(self) -> None:
        url = str(self.context.get("_pending_telegram_url", "") or "")
        if not url:
            return
        self.context.sources.channel.browser_return_available = False
        self.context.dubbing._stop_dubbing()
        self.context.layout._player.stop()
        self.context.sources._reset_document_state_for_video()
        self.context.channel_browser._video_path = None
        self.context.channel_browser._video_source_http_headers = {}
        self.context.runtime.state.media_path = ""
        title_key = (
            "youtube_channel_browser_title"
            if self.context.sources._current_channel_provider() == "youtube"
            else "telegram_channel_browser_title"
        )
        ready_key = (
            "youtube_channel_browser_ready"
            if self.context.sources._current_channel_provider() == "youtube"
            else "telegram_channel_browser_ready"
        )
        self.context.channel_browser._sync_channel_browser_texts()
        self.context.layout._telegram_channel_title.setText(self.context.settings._tr(title_key).format(url=url))
        self.context.layout._telegram_channel_status.setText(
            self.context.settings._tr(ready_key).format(count=len(self.context.sources.channel.channel_all_items))
        )
        current = self.context.sources._current_telegram_channel_item_for_navigation()
        if current is not None:
            self.context.channel_browser._telegram_suppress_auto_open_selection = True
            try:
                self.context.sources._select_telegram_channel_item(current)
            finally:
                self.context.channel_browser._telegram_suppress_auto_open_selection = False
        self.context.channel_browser._show_telegram_browser_media_output()
        self.context.layout._media_stack.setCurrentWidget(self.context.layout._telegram_channel_view)
        self.context.layout._source_label.setText(url)
        self.context.channel_browser._sync_telegram_browser_button()
        self.context.channel_browser._sync_telegram_side_panel_toggle_button()
        self.context.media._apply_media_aspect_ratio()

    def _show_video_output(self) -> None:
        if self.context.channel_browser._should_embed_telegram_video_output():
            self.context.layout._player.set_video_output(self.context.layout._telegram_video_widget)
            self.context.layout._telegram_channel_media_stack.setCurrentWidget(
                self.context.layout._telegram_video_widget
            )
            self.context.layout._media_stack.setCurrentWidget(self.context.layout._telegram_channel_view)
        else:
            self.context.layout._player.set_video_output(self.context.layout._video_widget)
            self.context.layout._media_stack.setCurrentWidget(self.context.layout._video_widget)
        self.context.media._apply_media_aspect_ratio()

    def _show_telegram_browser_media_output(self) -> None:
        set_video_output = getattr(self.context.get("_player", None), "set_video_output", None)
        if callable(set_video_output):
            set_video_output(self.context.layout._video_widget)
        self.context.channel_browser._show_telegram_thumbnail_output()

    def _sync_channel_browser_texts(self) -> None:
        provider = self.context.sources._current_channel_provider()
        search = self.context.get("_telegram_channel_search", None)
        remote_search = self.context.get("_telegram_channel_remote_search_button", None)
        if search is not None:
            search_key = "youtube_channel_search" if provider == "youtube" else "telegram_channel_search"
            search.setPlaceholderText(self.context.settings._tr(search_key))
        if remote_search is not None:
            remote_key = "youtube_channel_remote_search" if provider == "youtube" else "telegram_channel_remote_search"
            remote_search.setText(self.context.settings._tr(remote_key))

    def _should_embed_telegram_video_output(self) -> bool:
        return bool(
            self.context.get("_current_telegram_channel_item", None) is not None
            and self.context.get("_telegram_browser_return_available", False)
            and self.context.get("_telegram_channel_view", None) is not None
        )

    def _show_telegram_thumbnail_output(self) -> None:
        telegram_stack = self.context.get("_telegram_channel_media_stack", None)
        thumbnail = self.context.get("_telegram_channel_thumbnail", None)
        if telegram_stack is not None and thumbnail is not None:
            telegram_stack.setCurrentWidget(thumbnail)

    def _video_widget_in_telegram_media(self) -> bool:
        telegram_stack = self.context.get("_telegram_channel_media_stack", None)
        video_widget = self.context.get("_telegram_video_widget", None)
        return bool(
            telegram_stack is not None and video_widget is not None and telegram_stack.currentWidget() is video_widget
        )

    def _telegram_video_output_is_visible(self) -> bool:
        telegram_stack = self.context.get("_telegram_channel_media_stack", None)
        video_widget = self.context.get("_telegram_video_widget", None)
        return bool(
            telegram_stack is not None
            and video_widget is not None
            and telegram_stack.currentWidget() is video_widget
            and self.context.layout._media_stack.currentWidget() is self.context.layout._telegram_channel_view
        )

    def _telegram_side_panel_toggled(self, visible: bool) -> None:
        self.context.channel_browser._set_telegram_side_panel_visible(visible)

    def _telegram_side_panel_splitter_moved(self, *_args) -> None:
        splitter = self.context.get("_telegram_channel_splitter", None)
        side_panel = self.context.get("_telegram_channel_side_panel", None)
        if splitter is None or side_panel is None or side_panel.isHidden():
            return
        sizes = splitter.sizes()
        if len(sizes) < 2:
            return
        visible = sizes[1] > 0
        self.context.sources.channel.side_panel_visible = visible
        if visible:
            self.context.sources.channel.side_panel_sizes = sizes[:2]
        self.context.channel_browser._sync_telegram_side_panel_toggle_button()
        self.context.settings._queue_save_settings()

    def _set_telegram_side_panel_visible(self, visible: bool) -> None:
        splitter = self.context.get("_telegram_channel_splitter", None)
        side_panel = self.context.get("_telegram_channel_side_panel", None)
        if splitter is None or side_panel is None:
            return
        sizes = splitter.sizes()
        if len(sizes) < 2:
            sizes = [1, 1]
        visible = bool(visible)
        if visible:
            side_panel.setVisible(True)
            restore_sizes = list(self.context.get("_telegram_side_panel_sizes", [1, 1]) or [1, 1])
            if len(restore_sizes) < 2 or restore_sizes[0] <= 0 or restore_sizes[1] <= 0:
                restore_sizes = [1, 1]
            splitter.setSizes(restore_sizes[:2])
        else:
            if not side_panel.isHidden() and sizes[1] > 0:
                self.context.sources.channel.side_panel_sizes = sizes[:2]
            side_panel.setVisible(False)
            splitter.setSizes([max(1, sum(sizes) or splitter.width() or 1), 0])
        self.context.sources.channel.side_panel_visible = visible
        self.context.channel_browser._sync_telegram_side_panel_toggle_button()
        self.context.media._apply_media_aspect_ratio()
        self.context.settings._queue_save_settings()

    def _sync_telegram_side_panel_toggle_button(self) -> None:
        button = self.context.get("_telegram_channel_side_toggle_button", None)
        if button is None:
            return
        visible = bool(self.context.get("_telegram_side_panel_visible", True))
        icon = QStyle.StandardPixmap.SP_ArrowRight if visible else QStyle.StandardPixmap.SP_ArrowLeft
        button.setIcon(self.context.ui._app_icon(icon))
        tooltip_key = "telegram_channel_side_hide" if visible else "telegram_channel_side_show"
        button.setToolTip(self.context.settings._tr(tooltip_key))
        button.setAccessibleName(self.context.settings._tr(tooltip_key))
        was_blocked = button.blockSignals(True)
        button.setChecked(visible)
        button.blockSignals(was_blocked)

    def _sync_telegram_browser_button(self) -> None:
        button = self.context.get("_telegram_browser_button", None)
        if button is None:
            return
        visible = (
            bool(self.context.get("_telegram_browser_return_available", False))
            and self.context.get("_media_stack", None) is not None
            and self.context.layout._media_stack.currentWidget() is self.context.get("_video_widget", None)
        )
        button.setVisible(visible)
        button.setEnabled(visible and bool(self.context.get("_telegram_channel_all_items", [])))
