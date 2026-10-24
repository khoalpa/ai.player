from __future__ import annotations

from ai_player.ui.features import layout as layout_types
from ai_player.ui.views.settings_sections import SettingsSections


def build(context, source_bar, video_panel, sections: SettingsSections):
    context.layout._transcript = layout_types.QTextEdit()
    context.layout._transcript.setObjectName("transcript")
    context.layout._transcript.setReadOnly(True)
    context.layout._transcript_view_combo = context.ui._option_combo(
        layout_types._dropdown_options("transcript_views", context.config.gui_language), "all"
    )
    context.layout._transcript_view_combo.setAccessibleName(context.settings._tr("show_transcript"))
    context.layout._transcript_view_combo.setToolTip(context.settings._tr("show_transcript"))
    context.layout._transcript_view_combo.currentIndexChanged.connect(context.transcript._render_transcript)
    context.layout._transcript_type_combo = context.ui._option_combo(
        layout_types._dropdown_options("transcript_types", context.config.gui_language), "all"
    )
    context.layout._transcript_type_combo.setAccessibleName(context.settings._tr("transcript_type"))
    context.layout._transcript_type_combo.setToolTip(context.settings._tr("transcript_type"))
    context.layout._transcript_type_combo.currentIndexChanged.connect(context.transcript._render_transcript)
    context.layout._export_transcript_button = context.ui._make_button(
        "export_transcript",
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_DialogSaveButton),
    )
    context.layout._export_transcript_button.clicked.connect(context.transcript._export_transcript)
    context.layout._transcript.setPlaceholderText(context.settings._tr("transcript_placeholder"))

    basic_tab = layout_types.build_basic_settings_tab(
        context,
        basic_source_grid=sections.basic_source_grid,
        basic_voice_grid=sections.basic_voice_grid,
        basic_playback_grid=sections.basic_playback_grid,
        basic_processing_grid=sections.basic_processing_grid,
    )
    models_tab = layout_types.build_models_settings_tab(
        context,
        asr_grid=sections.asr_grid,
        translation_grid=sections.translation_grid,
        tts_grid=sections.tts_grid,
        tts_advanced_grid=sections.tts_advanced_grid,
        voice_ai_grid=sections.voice_ai_grid,
        ocr_grid=sections.ocr_grid,
        cleanup_grid=sections.cleanup_grid,
    )
    advanced_tab = layout_types.build_advanced_settings_tab(
        context,
        advanced_terms_grid=sections.advanced_terms_grid,
        advanced_timing_grid=sections.advanced_timing_grid,
        advanced_match_grid=sections.advanced_match_grid,
        advanced_playback_grid=sections.advanced_playback_grid,
        advanced_capture_grid=sections.advanced_capture_grid,
    )
    readiness_tab = context.readiness._readiness_tab()
    task_center_tab = context.task_center._task_center_tab()
    transcript_tab = layout_types.build_transcript_settings_tab(context)
    runtime_tab = context.runtime._runtime_tab()
    offline_models_tab = context.offline_models._offline_models_tab()

    context.layout._settings_tabs = layout_types.build_settings_tabs(
        context,
        readiness_tab=readiness_tab,
        task_center_tab=task_center_tab,
        basic_tab=basic_tab,
        models_tab=models_tab,
        offline_models_tab=offline_models_tab,
        advanced_tab=advanced_tab,
        transcript_tab=transcript_tab,
        runtime_tab=runtime_tab,
    )
    settings_panel = layout_types.build_settings_panel(context, context.layout._settings_tabs)
    context.settings._refresh_tts_options()
    context.settings._sync_auto_voice_controls_enabled()
    context.settings._sync_auto_match_controls_enabled()
    context.settings._sync_asr_controls()
    context.settings._sync_ocr_controls()
    context.settings._sync_translation_model_combo_enabled()
    context.settings._sync_source_filter_controls()
    context.settings._sync_transcript_cleanup_controls()
    context.settings._sync_vieneu_advanced_controls()
    context.settings._refresh_preset_inspector()
    context.layout._apply_control_tooltips()
    context.layout._performance_preset_combo.currentIndexChanged.connect(
        context.settings._apply_selected_performance_preset
    )
    context.settings._connect_settings_autosave()
    context.layout._connect_media_start_context_refresh()

    context.layout._settings_scroll = settings_panel

    context.layout._splitter = layout_types.QSplitter(layout_types.Qt.Horizontal)
    context.layout._splitter.addWidget(video_panel)
    context.layout._splitter.addWidget(context.layout._settings_scroll)
    context.layout._splitter.setStretchFactor(0, 1)
    context.layout._splitter.setStretchFactor(1, 0)
    context.layout._splitter.setSizes(list(layout_types.DEFAULT_SIDEBAR_PANEL_SIZES))

    root = layout_types.QVBoxLayout()
    context.layout._root_layout = root
    root.setContentsMargins(14, 12, 14, 10)
    root.setSpacing(10)
    root.addWidget(source_bar)
    context.layout._task_drawer = context.layout._task_drawer_panel()
    root.addWidget(context.layout._task_drawer)
    root.addWidget(context.layout._splitter, 1)

    container = layout_types.QWidget()
    container.setObjectName("root")
    container.setLayout(root)
    context.window.setCentralWidget(container)
    context.window.setStatusBar(layout_types.QStatusBar(context.window))
    context.layout._media_stack.currentChanged.connect(lambda *_args: context.media_browser._sync_media_browser_state())
    url_changed = getattr(context.layout._video_placeholder, "urlChanged", None)
    if url_changed is not None:
        url_changed.connect(lambda *_args: context.media_browser._sync_media_browser_state())
    context.media_browser._sync_media_browser_state()
    context.media._sync_panel_visibility_buttons()
    context.layout._sync_media_start_overlay()
    context.layout._set_simple_sidebar_mode(True)
    if context.has("_refresh_next_action_panel"):
        context.transcript._refresh_next_action_panel()
