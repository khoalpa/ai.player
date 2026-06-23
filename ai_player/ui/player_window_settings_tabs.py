from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ai_player.ui.player_window_media import DEFAULT_SIDEBAR_PANEL_WIDTH


def scrollable_settings_tab(content: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName("sideScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setWidget(content)
    return scroll


def build_basic_settings_tab(
    owner: Any,
    *,
    basic_source_grid,
    basic_voice_grid,
    basic_playback_grid,
    basic_processing_grid,
) -> QWidget:
    tab = _settings_tab()
    layout = QVBoxLayout(tab)
    _setup_settings_tab_layout(layout)
    layout.addWidget(owner._dub_button)
    layout.addWidget(owner._section_title("basic_source_group"))
    layout.addLayout(basic_source_grid)
    layout.addWidget(owner._section_title("basic_voice_group"))
    layout.addLayout(basic_voice_grid)
    layout.addWidget(owner._section_title("basic_playback_group"))
    layout.addLayout(basic_playback_grid)
    layout.addWidget(owner._section_title("basic_processing_group"))
    layout.addLayout(basic_processing_grid)
    layout.addStretch(1)
    return tab


def build_models_settings_tab(
    owner: Any,
    *,
    asr_grid,
    translation_grid,
    tts_grid,
    tts_advanced_grid,
    voice_ai_grid,
    ocr_grid,
    cleanup_grid,
) -> QWidget:
    tab = _settings_tab()
    layout = QVBoxLayout(tab)
    _setup_settings_tab_layout(layout)
    for title_key, section in (
        ("asr_group", asr_grid),
        ("translation_group", translation_grid),
        ("tts_group", tts_grid),
        ("tts_advanced_group", tts_advanced_grid),
        ("voice_ai_group", voice_ai_grid),
        ("ocr_group", ocr_grid),
        ("cleanup_group", cleanup_grid),
    ):
        layout.addWidget(owner._section_title(title_key))
        layout.addLayout(section)
    layout.addWidget(owner._section_title("provider_preview_group"))
    layout.addWidget(owner._provider_preview_status)
    layout.addStretch(1)
    return tab


def build_advanced_settings_tab(
    owner: Any,
    *,
    advanced_terms_grid,
    advanced_timing_grid,
    advanced_match_grid,
    advanced_playback_grid,
    advanced_capture_grid,
) -> QWidget:
    tab = _settings_tab()
    layout = QVBoxLayout(tab)
    _setup_settings_tab_layout(layout)
    for title_key, section in (
        ("advanced_terms_group", advanced_terms_grid),
        ("advanced_timing_group", advanced_timing_grid),
        ("advanced_audio_match_group", advanced_match_grid),
        ("advanced_playback_group", advanced_playback_grid),
        ("advanced_capture_group", advanced_capture_grid),
    ):
        layout.addWidget(owner._section_title(title_key))
        layout.addLayout(section)
    layout.addStretch(1)
    return tab


def build_transcript_settings_tab(owner: Any) -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(7, 7, 7, 7)
    layout.setSpacing(7)
    toolbar = QWidget()
    toolbar_layout = QHBoxLayout(toolbar)
    toolbar_layout.setContentsMargins(0, 0, 0, 0)
    toolbar_layout.setSpacing(6)
    toolbar_layout.addWidget(owner._transcript_view_combo, 1)
    toolbar_layout.addWidget(owner._transcript_type_combo, 1)
    toolbar_layout.addWidget(owner._export_transcript_button)
    layout.addWidget(toolbar)
    layout.addWidget(owner._transcript, 1)
    return tab


def build_settings_panel(owner: Any, tabs: QTabWidget) -> QFrame:
    panel = QFrame()
    panel.setObjectName("sidePanel")
    panel.setMinimumWidth(DEFAULT_SIDEBAR_PANEL_WIDTH)
    panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(10)
    layout.addWidget(_settings_nav(owner, tabs))
    layout.addWidget(tabs, 1)
    return panel


def build_settings_tabs(
    owner: Any,
    *,
    readiness_tab: QWidget,
    task_center_tab: QWidget,
    basic_tab: QWidget,
    models_tab: QWidget,
    offline_models_tab: QWidget,
    advanced_tab: QWidget,
    transcript_tab: QWidget,
    runtime_tab: QWidget,
) -> QTabWidget:
    tabs = QTabWidget()
    tabs.setObjectName("settingsTabs")
    owner._readiness_tab_widget = readiness_tab
    owner._task_center_tab_widget = task_center_tab
    owner._basic_tab_widget = basic_tab
    owner._models_tab_widget = models_tab
    owner._offline_models_tab_widget = offline_models_tab
    owner._advanced_tab_widget = advanced_tab
    owner._transcript_tab_widget = transcript_tab
    owner._runtime_tab_widget = runtime_tab
    tabs.addTab(scrollable_settings_tab(readiness_tab), owner._tr("first_run_tab"))
    tabs.addTab(scrollable_settings_tab(task_center_tab), owner._tr("task_center_tab"))
    tabs.addTab(scrollable_settings_tab(basic_tab), owner._tr("basic_tab"))
    tabs.addTab(scrollable_settings_tab(models_tab), owner._tr("models_tab"))
    tabs.addTab(scrollable_settings_tab(offline_models_tab), owner._tr("offline_models_tab"))
    tabs.addTab(scrollable_settings_tab(advanced_tab), owner._tr("advanced_tab"))
    tabs.addTab(transcript_tab, owner._tr("transcript_tab"))
    tabs.addTab(scrollable_settings_tab(runtime_tab), owner._tr("runtime_tab"))
    tabs.currentChanged.connect(owner._runtime_tab_changed)
    tabs.currentChanged.connect(owner._offline_models_tab_changed)
    tabs.currentChanged.connect(owner._task_center_tab_changed)
    return tabs


def _settings_nav(owner: Any, tabs: QTabWidget) -> QFrame:
    nav = QFrame()
    nav.setObjectName("settingsNav")
    layout = QHBoxLayout(nav)
    layout.setContentsMargins(4, 4, 4, 4)
    layout.setSpacing(4)
    group = QButtonGroup(nav)
    group.setExclusive(True)
    owner._settings_group_buttons = {}
    for key, tab_index in (
        ("settings_group_start", 0),
        ("settings_group_workflow", 2),
        ("settings_group_transcript", 6),
        ("settings_group_models", 3),
        ("settings_group_system", 1),
    ):
        button = QPushButton(owner._tr(key))
        button.setObjectName("settingsNavButton")
        button.setProperty("i18n_key", key)
        button.setCheckable(True)
        button.setMinimumWidth(0)
        button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        button.clicked.connect(lambda _checked=False, index=tab_index: tabs.setCurrentIndex(index))
        group.addButton(button)
        owner._settings_group_buttons[key] = button
        layout.addWidget(button)
    owner._settings_group_buttons["settings_group_start"].setChecked(True)
    tabs.currentChanged.connect(lambda index: _sync_settings_nav(owner, index))
    return nav


def _sync_settings_nav(owner: Any, index: int) -> None:
    buttons = getattr(owner, "_settings_group_buttons", {})
    if not buttons:
        return
    key = "settings_group_system"
    if index == 0:
        key = "settings_group_start"
    elif index in {2, 5}:
        key = "settings_group_workflow"
    elif index == 6:
        key = "settings_group_transcript"
    elif index in {3, 4}:
        key = "settings_group_models"
    button = buttons.get(key)
    if button is not None:
        button.setChecked(True)


def _settings_tab() -> QWidget:
    return QWidget()


def _setup_settings_tab_layout(layout: QVBoxLayout) -> None:
    layout.setContentsMargins(7, 7, 7, 7)
    layout.setSpacing(10)
