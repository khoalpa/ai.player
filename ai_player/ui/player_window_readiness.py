from __future__ import annotations

from dataclasses import fields, replace
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from ai_player.core.config import MODEL_ROOT, AppConfig
from ai_player.core.runtime_health import build_runtime_health, format_runtime_health
from ai_player.ui.player_window_utils import PERFORMANCE_PRESETS

READINESS_PROFILES = (
    {
        "key": "quick",
        "preset": "low_latency",
        "title": "first_run_profile_quick",
        "detail": "first_run_profile_quick_detail",
    },
    {
        "key": "offline",
        "preset": "offline_lite",
        "title": "first_run_profile_offline",
        "detail": "first_run_profile_offline_detail",
    },
    {
        "key": "quality",
        "preset": "quality",
        "title": "first_run_profile_quality",
        "detail": "first_run_profile_quality_detail",
    },
    {
        "key": "meeting_document",
        "preset": "balanced",
        "title": "first_run_profile_meeting_document",
        "detail": "first_run_profile_meeting_document_detail",
        "overrides": {"audio_source": "document_editor"},
    },
)


class PlayerReadinessMixin:
    def _readiness_tab(self) -> QWidget:
        tab = QWidget()
        self._readiness_tab_widget = tab
        self._readiness_selected_profile = "quick"
        self._readiness_profile_buttons: dict[str, QPushButton] = {}

        layout = QVBoxLayout(tab)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(10)

        summary = QLabel(self._tr("first_run_summary"))
        summary.setProperty("i18n_key", "first_run_summary")
        summary.setWordWrap(True)
        summary.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(summary)

        layout.addWidget(self._section_title("first_run_workflow_group"))
        workflow_grid = QGridLayout()
        workflow_grid.setHorizontalSpacing(8)
        workflow_grid.setVerticalSpacing(8)
        workflow_grid.setColumnStretch(0, 1)
        workflow_grid.setColumnStretch(1, 1)
        workflow_specs = (
            (
                "video",
                "first_run_workflow_video",
                "first_run_workflow_video_detail",
                QStyle.StandardPixmap.SP_DirOpenIcon,
                self._open_video,
            ),
            (
                "url",
                "first_run_workflow_url",
                "first_run_workflow_url_detail",
                QStyle.StandardPixmap.SP_BrowserReload,
                self._open_video_url,
            ),
            (
                "document",
                "first_run_workflow_document",
                "first_run_workflow_document_detail",
                QStyle.StandardPixmap.SP_FileIcon,
                self._open_document,
            ),
            (
                "meeting",
                "first_run_workflow_meeting",
                "first_run_workflow_meeting_detail",
                QStyle.StandardPixmap.SP_MediaPlay,
                self._toggle_meeting,
            ),
        )
        self._readiness_workflow_buttons: dict[str, QPushButton] = {}
        for index, (workflow_key, title_key, detail_key, icon, callback) in enumerate(workflow_specs):
            button = self._make_button(title_key, self.style().standardIcon(icon))
            button.setObjectName("workflowCardButton")
            button.setText(f"{self._tr(title_key)}\n{self._tr(detail_key)}")
            button.setProperty("i18n_key", "")
            button.setProperty("workflow_title_key", title_key)
            button.setProperty("workflow_detail_key", detail_key)
            button.setMinimumHeight(64)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, key=workflow_key, cb=callback: self._start_workflow(key, cb))
            self._fit_readiness_button(button)
            workflow_grid.addWidget(button, index // 2, index % 2)
            self._readiness_workflow_buttons[title_key] = button
        layout.addLayout(workflow_grid)

        layout.addWidget(self._section_title("first_run_profile_group"))
        profile_grid = QGridLayout()
        profile_grid.setHorizontalSpacing(8)
        profile_grid.setVerticalSpacing(8)
        profile_grid.setColumnStretch(0, 1)
        profile_grid.setColumnStretch(1, 1)
        self._readiness_profile_group = QButtonGroup(tab)
        self._readiness_profile_group.setExclusive(True)
        for index, profile in enumerate(READINESS_PROFILES):
            button = QPushButton(self._readiness_profile_button_text(profile))
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(56)
            self._fit_readiness_button(button)
            button.setProperty("readiness_profile", profile["key"])
            button.clicked.connect(
                lambda _checked=False, profile_key=str(profile["key"]): self._readiness_select_profile(profile_key)
            )
            self._readiness_profile_group.addButton(button)
            self._readiness_profile_buttons[str(profile["key"])] = button
            profile_grid.addWidget(button, index // 2, index % 2)
        self._readiness_profile_buttons["quick"].setChecked(True)
        layout.addLayout(profile_grid)

        self._readiness_recommendation = QLabel("")
        self._readiness_recommendation.setWordWrap(True)
        self._readiness_recommendation.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._readiness_recommendation.setObjectName("apiKeyStatusLabel")
        layout.addWidget(self._readiness_recommendation)

        self._readiness_apply_button = self._make_button(
            "first_run_apply_profile",
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton),
        )
        self._readiness_apply_button.clicked.connect(self._apply_readiness_profile)
        self._readiness_check_button = self._make_button(
            "first_run_check",
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
        )
        self._readiness_check_button.clicked.connect(self._refresh_readiness_status)
        layout.addWidget(
            self._readiness_button_grid(
                (self._readiness_apply_button, self._readiness_check_button),
                columns=2,
            )
        )

        self._readiness_download_button = self._make_button(
            "first_run_download_missing",
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward),
        )
        self._readiness_download_button.clicked.connect(self._readiness_download_missing)
        self._readiness_preview_missing_button = self._make_button(
            "first_run_preview_missing",
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView),
        )
        self._readiness_preview_missing_button.clicked.connect(self._readiness_preview_missing)
        self._readiness_model_folder_button = self._make_button(
            "first_run_open_model_folder",
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
        )
        self._readiness_model_folder_button.clicked.connect(self._readiness_open_model_folder)
        self._readiness_test_provider_button = self._make_button(
            "first_run_test_provider",
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
        )
        self._readiness_test_provider_button.clicked.connect(self._readiness_test_provider)
        self._readiness_models_button = self._make_button(
            "first_run_configure_models",
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
        )
        self._readiness_models_button.clicked.connect(
            lambda: self._select_settings_tab_for_widget(self._models_tab_widget)
        )
        self._readiness_speed_button = self._make_button(
            "first_run_optimize_speed",
            self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon),
        )
        self._readiness_speed_button.clicked.connect(self._readiness_optimize_speed)
        self._readiness_runtime_button = self._make_button(
            "first_run_open_runtime",
            self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation),
        )
        self._readiness_runtime_button.clicked.connect(
            lambda: self._select_settings_tab_for_widget(self._runtime_tab_widget)
        )
        layout.addWidget(
            self._readiness_button_grid(
                (
                    self._readiness_download_button,
                    self._readiness_preview_missing_button,
                    self._readiness_model_folder_button,
                    self._readiness_test_provider_button,
                    self._readiness_models_button,
                    self._readiness_speed_button,
                    self._readiness_runtime_button,
                ),
                columns=2,
            )
        )

        self._readiness_basic_button = self._make_button(
            "first_run_open_basic",
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView),
        )
        self._readiness_basic_button.clicked.connect(
            lambda: self._select_settings_tab_for_widget(self._basic_tab_widget)
        )
        self._readiness_video_button = self._make_button(
            "open_video",
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
        )
        self._readiness_video_button.clicked.connect(
            lambda _checked=False: self._start_workflow("video", self._open_video)
        )
        self._readiness_url_button = self._make_button(
            "open_url",
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
        )
        self._readiness_url_button.clicked.connect(
            lambda _checked=False: self._start_workflow("url", self._open_video_url)
        )
        self._readiness_document_button = self._make_button(
            "open_document",
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon),
        )
        self._readiness_document_button.clicked.connect(
            lambda _checked=False: self._start_workflow("document", self._open_document)
        )
        self._readiness_meeting_button = self._make_button(
            "meeting_start_label",
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
        )
        self._readiness_meeting_button.clicked.connect(
            lambda _checked=False: self._start_workflow("meeting", self._toggle_meeting)
        )
        layout.addWidget(
            self._readiness_button_grid(
                (
                    self._readiness_basic_button,
                    self._readiness_video_button,
                    self._readiness_url_button,
                    self._readiness_document_button,
                    self._readiness_meeting_button,
                ),
                columns=2,
            )
        )

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        layout.addWidget(self._section_title("first_run_health_group"))
        self._readiness_status = QLabel("")
        self._readiness_status.setWordWrap(True)
        self._readiness_status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._readiness_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._readiness_status)
        layout.addStretch(1)

        self._refresh_readiness_profile_text()
        self._refresh_readiness_status()
        return tab

    def _readiness_profile_button_text(self, profile: dict[str, object]) -> str:
        return f"{self._tr(str(profile['title']))}\n{self._tr(str(profile['detail']))}"

    def _readiness_button_grid(self, buttons: tuple[QPushButton, ...], *, columns: int) -> QWidget:
        row = QWidget()
        grid = QGridLayout(row)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        columns = max(1, int(columns or 1))
        for column in range(columns):
            grid.setColumnStretch(column, 1)
        for index, button in enumerate(buttons):
            self._fit_readiness_button(button)
            grid.addWidget(button, index // columns, index % columns)
        return row

    @staticmethod
    def _fit_readiness_button(button: QPushButton) -> None:
        button.setMinimumWidth(0)
        button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

    def _readiness_select_profile(self, profile_key: str) -> None:
        self._readiness_selected_profile = profile_key
        button = self._readiness_profile_buttons.get(profile_key)
        if button is not None:
            button.setChecked(True)
        self._refresh_readiness_status()

    def _refresh_readiness_profile_text(self) -> None:
        if not hasattr(self, "_readiness_profile_buttons"):
            return
        for profile in READINESS_PROFILES:
            button = self._readiness_profile_buttons.get(str(profile["key"]))
            if button is not None:
                button.setText(self._readiness_profile_button_text(profile))
        for button in getattr(self, "_readiness_workflow_buttons", {}).values():
            title_key = str(button.property("workflow_title_key") or "")
            detail_key = str(button.property("workflow_detail_key") or "")
            if title_key and detail_key:
                button.setText(f"{self._tr(title_key)}\n{self._tr(detail_key)}")

    def _refresh_readiness_status(self) -> None:
        if not hasattr(self, "_readiness_status"):
            return
        config = self._readiness_profile_config()
        try:
            items = build_runtime_health(config)
            status_text = format_runtime_health(items)
        except Exception as exc:
            self._readiness_status.setText(self._tr("runtime_health_failed").format(detail=exc))
            self._readiness_recommendation.setText(self._tr("first_run_recommend_runtime"))
            return
        self._readiness_status.setText(status_text)
        attention = [item for item in items if item.status == "ATTENTION"]
        if attention:
            self._readiness_recommendation.setText(
                self._tr("first_run_recommend_missing").format(count=len(attention))
            )
        else:
            self._readiness_recommendation.setText(self._tr("first_run_recommend_ready"))
        missing_keys = tuple(getattr(self, "_missing_offline_model_keys", lambda: ())())
        self._readiness_download_button.setEnabled(bool(missing_keys))
        self._readiness_preview_missing_button.setEnabled(bool(missing_keys))
        self._readiness_test_provider_button.setProperty(
            "provider_preview_kind",
            self._readiness_provider_preview_kind(items),
        )

    def _apply_readiness_profile(self) -> None:
        profile = self._readiness_profile()
        self._set_combo_data(self._performance_preset_combo, profile["preset"])
        self._apply_selected_performance_preset()
        for name, value in dict(profile.get("overrides") or {}).items():
            if name == "audio_source":
                self._set_combo_data(self._audio_source_combo, value)
        self._save_settings()
        self._refresh_readiness_status()
        self.statusBar().showMessage(
            self._tr("first_run_applied").format(profile=self._tr(str(profile["title"])))
        )

    def _readiness_download_missing(self) -> None:
        self._select_settings_tab_for_widget(self._offline_models_tab_widget)
        self._run_missing_offline_model_scripts()

    def _readiness_preview_missing(self) -> None:
        self._select_settings_tab_for_widget(self._offline_models_tab_widget)
        self._preview_missing_offline_model_scripts()

    def _readiness_open_model_folder(self) -> None:
        MODEL_ROOT.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(MODEL_ROOT)))
        self.statusBar().showMessage(self._tr("first_run_model_folder_opened").format(path=MODEL_ROOT))

    def _readiness_test_provider(self) -> None:
        try:
            items = build_runtime_health(self._readiness_profile_config())
        except Exception:
            items = ()
        kind = self._readiness_provider_preview_kind(items)
        self._select_settings_tab_for_widget(self._models_tab_widget)
        self._start_provider_preview(kind)

    def _readiness_optimize_speed(self) -> None:
        self._readiness_select_profile("quick")
        self._apply_readiness_profile()
        self._select_settings_tab_for_widget(self._basic_tab_widget)
        self.statusBar().showMessage(self._tr("first_run_speed_optimized"))

    def _select_settings_tab_for_widget(self, content: QWidget) -> None:
        if not hasattr(self, "_settings_tabs"):
            return
        for index in range(self._settings_tabs.count()):
            if self._settings_tab_contains(self._settings_tabs.widget(index), content):
                set_visible = getattr(self._settings_tabs, "setTabVisible", None)
                if callable(set_visible):
                    set_visible(index, True)
                self._settings_tabs.setCurrentIndex(index)
                return

    def _readiness_profile(self) -> dict[str, object]:
        selected = str(getattr(self, "_readiness_selected_profile", "quick") or "quick")
        return next((profile for profile in READINESS_PROFILES if profile["key"] == selected), READINESS_PROFILES[0])

    def _readiness_profile_config(self) -> AppConfig:
        try:
            config = self._current_runtime_config()
        except Exception:
            config = self._config
        profile = self._readiness_profile()
        config = _config_with_preset(config, str(profile["preset"]))
        overrides = dict(profile.get("overrides") or {})
        return _replace_config_values(config, overrides)

    @staticmethod
    def _readiness_provider_preview_kind(items: tuple[object, ...]) -> str:
        attention_names = [
            str(getattr(item, "name", "") or "").lower()
            for item in items
            if getattr(item, "status", "") == "ATTENTION"
        ]
        for name, kind in (
            ("asr", "asr"),
            ("translation", "translation"),
            ("tts", "tts"),
            ("ocr", "ocr"),
        ):
            if name in attention_names:
                return kind
        return "tts"


def _config_with_preset(config: AppConfig, preset_id: str) -> AppConfig:
    preset = PERFORMANCE_PRESETS.get(preset_id) or {}
    return _replace_config_values(config, preset)


def _replace_config_values(config: AppConfig, values: dict[str, Any]) -> AppConfig:
    field_names = {field.name for field in fields(AppConfig)}
    updates = {name: value for name, value in values.items() if name in field_names and value is not None}
    return replace(config, **updates) if updates else config
