from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTabWidget,
    QTextEdit,
    QToolButton,
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
    owner._dub_button.setVisible(False)
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
    layout.addWidget(_model_status_strip(owner))
    for title_key, section in (
        ("asr_group", asr_grid),
        ("translation_group", translation_grid),
        ("tts_group", tts_grid),
        ("tts_advanced_group", tts_advanced_grid),
        ("voice_ai_group", voice_ai_grid),
        ("ocr_group", ocr_grid),
        ("cleanup_group", cleanup_grid),
    ):
        layout.addWidget(_settings_section_card(owner, title_key, section))
    layout.addStretch(1)
    return tab


def _model_status_strip(owner: Any) -> QFrame:
    strip = QFrame()
    strip.setObjectName("modelStatusStrip")
    layout = QHBoxLayout(strip)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.setSpacing(6)
    owner._model_status_labels = {}
    for key in (
        "model_status_asr",
        "model_status_translation",
        "model_status_tts",
        "model_status_ocr",
        "model_status_cleanup",
    ):
        label = QLabel(owner._tr(key))
        label.setObjectName("modelStatusPill")
        label.setProperty("i18n_key", key)
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        owner._model_status_labels[key] = label
        layout.addWidget(label)
    return strip


def _settings_section_card(owner: Any, title_key: str, section) -> QFrame:
    card = QFrame()
    card.setObjectName("settingsSectionCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 9, 10, 10)
    layout.setSpacing(8)
    header = QWidget()
    header_layout = QHBoxLayout(header)
    header_layout.setContentsMargins(0, 0, 0, 0)
    header_layout.setSpacing(6)
    toggle = QToolButton()
    toggle.setObjectName("settingsSectionToggle")
    toggle.setCheckable(True)
    toggle.setChecked(False)
    toggle.setArrowType(Qt.ArrowType.RightArrow)
    toggle.setAutoRaise(True)
    title = owner._section_title(title_key)
    header_layout.addWidget(toggle)
    header_layout.addWidget(title, 1)
    layout.addWidget(header)
    content = QWidget()
    content_layout = QVBoxLayout(content)
    content_layout.setContentsMargins(0, 0, 0, 0)
    content_layout.addLayout(section)
    content.setVisible(False)
    layout.addWidget(content)

    def sync_collapsed(checked: bool) -> None:
        content.setVisible(checked)
        toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    toggle.toggled.connect(sync_collapsed)
    title.mousePressEvent = lambda event: toggle.toggle()
    return card


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
    owner._transcript_segment_banner = QLabel(owner._tr("transcript_segment_empty"))
    owner._transcript_segment_banner.setObjectName("inlineBanner")
    owner._transcript_segment_banner.setWordWrap(True)
    owner._transcript_segment_banner.setVisible(False)
    layout.addWidget(owner._transcript_segment_banner)
    owner._transcript_status_labels = {}
    owner._transcript_status_strip = QFrame()
    owner._transcript_status_strip.setObjectName("transcriptStatusStrip")
    status_layout = QGridLayout(owner._transcript_status_strip)
    status_layout.setContentsMargins(6, 6, 6, 6)
    status_layout.setHorizontalSpacing(6)
    status_layout.setVerticalSpacing(6)
    for index, key in enumerate(
        (
            "transcript_status_total",
            "transcript_status_translated",
            "transcript_status_retry",
            "transcript_status_state_empty",
        )
    ):
        label = QLabel(owner._tr(key).format(count=0))
        label.setObjectName("transcriptStatusPill")
        label.setProperty("i18n_key", key)
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        owner._transcript_status_labels[key] = label
        status_layout.addWidget(label, index // 2, index % 2)
    layout.addWidget(owner._transcript_status_strip)
    owner._transcript_empty_panel = _next_action_panel(
        owner,
        object_name="transcriptEmptyPanel",
        show_primary=False,
    )
    layout.addWidget(owner._transcript_empty_panel)
    owner._transcript_segment_table = QTableWidget(0, 3)
    owner._transcript_segment_table.setObjectName("transcriptSegmentTable")
    owner._transcript_segment_table.setHorizontalHeaderLabels(
        [
            owner._tr("transcript_segment_index"),
            owner._tr("transcript_segment_content"),
            owner._tr("transcript_segment_status"),
        ]
    )
    owner._transcript_segment_table.verticalHeader().setVisible(False)
    owner._transcript_segment_table.setWordWrap(True)
    owner._transcript_segment_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    owner._transcript_segment_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    owner._transcript_segment_table.setMinimumHeight(130)
    owner._transcript_segment_table.setMaximumHeight(230)
    owner._transcript_segment_table.setVisible(False)
    owner._transcript_segment_table.setColumnWidth(0, 42)
    owner._transcript_segment_table.setColumnWidth(2, 96)
    segment_header = owner._transcript_segment_table.horizontalHeader()
    segment_header.setStretchLastSection(False)
    segment_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    segment_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    segment_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    owner._transcript_segment_table.itemSelectionChanged.connect(owner._transcript_segment_selection_changed)
    layout.addWidget(owner._transcript_segment_table)

    editor = QFrame()
    editor.setObjectName("transcriptSegmentEditor")
    owner._transcript_segment_editor = editor
    editor.setVisible(False)
    editor.setMinimumHeight(210)
    editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
    editor_layout = QVBoxLayout(editor)
    editor_layout.setContentsMargins(8, 8, 8, 8)
    editor_layout.setSpacing(6)
    editor_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
    owner._transcript_segment_editor_title = QLabel(owner._tr("transcript_segment_editor_group"))
    owner._transcript_segment_editor_title.setProperty("i18n_key", "transcript_segment_editor_group")
    owner._transcript_segment_editor_title.setObjectName("settingsSectionTitle")
    editor_layout.addWidget(owner._transcript_segment_editor_title)
    owner._transcript_segment_source_label = QLabel(owner._tr("transcript_segment_source_detail"))
    owner._transcript_segment_source_label.setProperty("i18n_key", "transcript_segment_source_detail")
    editor_layout.addWidget(owner._transcript_segment_source_label)
    owner._transcript_segment_source_detail = QTextEdit()
    owner._transcript_segment_source_detail.setObjectName("transcriptSegmentSource")
    owner._transcript_segment_source_detail.setReadOnly(True)
    owner._transcript_segment_source_detail.setMinimumHeight(30)
    owner._transcript_segment_source_detail.setMaximumHeight(44)
    editor_layout.addWidget(owner._transcript_segment_source_detail)
    owner._transcript_segment_target_label = QLabel(owner._tr("transcript_segment_target_edit"))
    owner._transcript_segment_target_label.setProperty("i18n_key", "transcript_segment_target_edit")
    editor_layout.addWidget(owner._transcript_segment_target_label)
    owner._transcript_segment_target_edit = QTextEdit()
    owner._transcript_segment_target_edit.setObjectName("transcriptSegmentTarget")
    owner._transcript_segment_target_edit.setMinimumHeight(34)
    owner._transcript_segment_target_edit.setMaximumHeight(48)
    editor_layout.addWidget(owner._transcript_segment_target_edit)
    editor_actions = QWidget()
    editor_actions.setMinimumHeight(70)
    editor_actions_layout = QGridLayout(editor_actions)
    editor_actions_layout.setContentsMargins(0, 0, 0, 0)
    editor_actions_layout.setHorizontalSpacing(6)
    editor_actions_layout.setVerticalSpacing(6)
    editor_actions_layout.setColumnStretch(0, 1)
    editor_actions_layout.setColumnStretch(1, 1)
    owner._transcript_segment_apply_button = QPushButton(owner._tr("transcript_segment_apply"))
    owner._transcript_segment_apply_button.setProperty("i18n_key", "transcript_segment_apply")
    owner._transcript_segment_apply_button.clicked.connect(owner._apply_transcript_segment_target)
    owner._transcript_segment_review_button = QPushButton(owner._tr("transcript_segment_mark_reviewed"))
    owner._transcript_segment_review_button.setProperty("i18n_key", "transcript_segment_mark_reviewed")
    owner._transcript_segment_review_button.clicked.connect(owner._mark_transcript_segment_reviewed)
    owner._transcript_segment_retry_button = QPushButton(owner._tr("transcript_segment_retry"))
    owner._transcript_segment_retry_button.setProperty("i18n_key", "transcript_segment_retry")
    owner._transcript_segment_retry_button.clicked.connect(owner._retry_transcript_segment)
    segment_action_buttons = (
        owner._transcript_segment_apply_button,
        owner._transcript_segment_review_button,
        owner._transcript_segment_retry_button,
    )
    for button in segment_action_buttons:
        button.setObjectName("transcriptSegmentButton")
        button.setMinimumHeight(32)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    editor_actions_layout.addWidget(owner._transcript_segment_apply_button, 0, 0)
    editor_actions_layout.addWidget(owner._transcript_segment_review_button, 0, 1)
    editor_actions_layout.addWidget(owner._transcript_segment_retry_button, 1, 0, 1, 2)
    editor_layout.addWidget(editor_actions)
    layout.addWidget(editor)
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
    owner._next_action_panel = _next_action_panel(owner)
    layout.addWidget(owner._next_action_panel)
    layout.addWidget(_settings_nav(owner, tabs))
    layout.addWidget(tabs, 1)
    return panel


def _next_action_panel(owner: Any, *, object_name: str = "nextActionPanel", show_primary: bool = True) -> QFrame:
    panel = QFrame()
    panel.setObjectName(object_name)
    panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(10, 9, 10, 10)
    layout.setSpacing(7)

    title = QLabel(owner._tr("next_action_title"))
    title.setObjectName("nextActionTitle")
    title.setProperty("i18n_key", "next_action_title")
    title.setWordWrap(True)
    layout.addWidget(title)

    detail = QLabel(owner._tr("next_action_no_source_detail"))
    detail.setObjectName("nextActionDetail")
    detail.setWordWrap(True)
    layout.addWidget(detail)

    buttons = []
    if show_primary:
        primary = QPushButton("")
        primary.setObjectName("nextActionPrimaryButton")
        primary.setCursor(Qt.CursorShape.PointingHandCursor)
        primary.setMinimumHeight(34)
        primary.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        primary.clicked.connect(lambda _checked=False, target=object_name: owner._run_next_action(0, panel_name=target))
        layout.addWidget(primary)
        buttons.append(primary)

    panel._next_action_title = title
    panel._next_action_detail = detail
    panel._next_action_buttons = buttons
    panel._next_action_keys = [""]
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
    tabs.addTab(scrollable_settings_tab(transcript_tab), owner._tr("transcript_tab"))
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
        button.clicked.connect(
            lambda _checked=False, group_key=key, index=tab_index: _activate_settings_group(
                owner,
                tabs,
                group_key,
                index,
            )
        )
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


def _activate_settings_group(owner: Any, tabs: QTabWidget, group_key: str, index: int) -> None:
    if getattr(owner, "_simple_sidebar_enabled", False):
        visible_indexes = {
            "settings_group_start": {0},
            "settings_group_workflow": {2},
            "settings_group_transcript": {6},
            "settings_group_models": {3},
            "settings_group_system": {1},
        }.get(group_key, {1, 2, 3, 6})
    else:
        visible_indexes = {
            "settings_group_start": {0},
            "settings_group_workflow": {2, 5},
            "settings_group_transcript": {6},
            "settings_group_models": {3, 4},
            "settings_group_system": {1, 7},
        }.get(group_key, set(range(tabs.count())))
    apply_visibility = getattr(owner, "_set_sidebar_tab_visibility", None)
    if callable(apply_visibility):
        apply_visibility(visible_indexes)
    else:
        set_visible = getattr(tabs, "setTabVisible", None)
        if callable(set_visible):
            for row in range(tabs.count()):
                set_visible(row, row in visible_indexes)
    tabs.setCurrentIndex(index)


def _settings_tab() -> QWidget:
    return QWidget()


def _setup_settings_tab_layout(layout: QVBoxLayout) -> None:
    layout.setContentsMargins(7, 7, 7, 7)
    layout.setSpacing(10)
