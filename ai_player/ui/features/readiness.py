from __future__ import annotations

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

from ai_player.configuration import MODEL_ROOT, AppConfig
from ai_player.ui.features.base import Feature
from ai_player.ui.readiness_controller import READINESS_PROFILES, ReadinessController, ReadinessProfile


class PlayerReadinessFeature(Feature):
    @property
    def _readiness_selected_profile(self) -> str:
        controller = self.context.get("_readiness_controller", None)
        return controller.selected_profile_key if controller is not None else "auto"

    @_readiness_selected_profile.setter
    def _readiness_selected_profile(self, value: str) -> None:
        controller = self.context.get("_readiness_controller", None)
        if controller is not None:
            controller.select_profile(value)

    def _readiness_tab(self) -> QWidget:
        tab = QWidget()
        self.context.readiness._readiness_tab_widget = tab
        self.context.readiness._readiness_controller = ReadinessController(
            lambda: self.context.settings._current_runtime_config(), self.context.config
        )
        self.context.readiness._readiness_profile_buttons: dict[str, QPushButton] = {}

        layout = QVBoxLayout(tab)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(10)

        summary = QLabel(self.context.settings._tr("first_run_summary"))
        summary.setProperty("i18n_key", "first_run_summary")
        summary.setWordWrap(True)
        summary.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(summary)

        layout.addWidget(self.context.ui._section_title("first_run_workflow_group"))
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
                self.context.sources._open_video,
            ),
            (
                "url",
                "first_run_workflow_url",
                "first_run_workflow_url_detail",
                QStyle.StandardPixmap.SP_BrowserReload,
                self.context.sources._open_video_url,
            ),
            (
                "document",
                "first_run_workflow_document",
                "first_run_workflow_document_detail",
                QStyle.StandardPixmap.SP_FileIcon,
                self.context.sources._open_document,
            ),
            (
                "meeting",
                "first_run_workflow_meeting",
                "first_run_workflow_meeting_detail",
                QStyle.StandardPixmap.SP_MediaPlay,
                self.context.meeting._toggle_meeting,
            ),
        )
        self.context.readiness._readiness_workflow_buttons: dict[str, QPushButton] = {}
        for index, (workflow_key, title_key, detail_key, icon, callback) in enumerate(workflow_specs):
            button = self.context.ui._make_button(title_key, self.context.window.style().standardIcon(icon))
            button.setObjectName("workflowCardButton")
            button.setText(self.context.settings._tr(title_key))
            button.setToolTip(self.context.readiness._readiness_button_tooltip(title_key, detail_key))
            button.setProperty("i18n_key", "")
            button.setProperty("workflow_title_key", title_key)
            button.setProperty("workflow_detail_key", detail_key)
            button.setMinimumHeight(64)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, key=workflow_key, cb=callback: self.context.layout._start_goal_workflow(key, cb)
            )
            self.context.readiness._fit_readiness_button(button)
            workflow_grid.addWidget(button, index // 2, index % 2)
            self.context.readiness._readiness_workflow_buttons[title_key] = button
        layout.addLayout(workflow_grid)

        layout.addWidget(self.context.ui._section_title("first_run_profile_group"))
        self.context.readiness._readiness_profile_toggle = QPushButton(
            self.context.settings._tr("first_run_profile_change")
        )
        self.context.readiness._readiness_profile_toggle.setCheckable(True)
        self.context.readiness._readiness_profile_toggle.setProperty("i18n_key", "first_run_profile_change")
        self.context.readiness._readiness_profile_toggle.setFixedHeight(self.context.ui._COMMAND_BUTTON_HEIGHT)
        self.context.readiness._readiness_profile_toggle.setFixedWidth(self.context.ui._COMMAND_BUTTON_WIDTH)
        layout.addWidget(self.context.readiness._readiness_profile_toggle)
        profile_panel = QWidget(tab)
        self.context.readiness._readiness_profile_panel = profile_panel
        profile_grid = QGridLayout()
        profile_panel.setLayout(profile_grid)
        profile_grid.setHorizontalSpacing(8)
        profile_grid.setVerticalSpacing(8)
        profile_grid.setColumnStretch(0, 1)
        profile_grid.setColumnStretch(1, 1)
        self.context.readiness._readiness_profile_group = QButtonGroup(tab)
        self.context.readiness._readiness_profile_group.setExclusive(True)
        for index, profile in enumerate(READINESS_PROFILES):
            button = QPushButton(self.context.readiness._readiness_profile_button_text(profile))
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(56)
            self.context.readiness._fit_readiness_button(button)
            button.setProperty("readiness_profile", profile.key)
            button.setProperty("readiness_profile_title_key", profile.title_key)
            button.setProperty("readiness_profile_detail_key", profile.detail_key)
            button.setToolTip(self.context.readiness._readiness_button_tooltip(profile.title_key, profile.detail_key))
            button.clicked.connect(
                lambda _checked=False, profile_key=profile.key: self.context.readiness._readiness_select_profile(
                    profile_key
                )
            )
            self.context.readiness._readiness_profile_group.addButton(button)
            self.context.readiness._readiness_profile_buttons[profile.key] = button
            profile_grid.addWidget(button, index // 2, index % 2)
        self.context.readiness._readiness_profile_buttons["auto"].setChecked(True)
        profile_panel.setVisible(False)
        self.context.readiness._readiness_profile_toggle.toggled.connect(profile_panel.setVisible)
        layout.addWidget(profile_panel)

        self.context.readiness._readiness_recommendation = QLabel("")
        self.context.readiness._readiness_recommendation.setWordWrap(True)
        self.context.readiness._readiness_recommendation.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.context.readiness._readiness_recommendation.setObjectName("apiKeyStatusLabel")
        layout.addWidget(self.context.readiness._readiness_recommendation)

        self.context.readiness._readiness_apply_button = self.context.ui._make_button(
            "first_run_apply_profile",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton),
        )
        self.context.readiness._readiness_apply_button.clicked.connect(self.context.readiness._apply_readiness_profile)
        self.context.readiness._readiness_check_button = self.context.ui._make_button(
            "first_run_check",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
        )
        self.context.readiness._readiness_check_button.clicked.connect(self.context.readiness._refresh_readiness_status)
        layout.addWidget(
            self.context.readiness._readiness_button_grid(
                (self.context.readiness._readiness_apply_button, self.context.readiness._readiness_check_button),
                columns=2,
            )
        )

        self.context.readiness._readiness_download_button = self.context.ui._make_button(
            "first_run_download_missing",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward),
        )
        self.context.readiness._readiness_download_button.clicked.connect(
            self.context.readiness._readiness_download_missing
        )
        self.context.readiness._readiness_preview_missing_button = self.context.ui._make_button(
            "first_run_preview_missing",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView),
        )
        self.context.readiness._readiness_preview_missing_button.clicked.connect(
            self.context.readiness._readiness_preview_missing
        )
        self.context.readiness._readiness_model_folder_button = self.context.ui._make_button(
            "first_run_open_model_folder",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
        )
        self.context.readiness._readiness_model_folder_button.clicked.connect(
            self.context.readiness._readiness_open_model_folder
        )
        self.context.readiness._readiness_test_provider_button = self.context.ui._make_button(
            "first_run_test_provider",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
        )
        self.context.readiness._readiness_test_provider_button.clicked.connect(
            self.context.readiness._readiness_test_provider
        )
        self.context.readiness._readiness_models_button = self.context.ui._make_button(
            "first_run_configure_models",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
        )
        self.context.readiness._readiness_models_button.clicked.connect(
            lambda: self.context.readiness._select_settings_tab_for_widget(self.context.bindings._models_tab_widget)
        )
        self.context.readiness._readiness_speed_button = self.context.ui._make_button(
            "first_run_optimize_speed",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon),
        )
        self.context.readiness._readiness_speed_button.clicked.connect(self.context.readiness._readiness_optimize_speed)
        self.context.readiness._readiness_runtime_button = self.context.ui._make_button(
            "first_run_open_runtime",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation),
        )
        self.context.readiness._readiness_runtime_button.clicked.connect(
            lambda: self.context.readiness._select_settings_tab_for_widget(self.context.runtime._runtime_tab_widget)
        )
        layout.addWidget(
            self.context.readiness._readiness_button_grid(
                (
                    self.context.readiness._readiness_download_button,
                    self.context.readiness._readiness_preview_missing_button,
                    self.context.readiness._readiness_model_folder_button,
                    self.context.readiness._readiness_test_provider_button,
                    self.context.readiness._readiness_models_button,
                    self.context.readiness._readiness_speed_button,
                    self.context.readiness._readiness_runtime_button,
                ),
                columns=2,
            )
        )

        self.context.readiness._readiness_basic_button = self.context.ui._make_button(
            "first_run_open_basic",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView),
        )
        self.context.readiness._readiness_basic_button.clicked.connect(
            lambda: self.context.readiness._select_settings_tab_for_widget(self.context.bindings._basic_tab_widget)
        )
        self.context.readiness._readiness_video_button = self.context.ui._make_button(
            "open_video",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
        )
        self.context.readiness._readiness_video_button.clicked.connect(
            lambda _checked=False: self.context.layout._start_workflow("video", self.context.sources._open_video)
        )
        self.context.readiness._readiness_url_button = self.context.ui._make_button(
            "open_url",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
        )
        self.context.readiness._readiness_url_button.clicked.connect(
            lambda _checked=False: self.context.layout._start_workflow("url", self.context.sources._open_video_url)
        )
        self.context.readiness._readiness_document_button = self.context.ui._make_button(
            "open_document",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon),
        )
        self.context.readiness._readiness_document_button.clicked.connect(
            lambda _checked=False: self.context.layout._start_workflow("document", self.context.sources._open_document)
        )
        self.context.readiness._readiness_meeting_button = self.context.ui._make_button(
            "meeting_start_label",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
        )
        self.context.readiness._readiness_meeting_button.clicked.connect(
            lambda _checked=False: self.context.layout._start_workflow("meeting", self.context.meeting._toggle_meeting)
        )
        layout.addWidget(
            self.context.readiness._readiness_button_grid(
                (
                    self.context.readiness._readiness_basic_button,
                    self.context.readiness._readiness_video_button,
                    self.context.readiness._readiness_url_button,
                    self.context.readiness._readiness_document_button,
                    self.context.readiness._readiness_meeting_button,
                ),
                columns=2,
            )
        )

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        layout.addWidget(self.context.ui._section_title("first_run_health_group"))
        self.context.readiness._readiness_status = QLabel("")
        self.context.readiness._readiness_status.setWordWrap(True)
        self.context.readiness._readiness_status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.context.readiness._readiness_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.context.readiness._readiness_status)
        layout.addStretch(1)

        self.context.readiness._refresh_readiness_profile_text()
        self.context.readiness._refresh_readiness_status()
        return tab

    def _readiness_profile_button_text(self, profile: ReadinessProfile) -> str:
        return self.context.settings._tr(profile.title_key)

    def _readiness_button_tooltip(self, title_key: str, detail_key: str) -> str:
        return f"{self.context.settings._tr(title_key)}\n{self.context.settings._tr(detail_key)}"

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
            self.context.readiness._fit_readiness_button(button)
            grid.addWidget(button, index // columns, index % columns)
        return row

    @staticmethod
    def _fit_readiness_button(button: QPushButton) -> None:
        button.setMinimumWidth(0)
        button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

    def _readiness_select_profile(self, profile_key: str) -> None:
        profile = self.context.readiness._readiness_controller.select_profile(profile_key)
        button = self.context.readiness._readiness_profile_buttons.get(profile.key)
        if button is not None:
            button.setChecked(True)
        self.context.readiness._refresh_readiness_status()

    def _refresh_readiness_profile_text(self) -> None:
        if not self.context.has("_readiness_profile_buttons"):
            return
        toggle = self.context.get("_readiness_profile_toggle", None)
        if toggle is not None:
            toggle.setText(self.context.settings._tr("first_run_profile_change"))
        for profile in READINESS_PROFILES:
            button = self.context.readiness._readiness_profile_buttons.get(profile.key)
            if button is not None:
                button.setText(self.context.readiness._readiness_profile_button_text(profile))
                button.setToolTip(
                    self.context.readiness._readiness_button_tooltip(profile.title_key, profile.detail_key)
                )
        for button in self.context.get("_readiness_workflow_buttons", {}).values():
            title_key = str(button.property("workflow_title_key") or "")
            detail_key = str(button.property("workflow_detail_key") or "")
            if title_key and detail_key:
                button.setText(self.context.settings._tr(title_key))
                button.setToolTip(self.context.readiness._readiness_button_tooltip(title_key, detail_key))

    def _refresh_readiness_status(self) -> None:
        if not self.context.has("_readiness_status"):
            return
        try:
            status = self.context.readiness._readiness_controller.status()
        except Exception as exc:
            self.context.readiness._readiness_status.setText(
                self.context.settings._tr("runtime_health_failed").format(detail=exc)
            )
            self.context.readiness._readiness_recommendation.setText(
                self.context.settings._tr("first_run_recommend_runtime")
            )
            return
        self.context.readiness._readiness_status.setText(status.text)
        if status.attention_count:
            self.context.readiness._readiness_recommendation.setText(
                self.context.settings._tr("first_run_recommend_missing").format(count=status.attention_count)
            )
        else:
            self.context.readiness._readiness_recommendation.setText(
                self.context.settings._tr("first_run_recommend_ready")
            )
        missing_keys = tuple(self.context.get("_missing_offline_model_keys", lambda: ())())
        self.context.readiness._readiness_download_button.setEnabled(bool(missing_keys))
        self.context.readiness._readiness_preview_missing_button.setEnabled(bool(missing_keys))
        self.context.readiness._readiness_test_provider_button.setProperty(
            "provider_preview_kind",
            status.provider_preview_kind,
        )

    def _apply_readiness_profile(self) -> None:
        profile = self.context.readiness._readiness_profile()
        self.context.settings._set_combo_data(self.context.layout._performance_preset_combo, profile.preset)
        self.context.settings._apply_selected_performance_preset()
        for name, value in dict(profile.overrides or {}).items():
            if name == "audio_source":
                self.context.settings._set_combo_data(self.context.layout._audio_source_combo, value)
        self.context.settings._save_settings()
        self.context.readiness._refresh_readiness_status()
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("first_run_applied").format(profile=self.context.settings._tr(profile.title_key))
        )

    def _readiness_download_missing(self) -> None:
        self.context.readiness._select_settings_tab_for_widget(self.context.offline_models._offline_models_tab_widget)
        self.context.offline_models._run_missing_offline_model_scripts()

    def _readiness_preview_missing(self) -> None:
        self.context.readiness._select_settings_tab_for_widget(self.context.offline_models._offline_models_tab_widget)
        self.context.offline_models._preview_missing_offline_model_scripts()

    def _readiness_open_model_folder(self) -> None:
        MODEL_ROOT.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(MODEL_ROOT)))
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("first_run_model_folder_opened").format(path=MODEL_ROOT)
        )

    def _readiness_test_provider(self) -> None:
        try:
            kind = self.context.readiness._readiness_controller.status().provider_preview_kind
        except Exception:
            kind = "tts"
        self.context.readiness._select_settings_tab_for_widget(self.context.bindings._models_tab_widget)
        self.context.provider_preview._start_provider_preview(kind)

    def _readiness_optimize_speed(self) -> None:
        self.context.readiness._readiness_select_profile("quick")
        self.context.readiness._apply_readiness_profile()
        self.context.readiness._select_settings_tab_for_widget(self.context.bindings._basic_tab_widget)
        self.context.window.statusBar().showMessage(self.context.settings._tr("first_run_speed_optimized"))

    def _select_settings_tab_for_widget(self, content: QWidget) -> None:
        if not self.context.has("_settings_tabs"):
            return
        for index in range(self.context.layout._settings_tabs.count()):
            if self.context.runtime._settings_tab_contains(self.context.layout._settings_tabs.widget(index), content):
                set_visible = getattr(self.context.layout._settings_tabs, "setTabVisible", None)
                if callable(set_visible):
                    set_visible(index, True)
                self.context.layout._settings_tabs.setCurrentIndex(index)
                return

    def _readiness_profile(self) -> ReadinessProfile:
        return self.context.readiness._readiness_controller.profile()

    def _readiness_profile_config(self) -> AppConfig:
        return self.context.readiness._readiness_controller.profile_config()
