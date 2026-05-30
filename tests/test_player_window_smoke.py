from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QFrame, QPushButton, QScrollArea, QSizePolicy

from ai_player.core.config import LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH, LOCAL_TRANSLATION_MODEL_PATH, AppConfig
from ai_player.services.document_reader import DocumentPage
from ai_player.services.telegram_channel import TelegramChannelVideo
from ai_player.ui.player_window import PlayerWindow
from ai_player.ui.player_window_layout import (
    DEFAULT_MEDIA_ASPECT_RATIO,
    DEFAULT_MEDIA_HOME_URL,
    TELEGRAM_IN_PLAYER_SCRIPT_SOURCE,
    TELEGRAM_ITEM_HTML_ROLE,
    TELEGRAM_TRANSLATION_COLOR,
    _InPlayerWebEnginePage,
    _InPlayerWebEngineView,
    _player_supported_browser_url,
    _subtitle_qcolor,
    _telegram_in_player_url,
)
from ai_player.ui.player_window_media import (
    DEFAULT_SIDEBAR_PANEL_WIDTH,
    PlayerMediaMixin,
    _document_ms_value,
    _document_seconds_value,
)
from ai_player.ui.player_window_sources import _TelegramVideoChoiceDialog
from ai_player.workers.player_window_workers import TelegramContentTranslationWorker


def test_player_window_constructs_offscreen(qapp) -> None:
    window = PlayerWindow()
    try:
        assert window.windowTitle()
        assert window._source_filter_worker_mode == window._config.original_audio_voice_filter_mode
        assert window._source_filter_worker_model == window._config.original_audio_voice_filter_model
        assert window._source_filter_cache == {}
        assert window._playback_compat_cache == {}
        assert window._runtime_gpu_text == window._tr("status_checking_gpu")
        assert window._runtime_media_info_text == window._tr("status_no_video")
        assert window._dub_worker is None
        assert window._export_worker is None
        assert window._meeting_worker is None
        assert window._telegram_worker is None
        assert window._telegram_translation_worker is None
        assert window._document_worker is None
        assert window._pending_telegram_url == ""
        assert window._aspect_combo.currentData() == DEFAULT_MEDIA_ASPECT_RATIO
        assert not window._panel_toggle_button.icon().isNull()
        assert window._panel_toggle_button.icon().cacheKey() != window._panel_collapse_button.icon().cacheKey()
        placeholder_url = getattr(window._video_placeholder, "url", None)
        if callable(placeholder_url):
            assert placeholder_url().toString() == DEFAULT_MEDIA_HOME_URL
            assert window._source_label.text() == DEFAULT_MEDIA_HOME_URL
            assert not window._media_home_button.isHidden()
    finally:
        window.close()


def test_telegram_video_dialog_keeps_duplicate_titles_distinct(qapp) -> None:
    videos = [
        SimpleNamespace(title="same title", post_id="101"),
        SimpleNamespace(title="same title", post_id="102"),
    ]
    dialog = _TelegramVideoChoiceDialog(videos, "en")
    try:
        dialog._list.setCurrentRow(1)
        item = dialog._list.currentItem()
        assert item.data(Qt.ItemDataRole.UserRole) == 1
    finally:
        dialog.close()


def test_player_window_google_home_button_resets_placeholder_url(qapp) -> None:
    window = PlayerWindow()
    try:
        set_url = getattr(window._video_placeholder, "setUrl", None)
        get_url = getattr(window._video_placeholder, "url", None)
        if not callable(set_url) or not callable(get_url):
            assert window._media_home_button.isHidden()
            return

        set_url(QUrl("https://example.com/search"))
        window._sync_media_browser_state()
        assert window._source_label.text() == "https://example.com/search"

        window._open_media_home()

        assert window._media_stack.currentWidget() is window._video_placeholder
        assert get_url().toString() == DEFAULT_MEDIA_HOME_URL
        assert window._source_label.text() == DEFAULT_MEDIA_HOME_URL
        assert not window._media_home_button.isHidden()

        window._media_stack.setCurrentWidget(window._video_widget)
        qapp.processEvents()
        assert window._media_home_button.isHidden()
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_media_home_button_click_resets_placeholder_url(qapp) -> None:
    window = PlayerWindow()
    try:
        set_url = getattr(window._video_placeholder, "setUrl", None)
        get_url = getattr(window._video_placeholder, "url", None)
        if not callable(set_url) or not callable(get_url):
            assert window._media_home_button.isHidden()
            return

        set_url(QUrl("https://example.com/search"))
        window._sync_media_browser_state()

        QTest.mouseClick(window._media_home_button, Qt.MouseButton.LeftButton)

        assert window._media_stack.currentWidget() is window._video_placeholder
        assert get_url().toString() == DEFAULT_MEDIA_HOME_URL
        assert window._source_label.text() == DEFAULT_MEDIA_HOME_URL
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_uses_in_player_web_view(qapp) -> None:
    window = PlayerWindow()
    try:
        if _InPlayerWebEngineView is None:
            return
        assert isinstance(window._video_placeholder, _InPlayerWebEngineView)
        assert hasattr(window._video_placeholder, "_open_telegram_link_at")
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_browser_telegram_link_uses_player_open_url_flow(qapp, monkeypatch) -> None:
    window = PlayerWindow()
    opened: list[str] = []
    try:
        monkeypatch.setattr(window, "_start_telegram_channel_flow", lambda url: opened.append(url))

        window._open_url_from_browser("https://t.me/rewudingzh")

        assert opened == ["https://t.me/rewudingzh"]
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_telegram_deep_link_stays_in_player_browser() -> None:
    assert (
        _telegram_in_player_url(QUrl("tg://resolve?domain=DouyinFuliqun&post=2711")).toString()
        == "https://t.me/DouyinFuliqun/2711"
    )
    assert (
        _telegram_in_player_url(QUrl("tg://resolve?domain=DouyinFuliqun&post=2711"), channel_preview=True).toString()
        == "https://t.me/s/DouyinFuliqun/2711"
    )
    assert (
        _telegram_in_player_url(QUrl("tg://privatepost?channel=-10012345&post=678")).toString()
        == "https://t.me/c/12345/678"
    )
    assert _telegram_in_player_url(QUrl("https://t.me/DouyinFuliqun/2711")).toString() == (
        "https://t.me/DouyinFuliqun/2711"
    )
    assert (
        _telegram_in_player_url(QUrl("https://t.me/DouyinFuliqun"), channel_preview=True).toString()
        == "https://t.me/s/DouyinFuliqun"
    )
    assert (
        _telegram_in_player_url(QUrl("https://t.me/DouyinFuliqun/2711"), channel_preview=True).toString()
        == "https://t.me/s/DouyinFuliqun/2711"
    )
    assert (
        _telegram_in_player_url(
            QUrl("https://www.google.com/url?q=https%3A%2F%2Ft.me%2FDouyinFuliqun"),
            channel_preview=True,
        ).toString()
        == "https://t.me/s/DouyinFuliqun"
    )
    assert _telegram_in_player_url(QUrl("https://www.google.com/search?q=https%3A%2F%2Ft.me%2FDouyinFuliqun")) is None
    assert _telegram_in_player_url(QUrl("https://example.com")) is None


def test_supported_browser_link_uses_player_open_url_flow() -> None:
    assert _player_supported_browser_url(QUrl("https://www.youtube.com/watch?v=abc123")).toString() == (
        "https://www.youtube.com/watch?v=abc123"
    )
    assert _player_supported_browser_url(
        QUrl("https://www.google.com/url?q=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3Dabc123")
    ).toString() == "https://www.youtube.com/watch?v=abc123"
    assert _player_supported_browser_url(QUrl("https://cdn.example.test/video.mp4")).toString() == (
        "https://cdn.example.test/video.mp4"
    )
    assert _player_supported_browser_url(
        QUrl("https://support.google.com/websearch/answer/510?hl=vi")
    ) is None
    assert _player_supported_browser_url(
        QUrl("https://www.google.com/url?q=https%3A%2F%2Fsupport.google.com%2Fwebsearch%2Fanswer%2F510")
    ) is None
    assert _player_supported_browser_url(QUrl("mailto:demo@example.test")) is None


def test_telegram_page_redirects_tg_scheme_without_external_app(qapp, monkeypatch) -> None:
    if _InPlayerWebEnginePage is None:
        return
    page = _InPlayerWebEnginePage()
    opened: list[str] = []
    try:
        monkeypatch.setattr(page, "_set_player_url", lambda url: opened.append(url.toString()))

        accepted = page.acceptNavigationRequest(
            QUrl("tg://resolve?domain=jdcmdy&post=19429"),
            page.NavigationType.NavigationTypeLinkClicked,
            True,
        )
        redirected = page.acceptNavigationRequest(
            QUrl("https://t.me/rewudingzh"),
            page.NavigationType.NavigationTypeTyped,
            True,
        )
        page._redirect_telegram_channel_landing(QUrl("https://t.me/anotherdemo"))
        page._telegram_link_hovered("https://t.me/hoverdemo")
        assert page._open_hovered_telegram_url() is True
        popup = page.createWindow(page.WebWindowType.WebBrowserTab)
        popup.acceptNavigationRequest(
            QUrl("https://www.google.com/url?q=https%3A%2F%2Ft.me%2Frewudingzh"),
            page.NavigationType.NavigationTypeLinkClicked,
            True,
        )
        video_clicked = page.acceptNavigationRequest(
            QUrl("https://www.youtube.com/watch?v=abc123"),
            page.NavigationType.NavigationTypeLinkClicked,
            True,
        )
        google_video_clicked = page.acceptNavigationRequest(
            QUrl("https://www.google.com/url?q=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3Dabc123"),
            page.NavigationType.NavigationTypeLinkClicked,
            True,
        )
        blocked = page.acceptNavigationRequest(QUrl("mailto:demo@example.test"), None, True)

        assert accepted is False
        assert redirected is False
        assert video_clicked is False
        assert google_video_clicked is False
        assert blocked is False
        assert opened == [
            "https://t.me/jdcmdy/19429",
            "https://t.me/rewudingzh",
            "https://t.me/anotherdemo",
            "https://t.me/hoverdemo",
            "https://t.me/rewudingzh",
            "https://www.youtube.com/watch?v=abc123",
            "https://www.youtube.com/watch?v=abc123",
        ]
    finally:
        page.deleteLater()


def test_telegram_link_script_does_not_observe_google_dom_forever() -> None:
    assert "MutationObserver" not in TELEGRAM_IN_PLAYER_SCRIPT_SOURCE
    assert "window.addEventListener('click'" in TELEGRAM_IN_PLAYER_SCRIPT_SOURCE
    assert "addEventListener('click'" in TELEGRAM_IN_PLAYER_SCRIPT_SOURCE
    assert "function patchLinks()" in TELEGRAM_IN_PLAYER_SCRIPT_SOURCE
    assert "window.setTimeout(patchLinks" in TELEGRAM_IN_PLAYER_SCRIPT_SOURCE


def test_player_window_help_button_click_opens_user_guide(qapp) -> None:
    window = PlayerWindow()
    opened: list[QDialog] = []

    def close_user_guide() -> None:
        dialogs = [
            widget
            for widget in qapp.topLevelWidgets()
            if isinstance(widget, QDialog) and widget.windowTitle() == window._guide_text("title")
        ]
        assert dialogs
        opened.append(dialogs[0])
        dialogs[0].accept()

    try:
        QTimer.singleShot(0, close_user_guide)

        QTest.mouseClick(window._help_button, Qt.MouseButton.LeftButton)

        assert opened
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_telegram_previous_next_skips_non_video_posts(qapp, monkeypatch) -> None:
    window = PlayerWindow()
    try:
        items = [
            TelegramChannelVideo("Video 101", "https://t.me/demo/101", "101"),
            TelegramChannelVideo("Post 102", "https://t.me/demo/102", "102", has_video=False, media_kind="text"),
            TelegramChannelVideo("Video 103", "https://t.me/demo/103", "103"),
        ]
        opened: list[str] = []
        window._telegram_channel_all_items = items
        window._telegram_channel_items = items
        window._pending_telegram_url = "https://t.me/demo"
        window._set_active_telegram_channel_video(items[2])
        monkeypatch.setattr(
            window,
            "_open_telegram_channel_item",
            lambda item: opened.append((item.post_id, window._pending_telegram_autoplay)),
        )

        window._previous_media_item()
        window._set_active_telegram_channel_video(items[0])
        window._next_media_item()

        assert opened == [("101", True), ("103", True)]
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_telegram_browser_up_down_selects_visible_videos(qapp) -> None:
    window = PlayerWindow()
    try:
        items = [
            TelegramChannelVideo("Video 101", "https://t.me/demo/101", "101"),
            TelegramChannelVideo("Post 102", "https://t.me/demo/102", "102", has_video=False, media_kind="text"),
            TelegramChannelVideo("Video 103", "https://t.me/demo/103", "103"),
        ]
        window._telegram_channel_all_items = items
        window._populate_telegram_channel_browser(items)

        assert window._telegram_channel_splitter.count() == 2
        assert window._telegram_channel_splitter.widget(0) is window._telegram_channel_media_panel
        assert window._telegram_channel_splitter.widget(1) is window._telegram_channel_side_panel
        assert window._telegram_channel_thumbnail.minimumHeight() >= 320
        assert not window._telegram_channel_thumbnail.isHidden()
        assert window._telegram_channel_side_panel.maximumWidth() > 10000
        assert window._telegram_channel_search.height() == 36
        assert window._telegram_channel_filter_combo.height() == 36
        assert window._telegram_channel_load_more_button.height() == 36
        assert window._telegram_channel_load_more_button.isCheckable()
        assert not window._telegram_channel_load_more_button.isChecked()
        assert window._telegram_channel_translate_button.isCheckable()
        assert not window._telegram_channel_translate_button.isChecked()
        assert window._telegram_channel_side_toggle_button.isCheckable()
        assert window._telegram_channel_side_toggle_button.isChecked()
        assert window._telegram_channel_side_toggle_button.height() == 36
        assert window._telegram_channel_media_panel.layout().count() == 2
        assert window._telegram_channel_open_button.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Minimum
        assert window._telegram_channel_login_button.height() == 36
        assert window._telegram_channel_refresh_button.height() == 36
        assert window._telegram_channel_title.isHidden()
        assert window._telegram_channel_status.isHidden()
        assert window._telegram_channel_list.iconSize().width() == 96
        assert window._telegram_channel_list.wordWrap() is True
        assert window._telegram_channel_list.textElideMode() == Qt.TextElideMode.ElideNone
        assert window._telegram_channel_list.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Expanding
        assert not window._telegram_channel_preview.isHidden()
        assert window._telegram_channel_preview.maximumHeight() <= 240

        assert window._select_adjacent_telegram_channel_video(1) is True
        assert window._telegram_channel_list.currentRow() == 2
        assert window._select_adjacent_telegram_channel_video(-1) is True
        assert window._telegram_channel_list.currentRow() == 0
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_telegram_side_panel_toggle_hides_and_restores_right_panel(qapp) -> None:
    window = PlayerWindow()
    try:
        window._show_telegram_channel_browser("https://t.me/demo")
        window._telegram_channel_splitter.setSizes([640, 360])

        window._telegram_channel_side_toggle_button.click()

        assert window._telegram_channel_side_panel.isHidden()
        assert not window._telegram_channel_side_toggle_button.isChecked()
        assert window._telegram_channel_splitter.widget(0) is window._telegram_channel_media_panel
        assert window._telegram_channel_splitter.widget(1) is window._telegram_channel_side_panel
        assert window._telegram_channel_splitter.sizes()[1] == 0

        window._telegram_channel_side_toggle_button.click()

        assert not window._telegram_channel_side_panel.isHidden()
        assert window._telegram_channel_side_toggle_button.isChecked()
        assert window._telegram_channel_splitter.sizes()[1] > 0
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_telegram_side_panel_splitter_collapse_keeps_toggle_recoverable(qapp) -> None:
    window = PlayerWindow()
    try:
        window._show_telegram_channel_browser("https://t.me/demo")
        window._telegram_channel_splitter.setSizes([640, 360])
        window._telegram_channel_splitter.setCollapsible(1, True)
        window._telegram_channel_splitter.setSizes([1000, 0])

        window._telegram_side_panel_splitter_moved(0, 0)

        assert not window._telegram_channel_side_panel.isHidden()
        assert not window._telegram_channel_side_toggle_button.isChecked()

        window._telegram_channel_side_toggle_button.click()

        assert not window._telegram_channel_side_panel.isHidden()
        assert window._telegram_channel_side_toggle_button.isChecked()
        assert window._telegram_channel_splitter.sizes()[1] > 0
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_telegram_browser_item_height_grows_for_wrapped_text(qapp) -> None:
    window = PlayerWindow()
    try:
        item = TelegramChannelVideo(
            "Media by @rauhong Group chat Join Group Backup list Join ALL Managed by Very Long Caption",
            "https://t.me/demo/101",
            "101",
            duration="0:15",
            text="Media by @rauhong Group chat Join Group Backup list Join ALL Managed by Very Long Caption",
            thumbnail_url="https://cdn.example.test/thumb.jpg",
            date="2026-05-29 12:55",
            file_name="demo.mp4",
            file_size=8 * 1024 * 1024,
            media_url="https://cdn.example.test/video.mp4",
        )
        window._telegram_channel_all_items = [item]
        window._populate_telegram_channel_browser([item])

        list_item = window._telegram_channel_list.item(0)
        assert "[Video] #101" in list_item.text()
        assert "Very Long Caption" in list_item.text()
        assert "2026-05-29 12:55" in list_item.text()
        assert "0:15" in list_item.text()
        assert "demo.mp4" in list_item.text()
        assert "8.0 MB" in list_item.text()
        assert "https://t.me/demo/101" not in list_item.text()
        assert "https://cdn.example.test/video.mp4" not in list_item.text()
        assert list_item.toolTip() == "https://t.me/demo/101"
        assert list_item.sizeHint().height() <= 112
        window._telegram_channel_selection_changed(list_item)
        preview_text = window._telegram_channel_preview.toPlainText()
        assert "https://t.me/demo/101" in preview_text
        assert "https://cdn.example.test/video.mp4" in preview_text
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_telegram_video_selection_auto_opens_after_population(qapp, monkeypatch) -> None:
    window = PlayerWindow()
    opened = []
    try:
        item = TelegramChannelVideo("Video 101", "https://t.me/demo/101", "101")
        window._telegram_channel_all_items = [item]
        window._populate_telegram_channel_browser([item])
        monkeypatch.setattr(window, "_open_telegram_channel_item", lambda channel_item: opened.append(channel_item))

        window._telegram_channel_selection_changed(window._telegram_channel_list.item(0))

        assert opened == [item]
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_telegram_video_output_stays_in_channel_splitter(qapp) -> None:
    window = PlayerWindow()
    try:
        item = TelegramChannelVideo("Video 101", "https://t.me/demo/101", "101")
        window._show_telegram_channel_browser("https://t.me/demo")
        window._telegram_channel_all_items = [item]
        window._populate_telegram_channel_browser([item])
        window._set_active_telegram_channel_video(item)
        window._telegram_browser_return_available = True

        window._show_video_output()

        assert window._media_stack.currentWidget() is window._telegram_channel_view
        assert window._telegram_channel_media_stack.currentWidget() is window._telegram_video_widget
        assert window._telegram_channel_media_stack.indexOf(window._telegram_video_widget) >= 0
        assert window._media_stack.indexOf(window._video_widget) >= 0
        assert window._telegram_channel_media_stack.indexOf(window._video_widget) < 0
        assert window._telegram_video_widget.aspectRatioMode() == Qt.AspectRatioMode.KeepAspectRatio
        assert window._telegram_channel_splitter.widget(0) is window._telegram_channel_media_panel
        assert window._telegram_channel_splitter.widget(1) is window._telegram_channel_side_panel
        window._telegram_channel_selection_changed(window._telegram_channel_list.item(0))
        assert window._telegram_channel_media_stack.currentWidget() is window._telegram_video_widget

        window._clear_active_telegram_channel_video()
        window._show_video_output()

        assert window._media_stack.currentWidget() is window._video_widget
        assert window._media_stack.indexOf(window._video_widget) >= 0
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_telegram_auto_load_more_toggle_loads_near_list_end(qapp, monkeypatch) -> None:
    window = PlayerWindow()
    loaded = []
    try:
        window._pending_telegram_url = "https://t.me/demo"
        window._telegram_channel_all_items = [TelegramChannelVideo("Video 101", "https://t.me/demo/101", "101")]
        monkeypatch.setattr(window, "_load_more_current_telegram_channel", lambda: loaded.append(True))
        scroll_bar = window._telegram_channel_list.verticalScrollBar()
        scroll_bar.setRange(0, 100)
        scroll_bar.setPageStep(20)
        scroll_bar.setValue(90)
        was_blocked = window._telegram_channel_load_more_button.blockSignals(True)
        window._telegram_channel_load_more_button.setChecked(True)
        window._telegram_channel_load_more_button.blockSignals(was_blocked)

        window._maybe_auto_load_more_telegram_channel()
        window._maybe_auto_load_more_telegram_channel()

        assert loaded == [True]
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_telegram_auto_load_more_can_retry_after_failure(qapp, monkeypatch) -> None:
    window = PlayerWindow()
    loaded = []
    warnings = []
    try:
        window._pending_telegram_url = "https://t.me/demo"
        window._telegram_channel_all_items = [TelegramChannelVideo("Video 101", "https://t.me/demo/101", "101")]
        monkeypatch.setattr(window, "_load_more_current_telegram_channel", lambda: loaded.append(True))
        monkeypatch.setattr("ai_player.ui.player_window_sources.telegram_private_available", lambda: False)
        monkeypatch.setattr(
            "ai_player.ui.player_window_sources.QMessageBox.warning",
            lambda *_args, **_kwargs: warnings.append(True),
        )
        scroll_bar = window._telegram_channel_list.verticalScrollBar()
        scroll_bar.setRange(0, 100)
        scroll_bar.setPageStep(20)
        scroll_bar.setValue(90)
        was_blocked = window._telegram_channel_load_more_button.blockSignals(True)
        window._telegram_channel_load_more_button.setChecked(True)
        window._telegram_channel_load_more_button.blockSignals(was_blocked)

        window._maybe_auto_load_more_telegram_channel()
        window._telegram_worker_failed("list_public_more", "network")
        window._maybe_auto_load_more_telegram_channel()

        assert loaded == [True, True]
        assert warnings == [True]
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_telegram_translation_renders_in_list_preview_and_search(qapp) -> None:
    window = PlayerWindow()
    try:
        item = TelegramChannelVideo(
            "你好世界",
            "https://t.me/demo/101",
            "101",
            text="你好世界",
            has_video=False,
            media_kind="text",
        )
        window._telegram_channel_all_items = [item]
        window._telegram_channel_translations[window._telegram_channel_item_key(item)] = "xin chao the gioi"
        window._populate_telegram_channel_browser([item])

        list_item = window._telegram_channel_list.item(0)
        assert "xin chao the gioi" in list_item.text()
        assert "Dịch:" not in list_item.text()
        assert f"color:{TELEGRAM_TRANSLATION_COLOR}" in list_item.data(TELEGRAM_ITEM_HTML_ROLE)
        window._telegram_channel_selection_changed(list_item)
        assert "xin chao the gioi" in window._telegram_channel_preview.toPlainText()
        assert "Dịch:" not in window._telegram_channel_preview.toPlainText()

        window._telegram_channel_search.setText("the gioi")
        assert window._telegram_channel_list.count() == 1
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_telegram_translation_toggle_auto_translates_loaded_items(qapp, monkeypatch) -> None:
    window = PlayerWindow()
    calls = []
    try:
        monkeypatch.setattr(
            window,
            "_translate_current_telegram_channel",
            lambda *args, auto=False: calls.append(auto),
        )
        was_blocked = window._telegram_channel_translate_button.blockSignals(True)
        window._telegram_channel_translate_button.setChecked(True)
        window._telegram_channel_translate_button.blockSignals(was_blocked)

        window._telegram_items_ready(
            [TelegramChannelVideo("你好", "https://t.me/demo/101", "101", text="你好")],
            "list_public",
        )

        assert calls == [True]
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_telegram_translation_only_sends_missing_text_items(qapp) -> None:
    window = PlayerWindow()
    try:
        translated = TelegramChannelVideo("old", "https://t.me/demo/100", "100", text="old")
        pending = TelegramChannelVideo("你好", "https://t.me/demo/101", "101", text="你好")
        empty = TelegramChannelVideo("", "https://t.me/demo/102", "102", text="")
        window._telegram_channel_translations[window._telegram_channel_item_key(translated)] = "cu"
        window._telegram_channel_all_items = [translated, pending, empty]

        assert window._telegram_channel_items_to_translate() == [pending]
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_telegram_content_translation_worker_uses_detected_source_language(qapp, monkeypatch) -> None:
    translated_results = []
    calls = []

    class Translator:
        def translate_many(self, texts, source_language=None):
            calls.append((list(texts), source_language))
            return ["xin chao"]

    monkeypatch.setattr(
        "ai_player.workers.player_window_workers.get_shared_vietnamese_translator",
        lambda _config: Translator(),
    )
    worker = TelegramContentTranslationWorker(
        AppConfig(source_language="auto"),
        [TelegramChannelVideo("你好", "https://t.me/demo/101", "101", text="你好")],
    )
    worker.ready.connect(lambda results: translated_results.extend(results))

    worker.run()

    assert calls == [(["你好"], "zh")]
    assert translated_results == [("101", "https://t.me/demo/101", "xin chao")]


def test_player_window_telegram_public_item_uses_saved_private_downloader(qapp, monkeypatch) -> None:
    window = PlayerWindow()
    try:
        item = TelegramChannelVideo("Video 101", "https://t.me/demo/101", "101")
        config = SimpleNamespace(api_id=12345, api_hash="hash", phone="+84000000000")
        started: list[dict[str, object]] = []
        monkeypatch.setattr("ai_player.ui.player_window_sources.telegram_private_available", lambda: True)
        monkeypatch.setattr("ai_player.ui.player_window_sources.load_telegram_login_config", lambda: config)
        monkeypatch.setattr(
            window,
            "_start_telegram_worker",
            lambda operation, **kwargs: started.append({"operation": operation, **kwargs}),
        )
        monkeypatch.setattr(window, "_open_resolved_video_url", lambda _url: started.append({"operation": "url"}))
        window._pending_telegram_url = "https://t.me/demo"

        window._open_telegram_channel_item(item)

        assert started == [
            {
                "operation": "download",
                "url": "https://t.me/demo",
                "config": config,
                "post_id": "101",
                "status_text": window._tr("status_telegram_video_downloading").format(label="Video 101"),
            }
        ]
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_telegram_public_item_uses_direct_media_url_before_ytdlp(qapp, monkeypatch) -> None:
    window = PlayerWindow()
    try:
        item = TelegramChannelVideo(
            "Video 101",
            "https://t.me/demo/101",
            "101",
            media_url="https://cdn.example.test/video.mp4",
        )
        opened: list[str] = []
        monkeypatch.setattr("ai_player.ui.player_window_sources.telegram_private_available", lambda: False)
        monkeypatch.setattr(window, "_open_resolved_video_url", lambda url, **_kwargs: opened.append(url))

        window._open_telegram_channel_item(item)

        assert opened == ["https://cdn.example.test/video.mp4"]
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_telegram_media_url_keeps_video_in_channel_splitter(qapp, monkeypatch) -> None:
    window = PlayerWindow()
    try:
        item = TelegramChannelVideo(
            "Video 101",
            "https://t.me/demo/101",
            "101",
            media_url="https://cdn.example.test/video.mp4",
        )
        window._dubbing_auto_enabled = False
        window._show_telegram_channel_browser("https://t.me/demo")
        window._telegram_channel_all_items = [item]
        window._populate_telegram_channel_browser([item])
        monkeypatch.setattr("ai_player.ui.player_window_sources.telegram_private_available", lambda: False)
        monkeypatch.setattr(
            window,
            "_load_current_video_for_playback",
            lambda: setattr(window, "_runtime_media_path", window._video_path),
        )
        monkeypatch.setattr(
            window._video_url,
            "start",
            lambda url, *_args, **_kwargs: window._video_url_resolved(
                SimpleNamespace(
                    playback_url=url,
                    title="Telegram direct media",
                    input_url=url,
                    provider="telegram",
                    is_resolved=True,
                )
            ),
        )

        window._open_telegram_channel_item(item)

        assert window._current_telegram_channel_item is item
        assert window._media_stack.currentWidget() is window._telegram_channel_view
        assert window._telegram_channel_media_stack.currentWidget() is window._telegram_video_widget
        assert window._media_stack.indexOf(window._video_widget) >= 0
        assert window._telegram_channel_media_stack.indexOf(window._video_widget) < 0
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_telegram_back_button_returns_to_browser(qapp) -> None:
    window = PlayerWindow()
    try:
        items = [
            TelegramChannelVideo("Video 101", "https://t.me/demo/101", "101"),
            TelegramChannelVideo("Video 102", "https://t.me/demo/102", "102"),
        ]
        window._pending_telegram_url = "https://t.me/demo"
        window._telegram_channel_all_items = items
        window._populate_telegram_channel_browser(items)
        window._set_active_telegram_channel_video(items[1])
        window._telegram_browser_return_available = True
        window._show_video_output()

        assert window._media_stack.currentWidget() is window._telegram_channel_view
        assert window._telegram_channel_media_stack.currentWidget() is window._telegram_video_widget

        window._return_to_telegram_channel_browser()

        assert window._media_stack.currentWidget() is window._telegram_channel_view
        assert window._telegram_channel_media_stack.currentWidget() is window._telegram_channel_thumbnail
        assert window._telegram_browser_button.isHidden()
        assert window._telegram_channel_list.currentRow() == 1
        assert window._source_label.text() == "https://t.me/demo"
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_telegram_navigation_autoplays_after_url_resolves(qapp, monkeypatch) -> None:
    window = PlayerWindow()
    try:
        played: list[str] = []
        source = SimpleNamespace(
            playback_url="https://cdn.example.test/video.mp4",
            title="Telegram video",
            input_url="https://t.me/demo/103",
            provider="telegram",
            is_resolved=True,
        )
        window._dubbing_auto_enabled = False
        window._pending_telegram_autoplay = True
        monkeypatch.setattr(
            window,
            "_load_current_video_for_playback",
            lambda: setattr(window, "_runtime_media_path", window._video_path),
        )
        monkeypatch.setattr(window, "_play_active_source", lambda: played.append(str(window._video_path)))

        window._video_url_resolved(source)

        assert played == ["https://cdn.example.test/video.mp4"]
        assert window._pending_telegram_autoplay is False
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_runtime_format_helpers(qapp) -> None:
    window = PlayerWindow()
    try:
        assert window._format_seconds(65) == "01:05"
        assert window._format_bytes(1024) == "1.0 KB"
        assert window._format_seconds(float("inf")) == window._tr("runtime_unknown")
        assert window._format_seconds(float("nan")) == window._tr("runtime_unknown")
        assert window._format_bytes(float("inf")) == window._tr("runtime_unknown")
    finally:
        window.close()


def test_player_window_media_probe_ignores_non_dict_streams(qapp) -> None:
    window = PlayerWindow()
    try:
        text = window._format_media_probe(
            Path("demo.mp4"),
            {"streams": ["bad", {"codec_type": "video", "codec_name": "h264"}], "format": {}},
        )

        assert "demo.mp4" in text
    finally:
        window.close()


def test_document_ms_value_sanitizes_invalid_times() -> None:
    assert _document_ms_value(float("inf")) == 0
    assert _document_ms_value(float("nan")) == 0
    assert _document_ms_value("bad") == 0
    assert _document_ms_value(1.25) == 1250
    assert _document_seconds_value(float("inf")) == 0.0
    assert _document_seconds_value(float("nan")) == 0.0


def test_subtitle_qcolor_ignores_non_finite_rgba_parts() -> None:
    assert _subtitle_qcolor("rgba(inf, 0, 0, 1)").alpha() == 0


def test_player_window_scaled_preset_value_ignores_bad_numbers() -> None:
    assert PlayerWindow._scaled_preset_value(float("nan"), fallback=0.55, scale=100) == 55
    assert PlayerWindow._scaled_preset_value(float("inf"), fallback=0.55, scale=100) == 55
    assert PlayerWindow._scaled_preset_value("bad", fallback=0.55, scale=100) == 55


def test_auto_video_aspect_uses_source_metadata(qapp) -> None:
    window = PlayerWindow()
    try:
        window._set_combo_data(window._aspect_combo, "16:9")
        window._auto_select_video_aspect_ratio(SimpleNamespace(width=720, height=1280))

        assert window._aspect_combo.currentData() == "9:16"
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_probe_video_dimensions_honors_rotation(monkeypatch, tmp_path) -> None:
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"demo")

    monkeypatch.setattr("ai_player.ui.player_window_media.ffprobe_executable", lambda: "ffprobe")
    monkeypatch.setattr(
        "ai_player.ui.player_window_media.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout='{"streams":[{"width":1920,"height":1080,"tags":{"rotate":"90"}}]}',
        ),
    )

    assert PlayerMediaMixin._probe_video_dimensions(str(video)) == (1080, 1920)
    assert PlayerMediaMixin._video_aspect_for_dimensions(1080, 1920) == "9:16"


def test_player_window_exposes_advanced_config_controls(qapp) -> None:
    window = PlayerWindow()
    try:
        window._runtime_warmup_enabled_check.setChecked(False)
        window._runtime_warmup_whisper_check.setChecked(False)
        window._runtime_warmup_translation_check.setChecked(False)
        window._runtime_warmup_tts_check.setChecked(True)
        window._cleanup_timeout_slider.setValue(45)
        window._ocr_fps_slider.setValue(35)
        window._ocr_crop_top_slider.setValue(42)
        window._ocr_crop_height_slider.setValue(33)
        window._ocr_scale_slider.setValue(175)
        window._ocr_psm_slider.setValue(7)
        window._ocr_threshold_check.setChecked(False)
        window._ocr_min_confidence_slider.setValue(55)
        window._ocr_merge_similarity_slider.setValue(91)
        window._set_combo_data(window._vieneu_core_combo, "remote")
        window._vieneu_path_edit.setText("D:/vieneu")
        window._vieneu_python_edit.setText("D:/Python/python.exe")
        window._vieneu_api_base_edit.setText("http://localhost:23333/v1")
        window._vieneu_decoder_path_edit.setText("D:/models/decoder.onnx")
        window._vieneu_encoder_path_edit.setText("D:/models/encoder.onnx")
        window._vieneu_standard_codec_path_edit.setText("D:/models/codec")

        config = window._current_runtime_config()

        assert config.runtime_warmup_enabled is False
        assert config.runtime_warmup_whisper is False
        assert config.runtime_warmup_translation is False
        assert config.runtime_warmup_tts is True
        assert config.transcript_cleanup_timeout_seconds == 45
        assert config.ocr_fps == 3.5
        assert config.ocr_crop_top_ratio == 0.42
        assert config.ocr_crop_height_ratio == 0.33
        assert config.ocr_scale == 1.75
        assert config.ocr_psm == 7
        assert config.ocr_threshold is False
        assert config.ocr_min_confidence == 55
        assert config.ocr_merge_similarity == 0.91
        assert config.vieneu_tts_core == "remote"
        assert config.vieneu_tts_model_name == "pnnbao-ump/VieNeu-TTS"
        assert config.vieneu_tts_offline is False
        assert config.vieneu_tts_path == "D:/vieneu"
        assert config.vieneu_tts_python == "D:/Python/python.exe"
        assert config.vieneu_tts_api_base == "http://localhost:23333/v1"
        assert config.vieneu_tts_decoder_path == "D:/models/decoder.onnx"
        assert config.vieneu_tts_encoder_path == "D:/models/encoder.onnx"
        assert config.vieneu_tts_standard_codec_path == "D:/models/codec"
        assert window._vieneu_api_base_edit.isEnabled()
        assert not window._vieneu_offline_check.isEnabled()
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_event_loop_smoke(qapp) -> None:
    window = PlayerWindow()
    try:
        window.show()
        QTimer.singleShot(10, qapp.quit)
        assert qapp.exec() == 0
    finally:
        window.close()


def test_seek_requests_dubbing_resync_without_blocking_stop(qapp, monkeypatch) -> None:
    window = PlayerWindow()
    try:
        calls: list[object] = []

        class FakePlayer:
            def set_position(self, value: float) -> None:
                calls.append(("set_position", value))

            def stop(self) -> None:
                calls.append("player_stop")

        class FakeDubbingWorker:
            def isRunning(self) -> bool:
                return True

            def request_resync(self) -> None:
                calls.append("request_resync")

            def stop(self) -> None:
                raise AssertionError("seek must not stop dubbing synchronously")

            def wait(self, _timeout_ms: int) -> bool:
                raise AssertionError("seek must not wait for dubbing synchronously")

        monkeypatch.setattr(window, "_player", FakePlayer())
        monkeypatch.setattr(
            window,
            "_set_dubbing_ready",
            lambda ready, message="": calls.append(("ready", ready, message)),
        )
        window._document_mode = False
        window._video_path = "demo.mp4"
        window._dub_worker = FakeDubbingWorker()
        window._dub_button.blockSignals(True)
        window._dub_button.setChecked(True)
        window._dub_button.blockSignals(False)
        window._position_slider.setValue(500)

        window._end_seek()

        assert ("set_position", 0.5) in calls
        assert "request_resync" in calls
        assert any(call[0:2] == ("ready", False) for call in calls if isinstance(call, tuple))
    finally:
        window._dub_worker = None
        window._dub_button.blockSignals(True)
        window._dub_button.setChecked(False)
        window._dub_button.blockSignals(False)
        window.close()


def test_runtime_warmup_status_does_not_leave_last_progress_message(qapp) -> None:
    window = PlayerWindow()
    try:
        window.statusBar().showMessage(window._tr("warmup_loading_tts"))
        window._runtime_warmup_finished_successfully({"tts_seconds": 0.1})

        assert window.statusBar().currentMessage() == window._tr("status_runtime_warmup_ready")
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_runtime_warmup_status_ignores_empty_success(qapp) -> None:
    window = PlayerWindow()
    try:
        startup_message = window._runtime_startup_status_message()
        window.statusBar().showMessage(startup_message)

        window._runtime_warmup_finished_successfully({})

        assert window.statusBar().currentMessage() == startup_message
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_runtime_warmup_status_can_replace_startup_status(qapp) -> None:
    window = PlayerWindow()
    try:
        window.statusBar().showMessage(window._runtime_startup_status_message())

        window._runtime_warmup_status_changed(window._tr("warmup_loading_translation"))

        assert window.statusBar().currentMessage() == window._tr("warmup_loading_translation")
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_runtime_warmup_status_survives_language_change(qapp) -> None:
    window = PlayerWindow()
    try:
        english_message = "Preloading translator..."
        window._show_runtime_warmup_status(english_message)
        window._set_combo_data(window._ui_language_combo, "vi")
        qapp.processEvents()

        window._runtime_warmup_finished_successfully({"translation_seconds": 0.1})

        assert window.statusBar().currentMessage() == window._tr("status_runtime_warmup_ready")
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_runtime_warmup_status_does_not_override_user_status(qapp) -> None:
    window = PlayerWindow()
    try:
        window.statusBar().showMessage("User opened a file")

        window._runtime_warmup_status_changed(window._tr("warmup_loading_translation"))
        window._runtime_warmup_finished_successfully({})
        window._runtime_warmup_failed("boom")

        assert window.statusBar().currentMessage() == "User opened a file"
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_runtime_warmup_status_can_replace_previous_failure(qapp) -> None:
    window = PlayerWindow()
    try:
        window._runtime_warmup_failed("boom")

        window._runtime_warmup_status_changed(window._tr("warmup_loading_translation"))

        assert window.statusBar().currentMessage() == window._tr("warmup_loading_translation")
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_fits_common_laptop_width(qapp) -> None:
    window = PlayerWindow()
    try:
        for language in ("vi", "en"):
            window._set_combo_data(window._ui_language_combo, language)
            qapp.processEvents()
            assert window.minimumSizeHint().width() <= 1366
            assert window._controls.minimumSizeHint().width() <= 900
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_media_frame_expands_when_settings_panel_is_hidden(qapp) -> None:
    window = PlayerWindow()
    try:
        window.resize(1366, 768)
        window.show()
        qapp.processEvents()
        initial_width = window._media_frame.width()
        media_layout = window._media_frame.parentWidget().layout()
        assert window._controls.isVisible()
        assert window._source_bar.isVisible()
        assert all(widget.isVisible() for widget in window._header_controls)
        assert media_layout.itemAt(media_layout.indexOf(window._media_frame)).alignment() & Qt.AlignCenter

        window._set_sidebar_panel_visible(False)
        qapp.processEvents()
        qapp.processEvents()

        assert window._sidebar_panel_hidden is True
        assert not window._controls.isVisible()
        assert not window._source_bar.isVisible()
        assert not window.statusBar().isVisible()
        assert all(not widget.isVisible() for widget in window._header_controls)
        assert not window._panel_toggle_button.isVisible()
        assert window._root_layout.contentsMargins().left() == 0
        assert window._video_layout.contentsMargins().left() == 0
        assert window._video_panel.property("focusMedia") is True
        assert window._media_frame.property("focusMedia") is True
        assert window._video_panel.contentsRect().size() == window._video_panel.size()
        assert window._media_frame.size() == window._video_panel.size()
        assert window._media_frame.size() == window._splitter.size()
        assert window._media_frame.size() == window.centralWidget().size()
        assert window._splitter.sizes()[1] == 0
        assert window._media_frame.width() > initial_width

        window._handle_escape_shortcut()
        qapp.processEvents()

        assert window._sidebar_panel_hidden is False
        assert window._controls.isVisible()
        assert window._source_bar.isVisible()
        assert window.statusBar().isVisible()
        assert all(widget.isVisible() for widget in window._header_controls)
        assert window._root_layout.contentsMargins().left() == 14
        assert window._video_layout.contentsMargins().left() == 12
        assert window._video_panel.property("focusMedia") is False
        assert window._media_frame.property("focusMedia") is False
        assert window._video_panel.frameShape() == QFrame.Shape.NoFrame
        assert window._media_frame.frameShape() == QFrame.Shape.NoFrame

        window._set_sidebar_panel_visible(False)
        qapp.processEvents()
        window._reset_panel_sizes()
        qapp.processEvents()

        assert window._sidebar_panel_hidden is False
        assert window._controls.isVisible()
        assert window._source_bar.isVisible()
        assert window.statusBar().isVisible()
        assert all(widget.isVisible() for widget in window._header_controls)
        assert window._root_layout.contentsMargins().left() == 14
        assert window._video_layout.contentsMargins().left() == 12
        assert window._video_panel.property("focusMedia") is False
        assert window._media_frame.property("focusMedia") is False
        assert window._video_panel.frameShape() == QFrame.Shape.NoFrame
        assert window._media_frame.frameShape() == QFrame.Shape.NoFrame
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_escape_restores_full_ui_from_focus_media_fullscreen(qapp) -> None:
    window = PlayerWindow()
    try:
        window.resize(1366, 768)
        window.show()
        qapp.processEvents()

        window._set_sidebar_panel_visible(False)
        qapp.processEvents()
        window._set_video_fullscreen(True)
        qapp.processEvents()

        assert window._sidebar_panel_hidden is True
        assert window._video_fullscreen is True

        window._handle_escape_shortcut()
        qapp.processEvents()
        qapp.processEvents()

        assert window._video_fullscreen is False
        assert window._sidebar_panel_hidden is False
        assert window._media_frame.parentWidget() is window._video_panel
        assert window._controls.isVisible()
        assert window._source_bar.isVisible()
        assert window.statusBar().isVisible()
        assert window._video_panel.property("focusMedia") is False
        assert window._media_frame.property("focusMedia") is False
        assert window._video_panel.frameShape() == QFrame.Shape.NoFrame
        assert window._media_frame.frameShape() == QFrame.Shape.NoFrame
        assert window._root_layout.contentsMargins().left() == 14
        assert window._video_layout.contentsMargins().left() == 12
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_repeated_focus_media_toggle_preserves_layout_state(qapp) -> None:
    window = PlayerWindow()
    try:
        window.resize(1366, 768)
        window.show()
        qapp.processEvents()

        for _ in range(3):
            window._set_sidebar_panel_visible(False)
            qapp.processEvents()
            qapp.processEvents()

            assert window._sidebar_panel_hidden is True
            assert window._media_frame.size() == window.centralWidget().size()
            assert window._video_panel.contentsRect().size() == window._video_panel.size()
            assert window._video_panel.frameShape() == QFrame.Shape.NoFrame
            assert window._media_frame.frameShape() == QFrame.Shape.NoFrame

            window._set_sidebar_panel_visible(True)
            qapp.processEvents()
            qapp.processEvents()

            assert window._sidebar_panel_hidden is False
            assert window._root_layout.contentsMargins().left() == 14
            assert window._video_layout.contentsMargins().left() == 12
            assert window._video_panel.property("focusMedia") is False
            assert window._media_frame.property("focusMedia") is False
            assert window._video_panel.frameShape() == QFrame.Shape.NoFrame
            assert window._media_frame.frameShape() == QFrame.Shape.NoFrame
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_focus_media_refreshes_document_page_after_resize(qapp, monkeypatch) -> None:
    window = PlayerWindow()
    try:
        window.resize(1366, 768)
        window.show()
        qapp.processEvents()
        window._set_document_mode(
            True,
            6000,
            [
                DocumentPage(
                    number=1,
                    title="Demo",
                    text="Document page",
                    start_seconds=0,
                    duration_seconds=6,
                )
            ],
        )
        qapp.processEvents()

        calls = []
        original_update_document_page = window._update_document_page

        def update_document_page_spy(force: bool = False) -> None:
            calls.append(force)
            original_update_document_page(force=force)

        monkeypatch.setattr(window, "_update_document_page", update_document_page_spy)

        window._set_sidebar_panel_visible(False)
        qapp.processEvents()
        qapp.processEvents()

        assert True in calls

        calls.clear()
        window._set_sidebar_panel_visible(True)
        qapp.processEvents()
        qapp.processEvents()

        assert True in calls
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_panel_expand_button_widens_control_panel(qapp) -> None:
    window = PlayerWindow()
    try:
        window.resize(1366, 768)
        window.show()
        qapp.processEvents()
        before = window._splitter.sizes()
        before_min_width = window._settings_scroll.minimumWidth()

        window._expand_sidebar_panel()
        qapp.processEvents()
        after = window._splitter.sizes()

        assert window._panel_expand_button.toolTip() == window._tr("sidebar_wider_tooltip")
        assert window._settings_scroll.minimumWidth() > before_min_width
        assert window._sidebar_panel_sizes[1] > before[1]
        assert after[1] >= before[1]

        window._set_sidebar_panel_visible(False)
        qapp.processEvents()
        assert window._sidebar_panel_hidden is True

        window._expand_sidebar_panel()
        qapp.processEvents()

        assert window._sidebar_panel_hidden is False
        assert window._settings_scroll.isVisible()
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_panel_collapse_button_narrows_control_panel(qapp) -> None:
    window = PlayerWindow()
    try:
        window.resize(1366, 768)
        window.show()
        qapp.processEvents()

        window._expand_sidebar_panel()
        qapp.processEvents()
        expanded_sizes = list(window._sidebar_panel_sizes)
        expanded_min_width = window._settings_scroll.minimumWidth()

        window._collapse_sidebar_panel()
        qapp.processEvents()

        assert window._panel_collapse_button.toolTip() == window._tr("sidebar_narrower_tooltip")
        assert window._settings_scroll.minimumWidth() == DEFAULT_SIDEBAR_PANEL_WIDTH
        assert window._sidebar_panel_sizes[1] < expanded_sizes[1]
        assert window._sidebar_panel_sizes[0] > expanded_sizes[0]
        assert expanded_min_width > DEFAULT_SIDEBAR_PANEL_WIDTH

        window._set_sidebar_panel_visible(False)
        qapp.processEvents()
        assert window._sidebar_panel_hidden is True

        window._collapse_sidebar_panel()
        qapp.processEvents()

        assert window._sidebar_panel_hidden is False
        assert window._settings_scroll.isVisible()
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_sidebar_header_stays_outside_scroll_area(qapp) -> None:
    window = PlayerWindow()
    try:
        assert window._splitter.widget(1) is window._settings_scroll
        assert not isinstance(window._settings_scroll, QScrollArea)
        assert isinstance(window._settings_tabs.widget(0), QScrollArea)
        assert window._settings_tabs.parentWidget() is window._settings_scroll

        window._settings_tabs.setCurrentIndex(5)
        qapp.processEvents()

        assert window._settings_tab_contains(window._settings_tabs.currentWidget(), window._runtime_tab_widget)
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_offline_models_manager_tab_exists(qapp) -> None:
    window = PlayerWindow()
    try:
        assert hasattr(window, "_offline_models_tab_widget")
        assert "whisper" in window._offline_model_rows
        assert "adult_extractors" in window._offline_model_rows
        assert "telegram_client" in window._offline_model_rows
        assert "backup" in window._offline_model_rows
        assert window._offline_model_target_text(window._offline_model_spec("adult_extractors")) == (
            "ai-player-adult-extractors"
        )
        assert window._offline_model_target_text(window._offline_model_spec("telegram_client")) == (
            "ai-player-telegram-client"
        )
        assert window._offline_model_spec("adult_extractors")["script"] == "install_adult_extractors.ps1"
        assert window._offline_model_spec("telegram_client")["script"] == "install_telegram_client.ps1"
        for key in ("whisper", "translation", "vieneu", "ocr", "speaker_gender"):
            button = window._offline_model_rows[key]["button"]
            assert isinstance(button, QPushButton)
            assert button.property("i18n_key") == "offline_models_download"
        assert window._offline_model_rows["adult_extractors"]["button"].property("i18n_key") == "offline_models_install"
        assert window._offline_model_rows["telegram_client"]["button"].property("i18n_key") == "offline_models_install"
        assert window._offline_model_rows["portable"]["button"].property("i18n_key") == "offline_models_build"
        assert window._offline_model_rows["backup"]["button"].property("i18n_key") == "offline_models_backup_action"
        assert window._settings_tabs.count() == 6
        window._settings_tabs.setCurrentIndex(2)
        qapp.processEvents()
        assert window._settings_tab_contains(window._settings_tabs.currentWidget(), window._offline_models_tab_widget)
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_player_window_guide_and_device_auto_follow_language(qapp) -> None:
    window = PlayerWindow()
    try:
        window._set_combo_data(window._ui_language_combo, "en")
        qapp.processEvents()
        assert "Start from your goal" in window._user_guide_html()
        assert "Quick workflow" in window._user_guide_html()
        assert "Common fixes" in window._user_guide_html()
        assert "Quy trình nhanh" not in window._user_guide_html()
        assert [title for title, _html in window._user_guide_tabs()] == [
            "Workflow",
            "Sources",
            "Current setup",
            "Reference",
        ]
        assert "Mainstream video platforms" in window._user_guide_html()
        assert window._capture_system_device_combo.itemText(0) == "Auto"

        window._set_combo_data(window._ui_language_combo, "vi")
        qapp.processEvents()
        assert "Chọn nhanh theo mục tiêu" in window._user_guide_html()
        assert "Quy trình nhanh" in window._user_guide_html()
        assert "Sự cố thường gặp" in window._user_guide_html()
        assert "Nền tảng video phổ biến" in window._user_guide_html()
        assert "AI_PLAYER_EXTRA_YTDLP_HOSTS" in window._user_guide_html()
        assert len(window._user_guide_tabs()) == 4
        assert window._capture_system_device_combo.itemText(0) == "Tự động"
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_translation_model_combo_drops_incompatible_current_model(qapp) -> None:
    window = PlayerWindow()
    try:
        window._set_combo_data(window._translator_combo, "nllb")
        window._refresh_translation_models(LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH)
        qapp.processEvents()
        nllb_models = [window._nllb_model_combo.itemData(index) for index in range(window._nllb_model_combo.count())]
        assert LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH not in nllb_models
        assert window._nllb_model_combo.currentData() == LOCAL_TRANSLATION_MODEL_PATH

        window._set_combo_data(window._translator_combo, "nllb_ct2")
        window._refresh_translation_models(LOCAL_TRANSLATION_MODEL_PATH)
        qapp.processEvents()
        ct2_models = [window._nllb_model_combo.itemData(index) for index in range(window._nllb_model_combo.count())]
        assert LOCAL_TRANSLATION_MODEL_PATH not in ct2_models
        assert window._nllb_model_combo.currentData() == LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_source_filter_mode_combo_excludes_auto(qapp) -> None:
    window = PlayerWindow()
    try:
        modes = [
            window._source_filter_mode_combo.itemData(index)
            for index in range(window._source_filter_mode_combo.count())
        ]

        assert modes == ["fast", "ai"]
        assert window._source_filter_mode_combo.findData("auto") == -1
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_video_url_full_cache_is_below_auto_match_audio(qapp) -> None:
    window = PlayerWindow()
    try:
        window.show()
        qapp.processEvents()

        auto_match_y = window._auto_match_audio_check.mapTo(
            window,
            window._auto_match_audio_check.rect().topLeft(),
        ).y()
        full_cache_y = window._video_url_full_cache_check.mapTo(
            window,
            window._video_url_full_cache_check.rect().topLeft(),
        ).y()

        assert full_cache_y > auto_match_y
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_video_url_forces_full_cache_when_source_filter_is_enabled(qapp) -> None:
    window = PlayerWindow()
    try:
        window._video_url_full_cache_check.setChecked(False)
        window._source_filter_check.setChecked(False)
        qapp.processEvents()
        assert window._effective_video_url_full_cache() is False
        assert window._source_filter_forces_video_url_full_cache() is False

        window._source_filter_check.setChecked(True)
        qapp.processEvents()
        assert window._effective_video_url_full_cache() is True
        assert window._source_filter_forces_video_url_full_cache() is True

        window._video_url_full_cache_check.setChecked(True)
        qapp.processEvents()
        assert window._effective_video_url_full_cache() is True
        assert window._source_filter_forces_video_url_full_cache() is False
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_subtitle_background_combo_updates_overlay_style(qapp) -> None:
    window = PlayerWindow()
    try:
        window._set_combo_data(window._subtitle_background_combo, "rgba(0, 0, 0, 160)")
        qapp.processEvents()

        assert window._subtitle_background_color() == "rgba(0, 0, 0, 160)"
        assert window._subtitle_overlay.subtitleBackgroundColor().getRgb() == (0, 0, 0, 160)
        assert window._subtitle_overlay.styleSheet() == ""
        assert window._subtitle_overlay.font().pixelSize() == window._subtitle_font_size()
        assert window._subtitle_overlay.frameShape() == QFrame.Shape.NoFrame
        assert window._subtitle_overlay.lineWidth() == 0
        assert window._subtitle_overlay.midLineWidth() == 0
        assert window._subtitle_overlay.parentWidget() is None
        assert window._subtitle_overlay.isWindow()
        assert window._subtitle_overlay.windowFlags() & Qt.NoDropShadowWindowHint
        assert window._subtitle_overlay.windowFlags() & Qt.BypassWindowManagerHint
        assert window._subtitle_overlay.testAttribute(Qt.WA_NoSystemBackground)
        assert not window._subtitle_overlay.testAttribute(Qt.WA_StyledBackground)
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_timed_live_subtitle_tracks_source_audio_time(qapp, monkeypatch) -> None:
    window = PlayerWindow()
    try:
        current_ms = {"value": 0}
        fake_player = SimpleNamespace(get_time_ms=lambda: current_ms["value"], stop=lambda: None)
        monkeypatch.setattr(window, "_player", fake_player)
        window._set_combo_data(window._subtitle_mode_combo, "target")
        window._set_timed_live_subtitle(10.0, 2.0, "source line", "target line")

        current_ms["value"] = 9000
        window._update_subtitle_overlay()
        assert not window._subtitle_overlay.isVisible()

        current_ms["value"] = 10500
        window._update_subtitle_overlay()
        assert window._subtitle_overlay.text() == "target line"
        assert window._subtitle_overlay.isVisible()

        current_ms["value"] = 14000
        window._update_subtitle_overlay()
        assert not window._subtitle_overlay.isVisible()
        window._settings_save_timer.stop()
    finally:
        window.close()
