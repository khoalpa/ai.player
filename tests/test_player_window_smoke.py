from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QScrollArea

from ai_player.core.config import LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH, LOCAL_TRANSLATION_MODEL_PATH
from ai_player.ui.player_window import PlayerWindow


def test_player_window_constructs_offscreen(qapp) -> None:
    window = PlayerWindow()
    try:
        assert window.windowTitle()
    finally:
        window.close()


def test_player_window_runtime_format_helpers(qapp) -> None:
    window = PlayerWindow()
    try:
        assert window._format_seconds(65) == "01:05"
        assert window._format_bytes(1024) == "1.0 KB"
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
        assert window._controls.isVisible()

        window._set_sidebar_panel_visible(False)
        qapp.processEvents()
        qapp.processEvents()

        assert window._sidebar_panel_hidden is True
        assert not window._controls.isVisible()
        assert window._splitter.sizes()[1] == 0
        assert window._media_frame.width() > initial_width

        window._set_sidebar_panel_visible(True)
        qapp.processEvents()

        assert window._sidebar_panel_hidden is False
        assert window._controls.isVisible()
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

        window._settings_tabs.setCurrentIndex(4)
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
        assert "backup" in window._offline_model_rows
        assert window._settings_tabs.count() == 6
        window._settings_tabs.setCurrentIndex(5)
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
        assert "Quick workflow" in window._user_guide_html()
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
        assert "Quy trình nhanh" in window._user_guide_html()
        assert "Nền tảng video phổ biến" in window._user_guide_html()
        assert "BuomTV và mirror" not in window._user_guide_html()
        assert "Adult video" in window._user_guide_html()
        assert "buomtv.*" in window._user_guide_html()
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
