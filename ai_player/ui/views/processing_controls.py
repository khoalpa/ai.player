from __future__ import annotations

from ai_player.ui.features import layout as layout_types


def build(context):
    context.layout._fullscreen_escape_shortcut = layout_types.QShortcut(
        layout_types.QKeySequence("Esc"), context.window
    )
    context.layout._fullscreen_escape_shortcut.setContext(layout_types.Qt.ApplicationShortcut)
    context.layout._fullscreen_escape_shortcut.activated.connect(context.media._handle_escape_shortcut)
    context.layout._command_palette_shortcut = layout_types.QShortcut(
        layout_types.QKeySequence("Ctrl+K"), context.window
    )
    context.layout._command_palette_shortcut.setContext(layout_types.Qt.ApplicationShortcut)
    context.layout._command_palette_shortcut.activated.connect(context.layout._show_command_palette)

    context.layout._play_button = context.ui._icon_button(layout_types.QStyle.StandardPixmap.SP_MediaPlay, "play")
    context.layout._play_button.clicked.connect(context.dubbing._play)
    context.layout._pause_button = context.ui._icon_button(layout_types.QStyle.StandardPixmap.SP_MediaPause, "pause")
    context.layout._pause_button.clicked.connect(context.dubbing._pause)
    context.layout._stop_button = context.ui._icon_button(layout_types.QStyle.StandardPixmap.SP_MediaStop, "stop")
    context.layout._stop_button.clicked.connect(context.dubbing._stop)
    context.layout._previous_page_button = context.ui._icon_button(
        layout_types.QStyle.StandardPixmap.SP_MediaSkipBackward, "previous"
    )
    context.layout._previous_page_button.clicked.connect(context.media._previous_media_item)
    context.layout._next_page_button = context.ui._icon_button(
        layout_types.QStyle.StandardPixmap.SP_MediaSkipForward, "next"
    )
    context.layout._next_page_button.clicked.connect(context.media._next_media_item)
    layout_types.build_media_browser_buttons(context)
    context.layout._subtitle_mode_combo = layout_types.QComboBox()
    context.layout._subtitle_mode_combo.addItem("...", "off")
    context.layout._subtitle_mode_combo.addItem(context.settings._tr("source"), "source")
    context.layout._subtitle_mode_combo.addItem(context.settings._tr("target"), "target")
    context.layout._subtitle_mode_combo.setCurrentIndex(max(0, context.layout._subtitle_mode_combo.findData("target")))
    context.layout._subtitle_mode_combo.setFixedWidth(80)
    context.layout._subtitle_mode_combo.currentIndexChanged.connect(context.sources._subtitle_mode_changed)
    context.layout._subtitle_size_combo = layout_types.QComboBox()
    context.layout._subtitle_size_combo.addItem(context.settings._tr("small"), 18)
    context.layout._subtitle_size_combo.addItem(context.settings._tr("medium"), 24)
    context.layout._subtitle_size_combo.addItem(context.settings._tr("large"), 32)
    context.layout._subtitle_size_combo.addItem(context.settings._tr("very_large"), 40)
    context.layout._subtitle_size_combo.setCurrentIndex(max(0, context.layout._subtitle_size_combo.findData(24)))
    context.layout._subtitle_size_combo.setFixedWidth(80)
    context.layout._subtitle_size_combo.currentIndexChanged.connect(context.sources._subtitle_size_changed)
    context.layout._subtitle_color_combo = layout_types.QComboBox()
    context.layout._subtitle_color_combo.addItem(context.settings._tr("black"), "#000000")
    context.layout._subtitle_color_combo.addItem(context.settings._tr("white"), "#ffffff")
    context.layout._subtitle_color_combo.addItem(context.settings._tr("yellow"), "#ffd54a")
    context.layout._subtitle_color_combo.addItem(context.settings._tr("blue"), "#66d9ff")
    context.layout._subtitle_color_combo.addItem(context.settings._tr("green"), "#7ee787")
    context.layout._subtitle_color_combo.addItem(context.settings._tr("pink"), "#ff8bd1")
    context.layout._subtitle_color_combo.setCurrentIndex(
        max(0, context.layout._subtitle_color_combo.findData("#ffd54a"))
    )
    context.layout._subtitle_color_combo.setFixedWidth(80)
    context.layout._subtitle_color_combo.currentIndexChanged.connect(context.sources._subtitle_size_changed)
    context.layout._subtitle_background_combo = layout_types.QComboBox()
    context.layout._subtitle_background_combo.addItem(context.settings._tr("transparent"), "rgba(0, 0, 0, 0)")
    context.layout._subtitle_background_combo.addItem(context.settings._tr("black"), "rgba(0, 0, 0, 160)")
    context.layout._subtitle_background_combo.addItem(context.settings._tr("white"), "rgba(255, 255, 255, 190)")
    context.layout._subtitle_background_combo.addItem(context.settings._tr("yellow"), "rgba(255, 213, 74, 180)")
    context.layout._subtitle_background_combo.addItem(context.settings._tr("blue"), "rgba(102, 217, 255, 170)")
    context.layout._subtitle_background_combo.addItem(context.settings._tr("green"), "rgba(126, 231, 135, 170)")
    context.layout._subtitle_background_combo.addItem(context.settings._tr("pink"), "rgba(255, 139, 209, 170)")
    context.layout._subtitle_background_combo.setCurrentIndex(0)
    context.layout._subtitle_background_combo.setFixedWidth(112)
    context.layout._subtitle_background_combo.setToolTip(context.settings._tr("subtitle_background_tooltip"))
    context.layout._subtitle_background_combo.setProperty("i18n_tooltip_key", "subtitle_background_tooltip")
    context.layout._subtitle_background_combo.currentIndexChanged.connect(context.sources._subtitle_size_changed)
    context.layout._display_options_button = context.ui._make_button(
        "display_options",
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_FileDialogDetailedView),
    )
    context.layout._display_options_button.setObjectName("sourceButton")
    context.layout._display_options_button.setCheckable(True)
    context.layout._display_options_button.setToolTip(context.settings._tr("display_options_tooltip"))
    context.layout._display_options_button.setProperty("i18n_tooltip_key", "display_options_tooltip")
    context.layout._display_options_button.toggled.connect(context.layout._toggle_display_options)

    context.layout._position_slider = layout_types.QSlider(layout_types.Qt.Horizontal)
    context.layout._position_slider.setRange(0, 1000)
    context.layout._position_slider.sliderPressed.connect(context.media._begin_seek)
    context.layout._position_slider.sliderReleased.connect(context.media._end_seek)

    context.layout._time_label = layout_types.QLabel("00:00 / 00:00")
    context.layout._time_label.setObjectName("timeLabel")
    context.layout._time_label.setMinimumWidth(104)

    context.layout._cache_status_panel = layout_types.QFrame()
    context.layout._cache_status_panel.setObjectName("cacheStatusPanel")
    cache_status_layout = layout_types.QHBoxLayout(context.layout._cache_status_panel)
    cache_status_layout.setContentsMargins(0, 0, 0, 0)
    cache_status_layout.setSpacing(8)
    context.layout._cache_status_progress = layout_types.QProgressBar()
    context.layout._cache_status_progress.setRange(0, 100)
    context.layout._cache_status_progress.setValue(0)
    context.layout._cache_status_progress.setFixedWidth(180)
    context.layout._cache_status_label = layout_types.QLabel(context.settings._tr("cache_status_starting"))
    context.layout._cache_status_label.setWordWrap(False)
    context.layout._cache_status_label.setSizePolicy(layout_types.QSizePolicy.Expanding, layout_types.QSizePolicy.Fixed)
    context.layout._cache_play_now_button = layout_types.QPushButton(context.settings._tr("cache_play_now"))
    context.layout._cache_play_now_button.setEnabled(False)
    context.layout._cache_play_now_button.clicked.connect(context.sources._play_video_url_stream_now)
    cache_status_layout.addWidget(context.layout._cache_status_progress)
    cache_status_layout.addWidget(context.layout._cache_status_label, 1)
    cache_status_layout.addWidget(context.layout._cache_play_now_button)
    context.layout._cache_status_panel.hide()

    context.layout._volume_slider = layout_types.QSlider(layout_types.Qt.Horizontal)
    context.layout._volume_slider.setRange(0, 100)
    context.layout._volume_slider.setValue(context.config.original_audio_volume)
    context.layout._volume_slider.setSizePolicy(layout_types.QSizePolicy.Expanding, layout_types.QSizePolicy.Fixed)
    context.layout._volume_slider.valueChanged.connect(context.media._set_volume)

    context.layout._source_filter_check = layout_types.QCheckBox(context.settings._tr("source_filter"))
    context.layout._source_filter_check.setProperty("i18n_key", "source_filter")
    context.layout._source_filter_check.setChecked(context.config.original_audio_voice_filter)
    context.layout._source_filter_check.setToolTip(context.settings._tr("source_filter_tooltip"))
    context.layout._source_filter_check.setProperty("i18n_tooltip_key", "source_filter_tooltip")
    context.layout._source_filter_check.toggled.connect(context.media._source_voice_filter_changed)
    context.layout._source_filter_mode_combo = layout_types.QComboBox()
    context.layout._source_filter_mode_combo.addItem(context.settings._tr("source_filter_mode_ai"), "ai")
    context.layout._source_filter_mode_combo.setCurrentIndex(
        max(0, context.layout._source_filter_mode_combo.findData(context.config.original_audio_voice_filter_mode))
    )
    context.layout._source_filter_mode_combo.setToolTip(context.settings._tr("source_filter_mode_tooltip"))
    context.layout._source_filter_mode_combo.setProperty("i18n_tooltip_key", "source_filter_mode_tooltip")
    context.layout._source_filter_mode_combo.currentIndexChanged.connect(
        context.media._source_voice_filter_mode_changed
    )
    context.layout._source_filter_model_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._source_filter_model_combo)
    for model in sorted(layout_types.SOURCE_VOICE_FILTER_DEMUCS_MODELS):
        context.layout._source_filter_model_combo.addItem(model, model)
    selected_filter_model = layout_types.normalize_source_voice_filter_model(
        context.config.original_audio_voice_filter_model
    )
    context.layout._source_filter_model_combo.setCurrentIndex(
        max(0, context.layout._source_filter_model_combo.findData(selected_filter_model))
    )
    context.layout._source_filter_model_combo.currentIndexChanged.connect(
        context.media._source_voice_filter_mode_changed
    )

    context.layout._dub_volume_slider = layout_types.QSlider(layout_types.Qt.Horizontal)
    context.layout._dub_volume_slider.setRange(0, 100)
    context.layout._dub_volume_slider.setValue(context.config.dubbing_voice_volume)
    context.layout._dub_volume_slider.setSizePolicy(layout_types.QSizePolicy.Expanding, layout_types.QSizePolicy.Fixed)
    context.layout._dub_volume_slider.valueChanged.connect(context.media._set_dub_volume_status)

    controls = layout_types.QFrame()
    controls.setObjectName("controls")
    controls.setSizePolicy(layout_types.QSizePolicy.Expanding, layout_types.QSizePolicy.Fixed)
    context.layout._controls = controls
    controls_layout = layout_types.QVBoxLayout(controls)
    controls_layout.setContentsMargins(12, 8, 12, 8)
    controls_layout.setSpacing(8)
    timeline_layout = layout_types.QHBoxLayout()
    timeline_layout.setSpacing(6)
    timeline_layout.addWidget(context.layout._position_slider, 1)
    timeline_layout.addWidget(context.layout._time_label)
    timeline_layout.addWidget(context.ui._audio_slider_control("original_audio", context.layout._volume_slider))

    playback_layout = layout_types.QHBoxLayout()
    playback_layout.setSpacing(6)
    playback_layout.addWidget(context.layout._play_button)
    playback_layout.addWidget(context.layout._pause_button)
    playback_layout.addWidget(context.layout._stop_button)
    playback_layout.addWidget(context.layout._previous_page_button)
    playback_layout.addWidget(context.layout._next_page_button)
    playback_layout.addWidget(context.bindings._media_home_button)
    playback_layout.addWidget(context.bindings._telegram_browser_button)
    playback_layout.addWidget(context.layout._display_options_button)
    playback_layout.addWidget(context.layout._focus_media_button)
    playback_layout.addStretch(1)
    playback_layout.addWidget(context.ui._audio_slider_control("dub_audio", context.layout._dub_volume_slider))
    display_options = layout_types.QFrame()
    display_options.setObjectName("displayOptionsPanel")
    context.layout._display_options_panel = display_options
    display_options_layout = layout_types.QHBoxLayout(display_options)
    display_options_layout.setContentsMargins(8, 6, 8, 6)
    display_options_layout.setSpacing(6)
    display_options_layout.addWidget(context.ui._field_label("frame"))
    display_options_layout.addWidget(context.layout._aspect_combo)
    display_options_layout.addWidget(context.layout._playback_quality_combo)
    display_options_layout.addSpacing(6)
    display_options_layout.addWidget(context.ui._field_label("subtitle"))
    display_options_layout.addWidget(context.layout._subtitle_mode_combo)
    display_options_layout.addWidget(context.layout._subtitle_size_combo)
    display_options_layout.addWidget(context.layout._subtitle_color_combo)
    display_options_layout.addWidget(context.layout._subtitle_background_combo)
    display_options_layout.addStretch(1)
    display_options.hide()
    controls_layout.addLayout(timeline_layout)
    controls_layout.addWidget(context.layout._cache_status_panel)
    controls_layout.addLayout(playback_layout)
    controls_layout.addWidget(display_options)

    panel_visibility_bar = layout_types.QFrame()
    panel_visibility_bar.setObjectName("panelVisibilityBar")
    context.layout._panel_visibility_bar = panel_visibility_bar
    panel_visibility_layout = layout_types.QHBoxLayout(panel_visibility_bar)
    panel_visibility_layout.setContentsMargins(0, 0, 0, 0)
    panel_visibility_layout.setSpacing(6)
    panel_visibility_layout.addStretch(1)
    panel_visibility_layout.addWidget(context.layout._top_panel_toggle_button)
    panel_visibility_layout.addWidget(context.layout._bottom_panel_toggle_button)
    panel_visibility_layout.addWidget(context.layout._right_panel_toggle_button)
    context.layout._panel_visibility_buttons = (
        context.layout._top_panel_toggle_button,
        context.layout._bottom_panel_toggle_button,
        context.layout._right_panel_toggle_button,
    )

    video_panel = layout_types.QFrame()
    video_panel.setObjectName("videoPanel")
    context.layout._video_panel = video_panel
    video_layout = layout_types.QVBoxLayout(video_panel)
    context.layout._video_layout = video_layout
    video_layout.setContentsMargins(12, 12, 12, 12)
    video_layout.setSpacing(10)
    video_layout.addWidget(context.media.frame.frame, 1, layout_types.Qt.AlignCenter)
    video_layout.addWidget(panel_visibility_bar)
    video_layout.addWidget(controls)
    video_layout.setStretch(0, 1)
    video_layout.setStretch(1, 0)
    video_layout.setStretch(2, 0)

    context.layout._dub_button = context.ui._make_button(
        "dub_button",
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_MediaVolume),
    )
    context.layout._dub_button.setObjectName("dubButton")
    context.layout._dub_button.setCheckable(True)
    context.layout._dub_button.setChecked(context.media.playback.dubbing_auto_enabled)
    context.layout._dub_button.clicked.connect(context.dubbing._toggle_dubbing)

    context.layout._audio_source_combo = context.ui._option_combo(
        layout_types._dropdown_options("audio_sources", context.config.gui_language),
        context.config.audio_source,
    )
    context.layout._audio_source_combo.currentIndexChanged.connect(context.sources._audio_source_changed)
    context.layout._transcript_path_edit = layout_types.QLineEdit(context.config.transcript_path)
    context.layout._transcript_path_edit.setPlaceholderText(context.settings._tr("transcript_file_placeholder"))
    context.layout._transcript_path_edit.setClearButtonEnabled(True)
    context.layout._transcript_path_edit.textEdited.connect(context.settings._queue_save_settings)
    context.layout._transcript_path_edit.textChanged.connect(context.sources._invalidate_subtitle_entries)
    context.layout._transcript_file_button = context.ui._icon_button(
        layout_types.QStyle.StandardPixmap.SP_FileDialogStart, "choose"
    )
    context.layout._transcript_file_button.clicked.connect(context.sources._choose_transcript_file)

    context.layout._source_language_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._source_language_combo)
    for option in layout_types.available_language_options(include_auto=True, language_id=context.config.gui_language):
        context.layout._source_language_combo.addItem(layout_types._ui_label(option.name), option.id)
    context.layout._source_language_combo.setCurrentIndex(
        max(0, context.layout._source_language_combo.findData(context.config.source_language))
    )
    context.layout._source_language_combo.currentIndexChanged.connect(context.settings._language_pair_changed)
    context.layout._target_language_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._target_language_combo)
    for option in layout_types.available_language_options(include_auto=False, language_id=context.config.gui_language):
        context.layout._target_language_combo.addItem(layout_types._ui_label(option.name), option.id)
    context.layout._target_language_combo.setCurrentIndex(
        max(0, context.layout._target_language_combo.findData(context.config.target_language))
    )
    context.layout._target_language_combo.currentIndexChanged.connect(context.settings._language_pair_changed)

    context.layout._advanced_provider_options_check = layout_types.QCheckBox(
        context.settings._tr("show_advanced_provider_options")
    )
    context.layout._advanced_provider_options_check.setProperty("i18n_key", "show_advanced_provider_options")
    context.layout._advanced_provider_options_check.setToolTip(
        context.settings._tr("show_advanced_provider_options_tooltip")
    )
    context.layout._advanced_provider_options_check.setProperty(
        "i18n_tooltip_key",
        "show_advanced_provider_options_tooltip",
    )
    context.layout._advanced_provider_options_check.setChecked(context.config.show_advanced_provider_options)

    context.layout._asr_provider_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._asr_provider_combo)
    context.settings._refresh_asr_provider_options()
    return video_panel
