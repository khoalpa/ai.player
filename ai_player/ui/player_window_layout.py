from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPalette, QShortcut
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ai_player.core.runtime_catalog import (
    available_gui_language_options,
    available_language_options,
    available_local_llm_options,
)
from ai_player.services.capture_sources import list_capture_device_options
from ai_player.services.translation import available_translators, normalize_translator_provider
from ai_player.services.tts import available_tts_providers, available_vieneu_modes, normalize_tts_provider
from ai_player.ui.player_window_utils import (
    dropdown_options as _dropdown_options,
)
from ai_player.ui.player_window_utils import (
    ui_label as _ui_label,
)


class PlayerLayoutMixin:
    def _build_ui(self) -> None:
        self._source_label = QLabel(self._tr("source_empty"))
        self._source_label.setObjectName("sourceLabel")
        self._source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self._open_file_button = self._make_button(
            "open_video",
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
        )
        self._open_file_button.setObjectName("primaryButton")
        self._open_file_button.clicked.connect(self._open_video)
        self._open_url_button = self._make_button(
            "open_url",
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
        )
        self._open_url_button.setObjectName("primaryButton")
        self._open_url_button.clicked.connect(self._open_video_url)
        self._open_document_button = self._make_button(
            "open_document",
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon),
        )
        self._open_document_button.setObjectName("primaryButton")
        self._open_document_button.clicked.connect(self._open_document)
        self._meeting_button = self._make_button(
            "start",
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
        )
        self._meeting_button.setObjectName("primaryButton")
        self._meeting_button.clicked.connect(self._toggle_meeting)
        self._ui_language_combo = QComboBox()
        self._compact_combo(self._ui_language_combo)
        self._ui_language_combo.setMinimumContentsLength(10)
        for option in available_gui_language_options():
            self._ui_language_combo.addItem(_ui_label(option.name), option.id)
        self._ui_language_combo.setCurrentIndex(max(0, self._ui_language_combo.findData(self._config.gui_language)))
        self._ui_language_combo.currentIndexChanged.connect(self._gui_language_changed)
        self._export_button = self._make_button(
            "export",
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton),
        )
        self._export_button.setObjectName("primaryButton")
        self._export_button.clicked.connect(self._show_export_menu)
        self._video_fullscreen_button = self._make_button("fullscreen", QIcon())
        self._video_fullscreen_button.setToolTip(self._tr("fullscreen_tooltip"))
        self._video_fullscreen_button.setProperty("i18n_tooltip_key", "fullscreen_tooltip")
        self._video_fullscreen_button.clicked.connect(self._toggle_video_fullscreen)
        self._panel_toggle_button = self._make_button("panel_hide", QIcon())
        self._panel_toggle_button.setToolTip(self._tr("panel_toggle_tooltip"))
        self._panel_toggle_button.setProperty("i18n_tooltip_key", "panel_toggle_tooltip")
        self._panel_toggle_button.clicked.connect(self._toggle_sidebar_panel)
        self._layout_reset_button = self._make_button("reset", QIcon())
        self._layout_reset_button.setToolTip(self._tr("reset_tooltip"))
        self._layout_reset_button.setProperty("i18n_tooltip_key", "reset_tooltip")
        self._layout_reset_button.clicked.connect(self._reset_app)
        self._help_button = self._make_button("help", QIcon())
        self._help_button.setToolTip(self._tr("help_tooltip"))
        self._help_button.setProperty("i18n_tooltip_key", "help_tooltip")
        self._help_button.clicked.connect(self._show_user_guide)

        source_bar = QFrame()
        source_bar.setObjectName("sourceBar")
        source_layout = QHBoxLayout(source_bar)
        source_layout.setContentsMargins(16, 12, 16, 12)
        source_layout.setSpacing(10)
        title = QLabel("AI Player")
        title.setObjectName("appTitle")
        source_layout.addWidget(title)
        source_layout.addWidget(self._source_label, 1)
        source_layout.addWidget(self._video_fullscreen_button)
        source_layout.addWidget(self._panel_toggle_button)
        source_layout.addWidget(self._layout_reset_button)
        source_layout.addWidget(self._help_button)
        source_layout.addWidget(self._open_file_button)
        source_layout.addWidget(self._open_url_button)
        source_layout.addWidget(self._open_document_button)
        source_layout.addWidget(self._meeting_button)
        source_layout.addWidget(self._export_button)
        source_layout.addWidget(self._ui_language_combo)

        self._video_widget = QVideoWidget()
        self._video_widget.setObjectName("videoSurface")
        self._video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._video_widget.setAspectRatioMode(Qt.IgnoreAspectRatio)
        video_palette = self._video_widget.palette()
        video_palette.setColor(QPalette.Window, QColor("#ffffff"))
        video_palette.setColor(QPalette.Base, QColor("#ffffff"))
        self._video_widget.setPalette(video_palette)
        self._video_widget.setAttribute(Qt.WA_NoSystemBackground, False)
        self._video_widget.setStyleSheet("background-color: #ffffff;")
        self._video_widget.setAutoFillBackground(True)
        self._video_widget.installEventFilter(self)
        self._video_placeholder = QFrame()
        self._video_placeholder.setObjectName("videoPlaceholder")
        self._video_placeholder.setAutoFillBackground(True)
        self._video_placeholder.installEventFilter(self)
        self._document_view = QTextEdit()
        self._document_view.setObjectName("documentView")
        self._document_view.setReadOnly(True)
        self._document_view.setFrameShape(QFrame.Shape.NoFrame)
        self._document_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._document_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._document_view.installEventFilter(self)
        self._document_view.document().setDocumentMargin(0)
        self._document_view.setPlaceholderText(self._tr("document_placeholder"))
        self._aspect_combo = self._option_combo(
            _dropdown_options("video_aspects", self._config.gui_language), self._config.video_aspect_ratio
        )
        self._aspect_combo.setFixedWidth(92)
        self._aspect_combo.currentIndexChanged.connect(self._video_aspect_changed)
        self._playback_quality_combo = self._option_combo(
            _dropdown_options("playback_video_qualities", self._config.gui_language),
            self._config.playback_video_quality,
        )
        self._playback_quality_combo.setFixedWidth(106)
        self._playback_quality_combo.currentIndexChanged.connect(self._playback_quality_changed)
        self._video_url_full_cache_check = QCheckBox(self._tr("video_url_full_cache"))
        self._video_url_full_cache_check.setProperty("i18n_key", "video_url_full_cache")
        self._video_url_full_cache_check.setChecked(self._config.video_url_full_cache)
        self._video_url_full_cache_check.setToolTip(self._tr("video_url_full_cache_tooltip"))
        self._video_url_full_cache_check.setProperty("i18n_tooltip_key", "video_url_full_cache_tooltip")
        self._media_stack = QStackedWidget()
        self._media_stack.addWidget(self._video_placeholder)
        self._media_stack.addWidget(self._video_widget)
        self._media_stack.addWidget(self._document_view)
        self._media_stack.setCurrentWidget(self._video_placeholder)
        self._media_stack.installEventFilter(self)
        self._media_frame = QFrame()
        self._media_frame.setObjectName("mediaFrame")
        self._media_frame.installEventFilter(self)
        media_frame_layout = QVBoxLayout(self._media_frame)
        media_frame_layout.setContentsMargins(0, 0, 0, 0)
        media_frame_layout.addWidget(self._media_stack)
        self._subtitle_overlay = QLabel()
        self._subtitle_overlay.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self._subtitle_overlay.setObjectName("subtitleOverlay")
        self._subtitle_overlay.setAlignment(Qt.AlignCenter)
        self._subtitle_overlay.setWordWrap(True)
        self._subtitle_overlay.setTextFormat(Qt.PlainText)
        self._subtitle_overlay.setFrameStyle(QFrame.NoFrame)
        self._subtitle_overlay.setLineWidth(0)
        self._subtitle_overlay.setMidLineWidth(0)
        self._subtitle_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._subtitle_overlay.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._subtitle_overlay.setAttribute(Qt.WA_TranslucentBackground, True)
        self._subtitle_overlay.setAttribute(Qt.WA_NoSystemBackground, True)
        self._subtitle_overlay.setAutoFillBackground(False)
        self._subtitle_overlay.hide()
        self._fullscreen_shortcut = QShortcut(QKeySequence("F11"), self)
        self._fullscreen_shortcut.setContext(Qt.ApplicationShortcut)
        self._fullscreen_shortcut.activated.connect(self._toggle_video_fullscreen)
        self._fullscreen_escape_shortcut = QShortcut(QKeySequence("Esc"), self)
        self._fullscreen_escape_shortcut.setContext(Qt.ApplicationShortcut)
        self._fullscreen_escape_shortcut.activated.connect(self._exit_video_fullscreen)

        self._play_button = self._icon_button(QStyle.StandardPixmap.SP_MediaPlay, "play")
        self._play_button.clicked.connect(self._play)
        self._pause_button = self._icon_button(QStyle.StandardPixmap.SP_MediaPause, "pause")
        self._pause_button.clicked.connect(self._pause)
        self._stop_button = self._icon_button(QStyle.StandardPixmap.SP_MediaStop, "stop")
        self._stop_button.clicked.connect(self._stop)
        self._previous_page_button = self._icon_button(QStyle.StandardPixmap.SP_MediaSkipBackward, "previous")
        self._previous_page_button.clicked.connect(self._previous_document_page)
        self._next_page_button = self._icon_button(QStyle.StandardPixmap.SP_MediaSkipForward, "next")
        self._next_page_button.clicked.connect(self._next_document_page)
        self._subtitle_mode_combo = QComboBox()
        self._subtitle_mode_combo.addItem("...", "off")
        self._subtitle_mode_combo.addItem(self._tr("source"), "source")
        self._subtitle_mode_combo.addItem(self._tr("target"), "target")
        self._subtitle_mode_combo.setCurrentIndex(0)
        self._subtitle_mode_combo.setFixedWidth(96)
        self._subtitle_mode_combo.currentIndexChanged.connect(self._subtitle_mode_changed)
        self._subtitle_size_combo = QComboBox()
        self._subtitle_size_combo.addItem(self._tr("small"), 18)
        self._subtitle_size_combo.addItem(self._tr("medium"), 24)
        self._subtitle_size_combo.addItem(self._tr("large"), 32)
        self._subtitle_size_combo.addItem(self._tr("very_large"), 40)
        self._subtitle_size_combo.setCurrentIndex(0)
        self._subtitle_size_combo.setFixedWidth(92)
        self._subtitle_size_combo.currentIndexChanged.connect(self._subtitle_size_changed)
        self._subtitle_color_combo = QComboBox()
        self._subtitle_color_combo.addItem(self._tr("black"), "#000000")
        self._subtitle_color_combo.addItem(self._tr("white"), "#ffffff")
        self._subtitle_color_combo.addItem(self._tr("yellow"), "#ffd54a")
        self._subtitle_color_combo.addItem(self._tr("blue"), "#66d9ff")
        self._subtitle_color_combo.addItem(self._tr("green"), "#7ee787")
        self._subtitle_color_combo.addItem(self._tr("pink"), "#ff8bd1")
        self._subtitle_color_combo.setCurrentIndex(0)
        self._subtitle_color_combo.setFixedWidth(92)
        self._subtitle_color_combo.currentIndexChanged.connect(self._subtitle_size_changed)

        self._position_slider = QSlider(Qt.Horizontal)
        self._position_slider.setRange(0, 1000)
        self._position_slider.sliderPressed.connect(self._begin_seek)
        self._position_slider.sliderReleased.connect(self._end_seek)

        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setObjectName("timeLabel")
        self._time_label.setMinimumWidth(104)

        self._volume_slider = QSlider(Qt.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(self._config.original_audio_volume)
        self._volume_slider.setFixedWidth(130)
        self._volume_slider.valueChanged.connect(self._set_volume)

        self._source_filter_check = QCheckBox(self._tr("source_filter"))
        self._source_filter_check.setProperty("i18n_key", "source_filter")
        self._source_filter_check.setChecked(self._config.original_audio_voice_filter)
        self._source_filter_check.setToolTip(self._tr("source_filter_tooltip"))
        self._source_filter_check.setProperty("i18n_tooltip_key", "source_filter_tooltip")
        self._source_filter_check.toggled.connect(self._source_voice_filter_changed)
        self._source_filter_mode_combo = QComboBox()
        self._source_filter_mode_combo.addItem(self._tr("source_filter_mode_auto"), "auto")
        self._source_filter_mode_combo.addItem(self._tr("source_filter_mode_fast"), "fast")
        self._source_filter_mode_combo.addItem(self._tr("source_filter_mode_ai"), "ai")
        self._source_filter_mode_combo.setCurrentIndex(
            max(0, self._source_filter_mode_combo.findData(self._config.original_audio_voice_filter_mode))
        )
        self._source_filter_mode_combo.setFixedWidth(118)
        self._source_filter_mode_combo.setToolTip(self._tr("source_filter_mode_tooltip"))
        self._source_filter_mode_combo.setProperty("i18n_tooltip_key", "source_filter_mode_tooltip")
        self._source_filter_mode_combo.currentIndexChanged.connect(self._source_voice_filter_mode_changed)

        self._dub_volume_slider = QSlider(Qt.Horizontal)
        self._dub_volume_slider.setRange(0, 100)
        self._dub_volume_slider.setValue(self._config.dubbing_voice_volume)
        self._dub_volume_slider.setFixedWidth(130)
        self._dub_volume_slider.valueChanged.connect(self._set_dub_volume_status)

        controls = QFrame()
        controls.setObjectName("controls")
        self._controls = controls
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(10, 8, 10, 8)
        controls_layout.setSpacing(8)
        timeline_layout = QHBoxLayout()
        timeline_layout.setSpacing(8)
        timeline_layout.addWidget(self._position_slider, 1)
        timeline_layout.addWidget(self._time_label)
        timeline_layout.addWidget(self._source_filter_check)
        timeline_layout.addWidget(self._source_filter_mode_combo)
        timeline_layout.addWidget(self._field_label("original_audio"))
        timeline_layout.addWidget(self._volume_slider)
        command_layout = QHBoxLayout()
        command_layout.setSpacing(8)
        command_layout.addWidget(self._play_button)
        command_layout.addWidget(self._pause_button)
        command_layout.addWidget(self._stop_button)
        command_layout.addWidget(self._previous_page_button)
        command_layout.addWidget(self._next_page_button)
        command_layout.addWidget(self._field_label("frame"))
        command_layout.addWidget(self._aspect_combo)
        command_layout.addWidget(self._playback_quality_combo)
        command_layout.addWidget(self._field_label("subtitle"))
        command_layout.addWidget(self._subtitle_mode_combo)
        command_layout.addWidget(self._subtitle_size_combo)
        command_layout.addWidget(self._subtitle_color_combo)
        command_layout.addStretch(1)
        command_layout.addWidget(self._field_label("dub_audio"))
        command_layout.addWidget(self._dub_volume_slider)
        controls_layout.addLayout(timeline_layout)
        controls_layout.addLayout(command_layout)

        video_panel = QFrame()
        video_panel.setObjectName("videoPanel")
        video_layout = QVBoxLayout(video_panel)
        video_layout.setContentsMargins(12, 12, 12, 12)
        video_layout.setSpacing(10)
        video_layout.addWidget(self._media_frame, 1, Qt.AlignCenter)
        video_layout.addWidget(controls)

        self._dub_button = self._make_button(
            "dub_button",
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume),
        )
        self._dub_button.setObjectName("dubButton")
        self._dub_button.setCheckable(True)
        self._dub_button.setChecked(self._dubbing_auto_enabled)
        self._dub_button.clicked.connect(self._toggle_dubbing)

        self._audio_source_combo = self._option_combo(
            _dropdown_options("audio_sources", self._config.gui_language),
            self._config.audio_source,
        )
        self._audio_source_combo.currentIndexChanged.connect(self._audio_source_changed)
        self._transcript_path_edit = QLineEdit(self._config.transcript_path)
        self._transcript_path_edit.setPlaceholderText(self._tr("transcript_file_placeholder"))
        self._transcript_path_edit.setClearButtonEnabled(True)
        self._transcript_path_edit.textEdited.connect(self._queue_save_settings)
        self._transcript_path_edit.textChanged.connect(self._invalidate_subtitle_entries)
        self._transcript_file_button = self._make_button(
            "choose",
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogStart),
        )
        self._transcript_file_button.clicked.connect(self._choose_transcript_file)

        self._source_language_combo = QComboBox()
        self._compact_combo(self._source_language_combo)
        for option in available_language_options(include_auto=True, language_id=self._config.gui_language):
            self._source_language_combo.addItem(_ui_label(option.name), option.id)
        self._source_language_combo.setCurrentIndex(
            max(0, self._source_language_combo.findData(self._config.source_language))
        )
        self._source_language_combo.currentIndexChanged.connect(self._language_pair_changed)
        self._target_language_combo = QComboBox()
        self._compact_combo(self._target_language_combo)
        for option in available_language_options(include_auto=False, language_id=self._config.gui_language):
            self._target_language_combo.addItem(_ui_label(option.name), option.id)
        self._target_language_combo.setCurrentIndex(
            max(0, self._target_language_combo.findData(self._config.target_language))
        )
        self._target_language_combo.currentIndexChanged.connect(self._language_pair_changed)

        self._translator_combo = QComboBox()
        self._compact_combo(self._translator_combo)
        for translator in available_translators():
            self._translator_combo.addItem(translator.name, translator.id)
        self._translator_combo.setCurrentIndex(
            max(0, self._translator_combo.findData(normalize_translator_provider(self._config.translator_provider)))
        )
        self._translator_combo.currentIndexChanged.connect(self._translator_changed)
        self._nllb_model_combo = QComboBox()
        self._compact_combo(self._nllb_model_combo)
        self._refresh_translation_models(self._config.local_translation_model)
        self._nllb_model_combo.currentIndexChanged.connect(self._nllb_model_changed)
        self._performance_preset_combo = self._option_combo(
            _dropdown_options("performance_presets", self._config.gui_language),
            self._config.performance_preset,
        )
        self._export_video_quality_combo = self._option_combo(
            _dropdown_options("video_qualities", self._config.gui_language),
            self._config.export_video_quality,
        )
        self._translation_device_combo = self._option_combo(
            _dropdown_options("translation_devices", self._config.gui_language),
            self._config.local_translation_device,
        )
        self._preserve_terms_check = QCheckBox(self._tr("keep_terms"))
        self._preserve_terms_check.setProperty("i18n_key", "keep_terms")
        self._preserve_terms_check.setChecked(self._config.preserve_english_terms)
        self._preserved_terms_edit = QLineEdit(self._config.preserved_english_terms)
        self._preserved_terms_edit.setPlaceholderText("AI, API, server, database, URL...")
        self._preserved_terms_edit.setToolTip(
            f"{self._tr('saved_at_prefix')} {self._config.preserved_english_terms_file}"
        )
        self._preserved_terms_edit.setClearButtonEnabled(True)
        self._preserved_terms_edit.setEnabled(self._preserve_terms_check.isChecked())
        self._preserve_terms_check.toggled.connect(self._preserved_terms_edit.setEnabled)
        self._preserved_terms_edit.editingFinished.connect(self._save_preserved_terms)
        self._whisper_offline_check = QCheckBox(self._tr("whisper_offline"))
        self._whisper_offline_check.setProperty("i18n_key", "whisper_offline")
        self._whisper_offline_check.setChecked(self._config.whisper_offline)
        self._translation_offline_check = QCheckBox(self._tr("translator_offline"))
        self._translation_offline_check.setProperty("i18n_key", "translator_offline")
        self._translation_offline_check.setChecked(self._config.local_translation_offline)
        self._vieneu_offline_check = QCheckBox(self._tr("vieneu_offline"))
        self._vieneu_offline_check.setProperty("i18n_key", "vieneu_offline")
        self._vieneu_offline_check.setChecked(self._config.vieneu_tts_offline)
        self._translation_max_tokens_slider, self._translation_max_tokens_value = self._labeled_slider(
            minimum=64,
            maximum=512,
            step=32,
            value=self._config.translation_max_tokens,
            formatter=lambda value: f"{value}",
        )
        self._translation_beams_slider, self._translation_beams_value = self._labeled_slider(
            minimum=1,
            maximum=6,
            step=1,
            value=self._config.translation_num_beams,
            formatter=lambda value: f"{value}",
        )

        self._tts_provider_combo = QComboBox()
        self._compact_combo(self._tts_provider_combo)
        for provider in available_tts_providers():
            self._tts_provider_combo.addItem(provider.name, provider.id)
        self._tts_provider_combo.setCurrentIndex(
            max(0, self._tts_provider_combo.findData(normalize_tts_provider(self._config.tts_provider)))
        )
        self._tts_provider_combo.currentIndexChanged.connect(self._refresh_tts_options)

        self._tts_mode_label = self._field_label("mode")
        self._vieneu_mode_combo = QComboBox()
        self._compact_combo(self._vieneu_mode_combo)
        for mode in available_vieneu_modes():
            self._vieneu_mode_combo.addItem(mode.name, mode.id)
        self._vieneu_mode_combo.setCurrentIndex(max(0, self._vieneu_mode_combo.findData(self._config.vieneu_tts_mode)))
        self._vieneu_mode_combo.currentIndexChanged.connect(self._refresh_vieneu_models)

        self._tts_model_label = self._field_label("model")
        self._vieneu_model_combo = QComboBox()
        self._compact_combo(self._vieneu_model_combo)
        self._vieneu_model_combo.currentIndexChanged.connect(self._refresh_tts_voices)

        self._tts_voice_combo = QComboBox()
        self._compact_combo(self._tts_voice_combo)
        self._tts_male_voice_combo = QComboBox()
        self._compact_combo(self._tts_male_voice_combo)
        self._tts_female_voice_combo = QComboBox()
        self._compact_combo(self._tts_female_voice_combo)
        self._auto_voice_gender_check = QCheckBox(self._tr("auto_gender"))
        self._auto_voice_gender_check.setProperty("i18n_key", "auto_gender")
        self._auto_voice_gender_check.setChecked(self._config.dubbing_auto_voice_gender)
        self._auto_voice_gender_check.toggled.connect(self._sync_auto_voice_controls_enabled)
        self._auto_voice_gender_mode_combo = QComboBox()
        self._auto_voice_gender_mode_combo.addItem(self._tr("voice_gender_mode_stable"), "stable")
        self._auto_voice_gender_mode_combo.addItem(self._tr("voice_gender_mode_balanced"), "balanced")
        self._auto_voice_gender_mode_combo.addItem(self._tr("voice_gender_mode_sensitive"), "sensitive")
        self._auto_voice_gender_mode_combo.addItem(self._tr("voice_gender_mode_ai"), "ai")
        self._auto_voice_gender_mode_combo.setCurrentIndex(
            max(0, self._auto_voice_gender_mode_combo.findData(self._config.dubbing_auto_voice_gender_mode))
        )
        self._auto_voice_gender_mode_combo.setToolTip(self._tr("voice_gender_mode_tooltip"))
        self._auto_voice_gender_mode_combo.setProperty("i18n_tooltip_key", "voice_gender_mode_tooltip")
        self._auto_match_audio_check = QCheckBox(self._tr("auto_match"))
        self._auto_match_audio_check.setProperty("i18n_key", "auto_match")
        self._auto_match_audio_check.setChecked(self._config.dubbing_auto_match_audio)
        self._dubbing_buffer_slider = self._value_slider(
            minimum=0,
            maximum=600,
            step=10,
            value=int(self._config.dubbing_min_ready_ahead_seconds),
        )
        self._dubbing_buffer_value = self._value_label(f"{int(self._config.dubbing_min_ready_ahead_seconds)} s")
        self._dubbing_buffer_slider.valueChanged.connect(lambda value: self._dubbing_buffer_value.setText(f"{value} s"))
        self._dub_speed_slider = self._value_slider(
            minimum=-100,
            maximum=100,
            step=10,
            value=self._config.dubbing_speed_percent,
        )
        self._dub_speed_value = self._value_label(f"{self._config.dubbing_speed_percent:+d} %")
        self._dub_speed_slider.valueChanged.connect(lambda value: self._dub_speed_value.setText(f"{value:+d} %"))
        self._video_delay_slider = self._value_slider(
            minimum=0,
            maximum=30,
            step=1,
            value=int(self._config.original_audio_playback_delay_seconds),
        )
        self._video_delay_value = self._value_label(f"{int(self._config.original_audio_playback_delay_seconds)} s")
        self._video_delay_slider.valueChanged.connect(lambda value: self._video_delay_value.setText(f"{value} s"))
        self._whisper_device_combo = self._option_combo(
            _dropdown_options("whisper_devices", self._config.gui_language),
            self._config.whisper_device,
        )
        self._whisper_compute_combo = self._option_combo(
            _dropdown_options("whisper_compute_types", self._config.gui_language),
            self._config.whisper_compute_type,
        )
        self._segment_seconds_slider, self._segment_seconds_value = self._labeled_slider(
            minimum=4,
            maximum=20,
            step=2,
            value=self._config.segment_seconds,
            formatter=lambda value: f"{value} s",
        )
        self._prebuffer_segments_slider, self._prebuffer_segments_value = self._labeled_slider(
            minimum=1,
            maximum=4,
            step=1,
            value=self._config.dubbing_prebuffer_segments,
            formatter=lambda value: f"{value}",
        )
        self._lookahead_segments_slider, self._lookahead_segments_value = self._labeled_slider(
            minimum=1,
            maximum=6,
            step=1,
            value=self._config.dubbing_lookahead_segments,
            formatter=lambda value: f"{value}",
        )
        self._start_delay_slider, self._start_delay_value = self._labeled_slider(
            minimum=0,
            maximum=5,
            step=1,
            value=int(self._config.dubbing_start_delay_seconds),
            formatter=lambda value: f"{value} s",
        )
        self._speed_min_slider, self._speed_min_value = self._labeled_slider(
            minimum=50,
            maximum=100,
            step=5,
            value=int(self._config.dubbing_speed_min * 100),
            formatter=lambda value: f"{value} %",
        )
        self._speed_max_slider, self._speed_max_value = self._labeled_slider(
            minimum=100,
            maximum=200,
            step=5,
            value=int(self._config.dubbing_speed_max * 100),
            formatter=lambda value: f"{value} %",
        )
        self._volume_gain_min_slider, self._volume_gain_min_value = self._labeled_slider(
            minimum=-20,
            maximum=0,
            step=1,
            value=int(self._config.dubbing_volume_gain_min_db),
            formatter=lambda value: f"{value} dB",
        )
        self._volume_gain_max_slider, self._volume_gain_max_value = self._labeled_slider(
            minimum=0,
            maximum=20,
            step=1,
            value=int(self._config.dubbing_volume_gain_max_db),
            formatter=lambda value: f"+{value} dB",
        )
        self._vieneu_runtime_combo = self._option_combo(
            _dropdown_options("vieneu_runtimes", self._config.gui_language),
            self._config.vieneu_tts_runtime,
        )
        self._vieneu_device_combo = self._option_combo(
            _dropdown_options("vieneu_devices", self._config.gui_language),
            self._config.vieneu_tts_device,
        )
        self._vieneu_backend_combo = self._option_combo(
            _dropdown_options("vieneu_backends", self._config.gui_language),
            self._config.vieneu_tts_backend,
        )
        capture_devices = list_capture_device_options()
        self._capture_backend_combo = self._option_combo(
            _dropdown_options("capture_backends", self._config.gui_language),
            self._config.capture_backend,
        )
        self._capture_system_device_combo = self._device_combo(
            capture_devices.get("system", []),
            self._config.capture_system_device,
        )
        self._capture_microphone_device_combo = self._device_combo(
            capture_devices.get("microphone", []),
            self._config.capture_microphone_device,
        )
        self._transcript_cleanup_mode_combo = self._option_combo(
            _dropdown_options("transcript_cleanup_modes", self._config.gui_language),
            self._config.transcript_cleanup_mode,
        )
        self._transcript_cleanup_provider_combo = self._option_combo(
            _dropdown_options("transcript_cleanup_providers", self._config.gui_language),
            self._config.transcript_cleanup_provider,
        )
        self._transcript_cleanup_model_combo = QComboBox()
        self._compact_combo(self._transcript_cleanup_model_combo)
        self._transcript_cleanup_model_combo.setEditable(True)
        for option in available_local_llm_options():
            self._transcript_cleanup_model_combo.addItem(option.name, option.id)
        current_cleanup_model = self._config.transcript_cleanup_model
        cleanup_model_index = self._transcript_cleanup_model_combo.findData(current_cleanup_model)
        if cleanup_model_index < 0 and current_cleanup_model:
            self._transcript_cleanup_model_combo.addItem(current_cleanup_model, current_cleanup_model)
            cleanup_model_index = self._transcript_cleanup_model_combo.findData(current_cleanup_model)
        self._transcript_cleanup_model_combo.setCurrentIndex(max(0, cleanup_model_index))
        self._transcript_cleanup_model_combo.setToolTip(self._tr("cleanup_model_tooltip"))
        self._transcript_cleanup_api_base_edit = QLineEdit(self._config.transcript_cleanup_api_base)
        self._transcript_cleanup_api_base_edit.setPlaceholderText(self._tr("cleanup_api_base_placeholder"))
        self._transcript_cleanup_api_key_edit = QLineEdit(self._config.transcript_cleanup_api_key)
        self._transcript_cleanup_api_key_edit.setPlaceholderText(self._tr("cleanup_api_key_placeholder"))
        self._transcript_cleanup_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._vieneu_temperature_slider, self._vieneu_temperature_value = self._labeled_slider(
            minimum=0,
            maximum=100,
            step=5,
            value=int(self._config.vieneu_tts_temperature * 100),
            formatter=lambda value: f"{value / 100:.2f}",
        )
        self._vieneu_max_chars_slider, self._vieneu_max_chars_value = self._labeled_slider(
            minimum=80,
            maximum=320,
            step=20,
            value=self._config.vieneu_tts_max_chars_chunk,
            formatter=lambda value: f"{value}",
        )

        preset_row = QWidget()
        preset_layout = QHBoxLayout(preset_row)
        preset_layout.setContentsMargins(0, 0, 0, 0)
        preset_layout.setSpacing(10)
        preset_layout.addWidget(self._field_label("preset"))
        preset_layout.addWidget(self._performance_preset_combo, 1)

        settings_grid = QGridLayout()
        settings_grid.setHorizontalSpacing(10)
        settings_grid.setVerticalSpacing(9)
        settings_grid.addWidget(self._field_label("source_language"), 0, 0)
        settings_grid.addWidget(self._source_language_combo, 0, 1)
        settings_grid.addWidget(self._field_label("target_language"), 1, 0)
        settings_grid.addWidget(self._target_language_combo, 1, 1)
        settings_grid.addWidget(self._field_label("translator"), 2, 0)
        settings_grid.addWidget(self._translator_combo, 2, 1)
        settings_grid.addWidget(self._field_label("translation_model"), 3, 0)
        settings_grid.addWidget(self._nllb_model_combo, 3, 1)
        settings_grid.addWidget(self._field_label("tts"), 4, 0)
        settings_grid.addWidget(self._tts_provider_combo, 4, 1)
        settings_grid.addWidget(self._tts_mode_label, 5, 0)
        settings_grid.addWidget(self._vieneu_mode_combo, 5, 1)
        settings_grid.addWidget(self._tts_model_label, 6, 0)
        settings_grid.addWidget(self._vieneu_model_combo, 6, 1)
        settings_grid.addWidget(self._field_label("voice_default"), 7, 0)
        settings_grid.addWidget(self._tts_voice_combo, 7, 1)
        settings_grid.addWidget(self._field_label("buffer"), 8, 0)
        settings_grid.addWidget(self._slider_row(self._dubbing_buffer_slider, self._dubbing_buffer_value), 8, 1)
        settings_grid.addWidget(self._field_label("speed"), 9, 0)
        settings_grid.addWidget(self._slider_row(self._dub_speed_slider, self._dub_speed_value), 9, 1)
        settings_grid.addWidget(self._field_label("video_delay"), 10, 0)
        settings_grid.addWidget(self._slider_row(self._video_delay_slider, self._video_delay_value), 10, 1)
        settings_grid.addWidget(self._field_label("export_video_quality"), 11, 0)
        settings_grid.addWidget(self._export_video_quality_combo, 11, 1)
        settings_grid.addWidget(self._video_url_full_cache_check, 12, 0, 1, 2)
        settings_grid.addWidget(self._auto_voice_gender_check, 13, 0, 1, 2)
        settings_grid.addWidget(self._field_label("voice_gender_mode"), 14, 0)
        settings_grid.addWidget(self._auto_voice_gender_mode_combo, 14, 1)
        settings_grid.addWidget(self._field_label("male_voice"), 15, 0)
        settings_grid.addWidget(self._tts_male_voice_combo, 15, 1)
        settings_grid.addWidget(self._field_label("female_voice"), 16, 0)
        settings_grid.addWidget(self._tts_female_voice_combo, 16, 1)
        settings_grid.addWidget(self._auto_match_audio_check, 17, 0, 1, 2)

        advanced_grid = QGridLayout()
        advanced_grid.setHorizontalSpacing(10)
        advanced_grid.setVerticalSpacing(9)
        advanced_grid.addWidget(self._field_label("whisper_device"), 0, 0)
        advanced_grid.addWidget(self._whisper_device_combo, 0, 1)
        advanced_grid.addWidget(self._field_label("whisper_compute"), 1, 0)
        advanced_grid.addWidget(self._whisper_compute_combo, 1, 1)
        advanced_grid.addWidget(self._field_label("translator_device"), 2, 0)
        advanced_grid.addWidget(self._translation_device_combo, 2, 1)
        advanced_grid.addWidget(self._preserve_terms_check, 3, 0, 1, 2)
        advanced_grid.addWidget(self._field_label("preserved_terms"), 4, 0)
        advanced_grid.addWidget(self._preserved_terms_edit, 4, 1)
        advanced_grid.addWidget(self._whisper_offline_check, 5, 0, 1, 2)
        advanced_grid.addWidget(self._translation_offline_check, 6, 0, 1, 2)
        advanced_grid.addWidget(self._vieneu_offline_check, 7, 0, 1, 2)
        advanced_grid.addWidget(self._field_label("translation_max_tokens"), 8, 0)
        advanced_grid.addWidget(
            self._slider_row(self._translation_max_tokens_slider, self._translation_max_tokens_value), 8, 1
        )
        advanced_grid.addWidget(self._field_label("translation_beams"), 9, 0)
        advanced_grid.addWidget(self._slider_row(self._translation_beams_slider, self._translation_beams_value), 9, 1)
        advanced_grid.addWidget(self._field_label("segment_length"), 10, 0)
        advanced_grid.addWidget(self._slider_row(self._segment_seconds_slider, self._segment_seconds_value), 10, 1)
        advanced_grid.addWidget(self._field_label("prebuffer_segments"), 11, 0)
        advanced_grid.addWidget(
            self._slider_row(self._prebuffer_segments_slider, self._prebuffer_segments_value), 11, 1
        )
        advanced_grid.addWidget(self._field_label("lookahead_segments"), 12, 0)
        advanced_grid.addWidget(
            self._slider_row(self._lookahead_segments_slider, self._lookahead_segments_value), 12, 1
        )
        advanced_grid.addWidget(self._field_label("start_delay"), 13, 0)
        advanced_grid.addWidget(self._slider_row(self._start_delay_slider, self._start_delay_value), 13, 1)
        advanced_grid.addWidget(self._field_label("speed_min"), 14, 0)
        advanced_grid.addWidget(self._slider_row(self._speed_min_slider, self._speed_min_value), 14, 1)
        advanced_grid.addWidget(self._field_label("speed_max"), 15, 0)
        advanced_grid.addWidget(self._slider_row(self._speed_max_slider, self._speed_max_value), 15, 1)
        advanced_grid.addWidget(self._field_label("gain_min"), 16, 0)
        advanced_grid.addWidget(self._slider_row(self._volume_gain_min_slider, self._volume_gain_min_value), 16, 1)
        advanced_grid.addWidget(self._field_label("gain_max"), 17, 0)
        advanced_grid.addWidget(self._slider_row(self._volume_gain_max_slider, self._volume_gain_max_value), 17, 1)
        advanced_grid.addWidget(self._field_label("vieneu_runtime"), 18, 0)
        advanced_grid.addWidget(self._vieneu_runtime_combo, 18, 1)
        advanced_grid.addWidget(self._field_label("vieneu_device"), 19, 0)
        advanced_grid.addWidget(self._vieneu_device_combo, 19, 1)
        advanced_grid.addWidget(self._field_label("vieneu_backend"), 20, 0)
        advanced_grid.addWidget(self._vieneu_backend_combo, 20, 1)
        advanced_grid.addWidget(self._field_label("vieneu_temperature"), 21, 0)
        advanced_grid.addWidget(
            self._slider_row(self._vieneu_temperature_slider, self._vieneu_temperature_value), 21, 1
        )
        advanced_grid.addWidget(self._field_label("tts_max_chars"), 22, 0)
        advanced_grid.addWidget(self._slider_row(self._vieneu_max_chars_slider, self._vieneu_max_chars_value), 22, 1)

        advanced_grid.addWidget(self._field_label("capture_backend"), 23, 0)
        advanced_grid.addWidget(self._capture_backend_combo, 23, 1)
        advanced_grid.addWidget(self._field_label("system_audio"), 24, 0)
        advanced_grid.addWidget(self._capture_system_device_combo, 24, 1)
        advanced_grid.addWidget(self._field_label("microphone"), 25, 0)
        advanced_grid.addWidget(self._capture_microphone_device_combo, 25, 1)
        advanced_grid.addWidget(self._field_label("transcript_cleanup"), 26, 0)
        advanced_grid.addWidget(self._transcript_cleanup_mode_combo, 26, 1)
        advanced_grid.addWidget(self._field_label("cleanup_provider"), 27, 0)
        advanced_grid.addWidget(self._transcript_cleanup_provider_combo, 27, 1)
        advanced_grid.addWidget(self._field_label("cleanup_model"), 28, 0)
        advanced_grid.addWidget(self._transcript_cleanup_model_combo, 28, 1)
        advanced_grid.addWidget(self._field_label("cleanup_api_base"), 29, 0)
        advanced_grid.addWidget(self._transcript_cleanup_api_base_edit, 29, 1)
        advanced_grid.addWidget(self._field_label("cleanup_api_key"), 30, 0)
        advanced_grid.addWidget(self._transcript_cleanup_api_key_edit, 30, 1)

        self._transcript = QTextEdit()
        self._transcript.setObjectName("transcript")
        self._transcript.setReadOnly(True)
        self._transcript_view_combo = self._option_combo(
            _dropdown_options("transcript_views", self._config.gui_language), "all"
        )
        self._transcript_view_combo.setAccessibleName(self._tr("show_transcript"))
        self._transcript_view_combo.setToolTip(self._tr("show_transcript"))
        self._transcript_view_combo.currentIndexChanged.connect(self._render_transcript)
        self._transcript_type_combo = self._option_combo(
            _dropdown_options("transcript_types", self._config.gui_language), "all"
        )
        self._transcript_type_combo.setAccessibleName(self._tr("transcript_type"))
        self._transcript_type_combo.setToolTip(self._tr("transcript_type"))
        self._transcript_type_combo.currentIndexChanged.connect(self._render_transcript)
        self._export_transcript_button = self._make_button(
            "export_transcript",
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton),
        )
        self._export_transcript_button.clicked.connect(self._export_transcript)
        self._transcript.setPlaceholderText(self._tr("transcript_placeholder"))

        settings_panel = QFrame()
        settings_panel.setObjectName("sidePanel")
        settings_panel.setMinimumWidth(300)
        settings_layout = QVBoxLayout(settings_panel)
        settings_layout.setContentsMargins(12, 12, 12, 12)
        settings_layout.setSpacing(10)

        basic_tab = QWidget()
        basic_layout = QVBoxLayout(basic_tab)
        basic_layout.setContentsMargins(8, 8, 8, 8)
        basic_layout.setSpacing(12)
        basic_layout.addWidget(self._dub_button)
        basic_layout.addWidget(preset_row)
        basic_layout.addWidget(self._audio_source_panel())
        basic_layout.addLayout(settings_grid)
        basic_layout.addStretch(1)

        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)
        advanced_layout.setContentsMargins(8, 8, 8, 8)
        advanced_layout.setSpacing(10)
        advanced_layout.addLayout(advanced_grid)
        advanced_layout.addStretch(1)

        transcript_tab = QWidget()
        transcript_layout = QVBoxLayout(transcript_tab)
        transcript_layout.setContentsMargins(8, 8, 8, 8)
        transcript_layout.setSpacing(8)
        transcript_toolbar = QWidget()
        transcript_toolbar_layout = QHBoxLayout(transcript_toolbar)
        transcript_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        transcript_toolbar_layout.setSpacing(8)
        transcript_toolbar_layout.addWidget(self._transcript_view_combo, 1)
        transcript_toolbar_layout.addWidget(self._transcript_type_combo, 1)
        transcript_toolbar_layout.addWidget(self._export_transcript_button)
        transcript_layout.addWidget(transcript_toolbar)
        transcript_layout.addWidget(self._transcript, 1)

        runtime_tab = self._runtime_tab()

        self._settings_tabs = QTabWidget()
        self._settings_tabs.setObjectName("settingsTabs")
        self._settings_tabs.addTab(basic_tab, self._tr("basic_tab"))
        self._settings_tabs.addTab(advanced_tab, self._tr("advanced_tab"))
        self._settings_tabs.addTab(transcript_tab, self._tr("transcript_tab"))
        self._settings_tabs.addTab(runtime_tab, self._tr("runtime_tab"))
        self._settings_tabs.currentChanged.connect(self._runtime_tab_changed)
        settings_layout.addWidget(self._settings_tabs, 1)
        self._refresh_tts_options()
        self._sync_auto_voice_controls_enabled()
        self._performance_preset_combo.currentIndexChanged.connect(self._apply_selected_performance_preset)
        self._connect_settings_autosave()

        self._settings_scroll = QScrollArea()
        self._settings_scroll.setObjectName("sideScroll")
        self._settings_scroll.setWidgetResizable(True)
        self._settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._settings_scroll.setMinimumWidth(320)
        self._settings_scroll.setWidget(settings_panel)

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.addWidget(video_panel)
        self._splitter.addWidget(self._settings_scroll)
        self._splitter.setStretchFactor(0, 5)
        self._splitter.setStretchFactor(1, 2)
        self._splitter.setSizes([900, 460])

        root = QVBoxLayout()
        root.setContentsMargins(16, 14, 16, 10)
        root.setSpacing(12)
        root.addWidget(source_bar)
        root.addWidget(self._splitter, 1)

        container = QWidget()
        container.setObjectName("root")
        container.setLayout(root)
        self.setCentralWidget(container)
        self.setStatusBar(QStatusBar(self))
