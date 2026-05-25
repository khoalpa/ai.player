from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QScrollArea

from ai_player.core.config import LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH, LOCAL_TRANSLATION_MODEL_PATH
from ai_player.services.document_reader import DocumentPage
from ai_player.ui.player_window import PlayerWindow
from ai_player.ui.player_window_layout import _subtitle_qcolor
from ai_player.ui.player_window_media import _document_ms_value, _document_seconds_value


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
        assert "backup" in window._offline_model_rows
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
        assert "background-color: transparent" in window._subtitle_overlay.styleSheet()
        assert window._subtitle_overlay.testAttribute(Qt.WA_StyledBackground)
        window._settings_save_timer.stop()
    finally:
        window.close()
