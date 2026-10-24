from __future__ import annotations

import importlib
import importlib.util
import shutil
from pathlib import Path

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from ai_player.adapters.ai.translation import available_translation_models
from ai_player.configuration import (
    INTERNAL_VIENEU_PYTHON,
    INTERNAL_VIENEU_V3_PATH,
    LOCAL_SPEAKER_GENDER_MODEL_PATH,
    LOCAL_TRANSLATION_MODEL_PATH,
    LOCAL_WHISPER_MODEL_PATH,
    MODEL_ROOT,
    PROJECT_ROOT,
)
from ai_player.core.redaction import redact_secrets
from ai_player.runtime.runtime_catalog import (
    available_asr_models,
    available_ocr_models,
    available_speaker_gender_models,
)
from ai_player.runtime.vieneu_v3 import CPU_FILES
from ai_player.ui.features.base import Feature


class PlayerOfflineModelsFeature(Feature):
    def _offline_models_tab(self) -> QWidget:
        tab = QWidget()
        self.context.offline_models._offline_models_tab_widget = tab
        self.context.offline_models._offline_model_process: QProcess | None = None
        self.context.offline_models._offline_model_rows: dict[str, dict[str, object]] = {}
        self.context.offline_models._offline_model_action_buttons: list[QPushButton] = []

        layout = QVBoxLayout(tab)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(8)

        summary = QLabel(self.context.settings._tr("offline_models_summary"))
        summary.setProperty("i18n_key", "offline_models_summary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self.context.offline_models._offline_models_storage_summary = QLabel("...")
        self.context.offline_models._offline_models_storage_summary.setWordWrap(True)
        self.context.offline_models._offline_models_storage_summary.setTextInteractionFlags(
            self.context.offline_models._offline_models_storage_summary.textInteractionFlags()
            | Qt.TextSelectableByMouse
        )
        layout.addWidget(self.context.offline_models._offline_models_storage_summary)

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(6)
        self.context.offline_models._offline_models_run_all_button = self.context.ui._make_button(
            "offline_models_run_all",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward),
        )
        self.context.offline_models._offline_models_run_all_button.clicked.connect(
            lambda _checked=False: self.context.offline_models._run_offline_model_script("all")
        )
        self.context.offline_models._offline_models_run_missing_button = self.context.ui._make_button(
            "offline_models_run_missing",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton),
        )
        self.context.offline_models._offline_models_run_missing_button.clicked.connect(
            self.context.offline_models._run_missing_offline_model_scripts
        )
        self.context.offline_models._offline_models_preview_missing_button = self.context.ui._make_button(
            "offline_models_preview_missing",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation),
        )
        self.context.offline_models._offline_models_preview_missing_button.clicked.connect(
            self.context.offline_models._preview_missing_offline_model_scripts
        )
        self.context.offline_models._offline_models_refresh_button = self.context.ui._make_button(
            "offline_models_refresh",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
        )
        self.context.offline_models._offline_models_refresh_button.clicked.connect(
            self.context.offline_models._refresh_offline_model_statuses
        )
        self.context.offline_models._offline_models_stop_button = self.context.ui._make_button(
            "offline_models_stop",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop),
        )
        self.context.offline_models._offline_models_stop_button.clicked.connect(
            self.context.offline_models._stop_offline_model_process
        )
        self.context.offline_models._offline_models_stop_button.setEnabled(False)
        toolbar_layout.addWidget(self.context.offline_models._offline_models_run_all_button)
        toolbar_layout.addWidget(self.context.offline_models._offline_models_run_missing_button)
        toolbar_layout.addWidget(self.context.offline_models._offline_models_preview_missing_button)
        toolbar_layout.addWidget(self.context.offline_models._offline_models_refresh_button)
        toolbar_layout.addWidget(self.context.offline_models._offline_models_stop_button)
        toolbar_layout.addStretch(1)
        layout.addWidget(toolbar)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(7)
        headers = (
            (0, "offline_models_component"),
            (1, "offline_models_status"),
            (2, "offline_models_size"),
            (3, "offline_models_location"),
            (4, "offline_models_action"),
        )
        for column, key in headers:
            label = self.context.ui._field_label(key)
            if column == 4:
                label.setAlignment(Qt.AlignCenter)
            grid.addWidget(label, 0, column)

        for row, spec in enumerate(self.context.offline_models._offline_model_specs(), 1):
            name = QLabel(self.context.settings._tr(spec["title_key"]))
            name.setProperty("i18n_key", spec["title_key"])
            name.setWordWrap(True)
            name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            status = QLabel("...")
            status.setWordWrap(True)
            status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            size = QLabel("...")
            size.setTextInteractionFlags(size.textInteractionFlags() | Qt.TextSelectableByMouse)
            size.setWordWrap(True)
            target = QLabel(self.context.offline_models._offline_model_target_text(spec))
            target.setTextInteractionFlags(target.textInteractionFlags() | Qt.TextSelectableByMouse)
            target.setWordWrap(True)
            target.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            button = self.context.ui._make_button(
                str(spec.get("action_key", "offline_models_download")),
                self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward),
            )
            button.setMinimumWidth(72)
            button.setMaximumWidth(110)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            button.clicked.connect(
                lambda _checked=False, key=spec["key"]: self.context.offline_models._run_offline_model_script(key)
            )
            grid.addWidget(name, row, 0)
            grid.addWidget(status, row, 1)
            grid.addWidget(size, row, 2)
            grid.addWidget(target, row, 3)
            grid.addWidget(button, row, 4, alignment=Qt.AlignTop | Qt.AlignRight)
            self.context.offline_models._offline_model_rows[spec["key"]] = {
                "status": status,
                "size": size,
                "target": target,
                "button": button,
            }
            self.context.offline_models._offline_model_action_buttons.append(button)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 2)
        grid.setColumnStretch(4, 0)
        layout.addLayout(grid)

        self.context.offline_models._offline_models_log = QPlainTextEdit()
        self.context.offline_models._offline_models_log.setReadOnly(True)
        self.context.offline_models._offline_models_log.setMaximumBlockCount(400)
        self.context.offline_models._offline_models_log.setPlaceholderText(
            self.context.settings._tr("offline_models_log_placeholder")
        )
        self.context.offline_models._offline_models_log.setProperty("i18n_key", "offline_models_log_placeholder")
        self.context.offline_models._offline_models_log.setMinimumHeight(110)
        layout.addWidget(self.context.offline_models._offline_models_log)
        layout.addStretch(1)

        self.context.offline_models._offline_model_action_buttons.append(
            self.context.offline_models._offline_models_run_all_button
        )
        self.context.offline_models._offline_model_action_buttons.append(
            self.context.offline_models._offline_models_run_missing_button
        )
        self.context.offline_models._offline_model_action_buttons.append(
            self.context.offline_models._offline_models_preview_missing_button
        )
        self.context.offline_models._sync_offline_model_buttons()
        return tab

    def _offline_model_specs(self) -> tuple[dict[str, object], ...]:
        whisper = Path(LOCAL_WHISPER_MODEL_PATH)
        translation = Path(LOCAL_TRANSLATION_MODEL_PATH)
        ocr = MODEL_ROOT / "ocr" / "tessdata_best"
        portable = PROJECT_ROOT / "dist" / "portable" / "AI Player Lite"
        common_required = (
            whisper / "config.json",
            whisper / "model.bin",
            translation / "config.json",
            *(INTERNAL_VIENEU_V3_PATH / name for name in CPU_FILES),
            Path(INTERNAL_VIENEU_PYTHON),
            ocr / "eng.traineddata",
            ocr / "vie.traineddata",
            ocr / "osd.traineddata",
            LOCAL_SPEAKER_GENDER_MODEL_PATH / "config.json",
        )
        return (
            {
                "key": "all",
                "title_key": "offline_models_all",
                "action_key": "offline_models_run_all",
                "script": "download_offline_models.ps1",
                "target": MODEL_ROOT,
                "required": common_required,
                "estimated_size": 12 * 1024**3,
            },
            {
                "key": "whisper",
                "title_key": "offline_models_whisper",
                "script": "download_whisper_model.ps1",
                "target": whisper,
                "required": (whisper / "config.json", whisper / "model.bin"),
                "estimated_size": 3 * 1024**3,
            },
            {
                "key": "translation",
                "title_key": "offline_models_translation",
                "script": "download_translator_models.ps1",
                "target": translation,
                "required": (
                    translation / "config.json",
                    translation / "pytorch_model.bin",
                ),
                "estimated_size": 6 * 1024**3,
            },
            {
                "key": "vieneu",
                "title_key": "offline_models_vieneu",
                "script": "download_vieneu_tts_models.ps1",
                "target": MODEL_ROOT / "tts" / "vieneu",
                "required": (
                    *(INTERNAL_VIENEU_V3_PATH / name for name in CPU_FILES),
                    Path(INTERNAL_VIENEU_PYTHON),
                ),
                "estimated_size": 2 * 1024**3,
            },
            {
                "key": "ocr",
                "title_key": "offline_models_ocr",
                "script": "download_tessdata_models.ps1",
                "target": ocr,
                "required": (ocr / "eng.traineddata", ocr / "vie.traineddata", ocr / "osd.traineddata"),
                "estimated_size": 100 * 1024**2,
            },
            {
                "key": "speaker_gender",
                "title_key": "offline_models_speaker_gender",
                "script": "download_speaker_gender_model.ps1",
                "target": LOCAL_SPEAKER_GENDER_MODEL_PATH,
                "required": (
                    LOCAL_SPEAKER_GENDER_MODEL_PATH / "config.json",
                    LOCAL_SPEAKER_GENDER_MODEL_PATH / "preprocessor_config.json",
                ),
                "estimated_size": 200 * 1024**2,
            },
            {
                "key": "adult_extractors",
                "title_key": "offline_models_adult_extractors",
                "action_key": "offline_models_install",
                "script": "install_adult_extractors.ps1",
                "target_text": "ai-player-adult-extractors",
                "required_modules": ("yt_dlp_plugins.extractor.adult_sites",),
            },
            {
                "key": "telegram_client",
                "title_key": "offline_models_telegram_client",
                "action_key": "offline_models_install",
                "script": "install_telegram_client.ps1",
                "target_text": "ai-player-telegram-client",
                "required_modules": ("ai_player_telegram_client.adapter",),
            },
            {
                "key": "youtube_client",
                "title_key": "offline_models_youtube_client",
                "action_key": "offline_models_install",
                "script": "install_youtube_client.ps1",
                "target_text": "ai-player-youtube-client",
                "required_modules": ("ai_player_youtube_client.adapter",),
            },
            {
                "key": "portable",
                "title_key": "offline_models_portable",
                "action_key": "offline_models_build",
                "script": "build_portable.ps1",
                "target": portable,
                "required": (portable / "Run AI Player.bat",),
            },
            {
                "key": "backup",
                "title_key": "offline_models_backup",
                "action_key": "offline_models_backup_action",
                "script": "backup_local.ps1",
                "target": PROJECT_ROOT.parent,
                "required": (),
            },
        )

    def _offline_models_tab_changed(self, index: int) -> None:
        if self.context.has("_offline_models_tab_widget") and self.context.runtime._settings_tab_contains(
            self.context.layout._settings_tabs.widget(index), self.context.offline_models._offline_models_tab_widget
        ):
            self.context.offline_models._refresh_offline_model_statuses()

    def _run_offline_model_script(self, spec_key: str) -> None:
        if self.context.offline_models._offline_model_process is not None:
            self.context.window.statusBar().showMessage(self.context.settings._tr("offline_models_running"))
            return
        self.context.offline_models._offline_model_queue = []
        self.context.offline_models._offline_model_queue_active = False
        self.context.offline_models._offline_model_queue_total = 0
        self.context.offline_models._start_offline_model_script(spec_key)

    def _run_missing_offline_model_scripts(self) -> None:
        if self.context.offline_models._offline_model_process is not None:
            self.context.window.statusBar().showMessage(self.context.settings._tr("offline_models_running"))
            return
        keys = list(self.context.offline_models._missing_offline_model_keys())
        if not keys:
            message = self.context.settings._tr("offline_models_missing_none")
            if self.context.has("_offline_models_log"):
                self.context.offline_models._offline_models_log.appendPlainText(message)
            self.context.window.statusBar().showMessage(message)
            return
        disk_warning = self.context.offline_models._offline_model_queue_disk_space_warning(keys)
        if disk_warning:
            self.context.offline_models._offline_model_queue = []
            self.context.offline_models._offline_model_queue_active = False
            self.context.offline_models._offline_model_queue_total = 0
            if self.context.has("_offline_models_log"):
                self.context.offline_models._offline_models_log.appendPlainText(disk_warning)
            self.context.window.statusBar().showMessage(disk_warning)
            return
        self.context.offline_models._offline_model_queue = keys
        self.context.offline_models._offline_model_queue_active = True
        self.context.offline_models._offline_model_queue_total = len(keys)
        message = self.context.settings._tr("offline_models_missing_queued").format(count=len(keys))
        if self.context.has("_offline_models_log"):
            self.context.offline_models._offline_models_log.appendPlainText(message)
        self.context.window.statusBar().showMessage(message)
        self.context.offline_models._run_next_queued_offline_model_script()

    def _preview_missing_offline_model_scripts(self) -> None:
        if self.context.offline_models._offline_model_process is not None:
            self.context.window.statusBar().showMessage(self.context.settings._tr("offline_models_running"))
            return
        keys = self.context.offline_models._missing_offline_model_keys()
        message = self.context.offline_models._offline_model_missing_preview_text(keys)
        if self.context.has("_offline_models_log"):
            self.context.offline_models._offline_models_log.appendPlainText(message)
        self.context.window.statusBar().showMessage(message.splitlines()[0])

    def _run_next_queued_offline_model_script(self) -> None:
        queue = self.context.get("_offline_model_queue", [])
        if not queue:
            return
        next_key = queue.pop(0)
        if not self.context.offline_models._start_offline_model_script(str(next_key)):
            self.context.offline_models._offline_model_queue = []
            self.context.offline_models._offline_model_queue_active = False
            self.context.offline_models._offline_model_queue_total = 0

    def _start_offline_model_script(self, spec_key: str) -> bool:
        spec = self.context.offline_models._offline_model_spec(spec_key)
        script = PROJECT_ROOT / "scripts" / str(spec["script"])
        if not script.exists():
            self.context.window.statusBar().showMessage(
                f"{self.context.settings._tr('offline_models_missing_script')}: {script}"
            )
            return False
        disk_warning = self.context.offline_models._offline_model_disk_space_warning(spec)
        if disk_warning:
            if self.context.has("_offline_models_log"):
                self.context.offline_models._offline_models_log.appendPlainText(disk_warning)
            self.context.window.statusBar().showMessage(disk_warning)
            return False

        program = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
        process = QProcess(self.context.window)
        process.setWorkingDirectory(str(PROJECT_ROOT))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self.context.offline_models._offline_model_process_output_ready)
        process.finished.connect(self.context.offline_models._offline_model_process_finished)
        self.context.offline_models._offline_model_process = process
        self.context.offline_models._offline_model_running_key = spec_key
        message = self.context.offline_models._offline_model_started_message(spec_key, spec)
        self.context.offline_models._offline_model_running_message = message
        set_retry = self.context.get("_set_task_center_retry", None)
        if callable(set_retry):
            set_retry(
                self.context.settings._tr("task_center_retry_offline_model").format(
                    name=self.context.offline_models._offline_model_name(spec_key)
                ),
                lambda key=spec_key: self.context.offline_models._run_offline_model_script(key),
            )
        self.context.offline_models._offline_models_log.appendPlainText(message)
        self.context.window.statusBar().showMessage(message)
        self.context.offline_models._set_offline_model_task_detail(message)
        self.context.offline_models._sync_offline_model_buttons()
        args = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        process.start(program, args)
        if not process.waitForStarted(3000):
            detail = process.errorString()
            process.deleteLater()
            self.context.offline_models._offline_model_process = None
            self.context.offline_models._offline_model_running_message = ""
            self.context.offline_models._sync_offline_model_buttons()
            self.context.offline_models._clear_offline_model_task_detail()
            self.context.window.statusBar().showMessage(
                self.context.settings._tr("offline_models_failed").format(detail=detail)
            )
            return False
        return True

    def _offline_model_started_message(self, spec_key: str, spec: dict[str, object]) -> str:
        name = self.context.settings._tr(
            str(spec.get("title_key") or self.context.offline_models._offline_model_spec(spec_key).get("title_key", ""))
        )
        if self.context.get("_offline_model_queue_active", False):
            total = int(self.context.get("_offline_model_queue_total", 0) or 0)
            if total > 0:
                index = max(1, min(total, total - len(self.context.get("_offline_model_queue", []))))
                return self.context.settings._tr("offline_models_queue_started").format(
                    index=index, total=total, name=name
                )
        return self.context.settings._tr("offline_models_started").format(name=name)

    def _offline_model_process_output_ready(self) -> None:
        process = self.context.offline_models._offline_model_process
        if process is None:
            return
        data = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace").strip()
        if data:
            self.context.offline_models._offline_models_log.appendPlainText(data)
            self.context.offline_models._update_offline_model_task_detail_from_output(data)

    def _offline_model_process_finished(self, exit_code: int, _exit_status) -> None:
        process = self.context.offline_models._offline_model_process
        running_key = self.context.get("_offline_model_running_key", "")
        self.context.offline_models._offline_model_process_output_ready()
        if process is not None:
            process.deleteLater()
        self.context.offline_models._offline_model_process = None
        self.context.offline_models._offline_model_running_key = ""
        self.context.offline_models._offline_model_running_message = ""
        self.context.offline_models._sync_offline_model_buttons()
        self.context.offline_models._refresh_runtime_plugin_caches()
        self.context.offline_models._refresh_offline_model_statuses()
        self.context.offline_models._refresh_downloaded_model_combos()
        if exit_code == 0:
            message = self.context.settings._tr("offline_models_finished").format(
                name=self.context.offline_models._offline_model_name(running_key)
            )
        else:
            message = self.context.settings._tr("offline_models_failed").format(detail=f"exit code {exit_code}")
            self.context.offline_models._offline_model_queue = []
            self.context.offline_models._offline_model_queue_active = False
            self.context.offline_models._offline_model_queue_total = 0
            self.context.offline_models._clear_offline_model_task_detail()
        self.context.offline_models._offline_models_log.appendPlainText(message)
        self.context.window.statusBar().showMessage(message)
        if exit_code == 0 and self.context.get("_offline_model_queue", []):
            self.context.offline_models._run_next_queued_offline_model_script()
        elif exit_code == 0 and self.context.get("_offline_model_queue_active", False):
            self.context.offline_models._offline_model_queue_active = False
            self.context.offline_models._offline_model_queue_total = 0
            message = self.context.settings._tr("offline_models_missing_queue_finished")
            self.context.offline_models._offline_models_log.appendPlainText(message)
            self.context.window.statusBar().showMessage(message)
            self.context.offline_models._clear_offline_model_task_detail()
        elif exit_code == 0:
            self.context.offline_models._clear_offline_model_task_detail()

    def _stop_offline_model_process(self, wait_ms: int = 5000) -> bool:
        process = self.context.get("_offline_model_process", None)
        if process is None:
            return True
        try:
            process.readyReadStandardOutput.disconnect(self.context.offline_models._offline_model_process_output_ready)
            process.finished.disconnect(self.context.offline_models._offline_model_process_finished)
        except (RuntimeError, TypeError):
            pass
        self.context.offline_models._offline_model_process_output_ready()
        if process.state() != QProcess.ProcessState.NotRunning:
            process.terminate()
            if not process.waitForFinished(wait_ms):
                process.kill()
                if not process.waitForFinished(wait_ms):
                    return False
        process.deleteLater()
        self.context.offline_models._offline_model_process = None
        self.context.offline_models._offline_model_running_key = ""
        self.context.offline_models._offline_model_running_message = ""
        self.context.offline_models._offline_model_queue = []
        self.context.offline_models._offline_model_queue_active = False
        self.context.offline_models._offline_model_queue_total = 0
        self.context.offline_models._sync_offline_model_buttons()
        self.context.offline_models._clear_offline_model_task_detail()
        message = self.context.settings._tr("offline_models_stopped")
        if self.context.has("_offline_models_log"):
            self.context.offline_models._offline_models_log.appendPlainText(message)
        if self.context.has("statusBar"):
            self.context.window.statusBar().showMessage(message)
        return True

    def _set_offline_model_task_detail(self, detail: object) -> None:
        set_detail = self.context.get("_set_background_task_detail", None)
        if callable(set_detail):
            set_detail("Offline model download", detail)

    def _update_offline_model_task_detail_from_output(self, data: str) -> None:
        last_line = ""
        for line in str(data or "").splitlines():
            cleaned = " ".join(line.split())
            if cleaned:
                last_line = cleaned
        if not last_line:
            return
        prefix = " ".join(str(self.context.get("_offline_model_running_message", "") or "").split())
        detail = f"{prefix} | {last_line}" if prefix and prefix != last_line else last_line
        self.context.offline_models._set_offline_model_task_detail(detail)

    def _clear_offline_model_task_detail(self) -> None:
        clear_detail = self.context.get("_clear_background_task_detail", None)
        if callable(clear_detail):
            clear_detail("Offline model download")

    def _sync_offline_model_buttons(self) -> None:
        running = self.context.get("_offline_model_process", None) is not None
        for button in self.context.get("_offline_model_action_buttons", []):
            button.setEnabled(not running)
        if self.context.has("_offline_models_refresh_button"):
            self.context.offline_models._offline_models_refresh_button.setEnabled(not running)
        if self.context.has("_offline_models_preview_missing_button"):
            self.context.offline_models._offline_models_preview_missing_button.setEnabled(not running)
        if self.context.has("_offline_models_run_missing_button"):
            self.context.offline_models._offline_models_run_missing_button.setEnabled(
                not running and bool(self.context.offline_models._missing_offline_model_keys())
            )
        if self.context.has("_offline_models_stop_button"):
            self.context.offline_models._offline_models_stop_button.setEnabled(running)

    def _refresh_offline_model_statuses(self) -> None:
        if not self.context.has("_offline_model_rows"):
            return
        if self.context.has("_offline_models_storage_summary"):
            self.context.offline_models._offline_models_storage_summary.setText(
                self.context.offline_models._offline_models_storage_summary_text()
            )
        for spec in self.context.offline_models._offline_model_specs():
            row = self.context.offline_models._offline_model_rows.get(str(spec["key"]))
            if not row:
                continue
            status_label = row["status"]
            size_label = row["size"]
            target_label = row["target"]
            if isinstance(target_label, QLabel):
                target_label.setText(self.context.offline_models._offline_model_target_text(spec))
            if isinstance(size_label, QLabel):
                size_label.setText(self.context.offline_models._offline_model_size_text(spec))
            if isinstance(status_label, QLabel):
                status_label.setText(self.context.offline_models._offline_model_status_text(spec))
        self.context.offline_models._sync_offline_model_buttons()

    def _offline_model_status_text(self, spec: dict[str, object]) -> str:
        ready, total = self.context.offline_models._offline_model_readiness(spec)
        if not total:
            return self.context.settings._tr("offline_models_utility")
        if ready == total:
            return self.context.settings._tr("offline_models_ready")
        if ready:
            return self.context.settings._tr("offline_models_partial").format(ready=ready, total=total)
        return self.context.settings._tr("offline_models_missing")

    def _missing_offline_model_keys(self) -> tuple[str, ...]:
        skipped = {"all", "backup", "portable"}
        keys = []
        for spec in self.context.offline_models._offline_model_specs():
            key = str(spec["key"])
            if key in skipped:
                continue
            ready, total = self.context.offline_models._offline_model_readiness(spec)
            if total and ready < total:
                keys.append(key)
        return tuple(keys)

    def _offline_model_missing_preview_text(self, spec_keys: list[str] | tuple[str, ...]) -> str:
        if not spec_keys:
            return self.context.settings._tr("offline_models_missing_none")
        required_total = sum(
            self.context.offline_models._offline_model_required_free_bytes(
                self.context.offline_models._offline_model_spec(str(spec_key))
            )
            for spec_key in spec_keys
        )
        lines = [
            self.context.settings._tr("offline_models_preview_missing_header").format(
                count=len(spec_keys),
                size=self.context.offline_models._format_offline_model_size(required_total),
            )
        ]
        for index, spec_key in enumerate(spec_keys, 1):
            spec = self.context.offline_models._offline_model_spec(str(spec_key))
            required = self.context.offline_models._offline_model_required_free_bytes(spec)
            lines.append(
                self.context.settings._tr("offline_models_preview_missing_item").format(
                    index=index,
                    name=self.context.settings._tr(str(spec.get("title_key", spec_key))),
                    size=self.context.offline_models._format_offline_model_size(required) if required else "-",
                    target=self.context.offline_models._offline_model_target_text(spec),
                )
            )
        disk_warning = self.context.offline_models._offline_model_queue_disk_space_warning(
            tuple(str(key) for key in spec_keys)
        )
        if disk_warning:
            lines.append(disk_warning)
        return "\n".join(lines)

    def _offline_model_readiness(self, spec: dict[str, object]) -> tuple[int, int]:
        required = tuple(Path(path) for path in spec.get("required", ()))
        required_modules = tuple(str(module) for module in spec.get("required_modules", ()))
        ready = sum(1 for path in required if self.context.offline_models._offline_model_path_ready(path))
        ready += sum(
            1 for module in required_modules if self.context.offline_models._offline_model_module_ready(module)
        )
        total = len(required) + len(required_modules)
        return ready, total

    @staticmethod
    def _offline_model_path_ready(path: Path) -> bool:
        if path.is_file():
            try:
                return path.stat().st_size > 0
            except OSError:
                return False
        if path.is_dir():
            return any(path.iterdir())
        return False

    def _offline_model_target_text(self, spec: dict[str, object]) -> str:
        target_text = str(spec.get("target_text") or "").strip()
        if target_text:
            return target_text
        target = Path(spec["target"])
        try:
            return str(target.relative_to(PROJECT_ROOT))
        except ValueError:
            return str(target)

    def _offline_model_size_text(self, spec: dict[str, object]) -> str:
        if "target" not in spec or spec.get("key") == "backup":
            return "-"
        target = Path(spec["target"])
        size = self.context.offline_models._offline_model_path_size(target)
        estimated = int(spec.get("estimated_size", 0) or 0)
        if estimated > 0:
            estimated_text = self.context.offline_models._format_offline_model_size(estimated)
            if size <= 0:
                return self.context.settings._tr("offline_models_size_needed").format(estimated=estimated_text)
            if size < estimated:
                return self.context.settings._tr("offline_models_size_estimated").format(
                    size=self.context.offline_models._format_offline_model_size(size),
                    estimated=estimated_text,
                )
        return self.context.offline_models._format_offline_model_size(size) if size else "-"

    def _offline_models_storage_summary_text(self) -> str:
        model_size = self.context.offline_models._format_offline_model_size(
            self.context.offline_models._offline_model_path_size(MODEL_ROOT)
        )
        try:
            usage = shutil.disk_usage(MODEL_ROOT if MODEL_ROOT.exists() else PROJECT_ROOT)
        except OSError as exc:
            return self.context.settings._tr("offline_models_storage_summary_unavailable").format(
                size=model_size,
                detail=redact_secrets(exc),
            )
        return self.context.settings._tr("offline_models_storage_summary").format(
            size=model_size,
            free=self.context.offline_models._format_offline_model_size(usage.free),
            total=self.context.offline_models._format_offline_model_size(usage.total),
        )

    def _offline_model_disk_space_warning(self, spec: dict[str, object]) -> str:
        required = self.context.offline_models._offline_model_required_free_bytes(spec)
        if required <= 0:
            return ""
        try:
            usage = shutil.disk_usage(self.context.offline_models._offline_model_disk_usage_path(spec))
        except OSError:
            return ""
        if usage.free >= required:
            return ""
        return self.context.settings._tr("offline_models_low_disk_space").format(
            name=self.context.settings._tr(str(spec.get("title_key", "offline_models_all"))),
            required=self.context.offline_models._format_offline_model_size(required),
            free=self.context.offline_models._format_offline_model_size(usage.free),
        )

    def _offline_model_queue_disk_space_warning(self, spec_keys: list[str] | tuple[str, ...]) -> str:
        required_by_anchor: dict[str, int] = {}
        usage_by_anchor: dict[str, object] = {}
        for spec_key in spec_keys:
            spec = self.context.offline_models._offline_model_spec(str(spec_key))
            required = self.context.offline_models._offline_model_required_free_bytes(spec)
            if required <= 0:
                continue
            usage_path = self.context.offline_models._offline_model_disk_usage_path(spec)
            anchor = str(usage_path.resolve().anchor or usage_path.resolve())
            required_by_anchor[anchor] = required_by_anchor.get(anchor, 0) + required
            if anchor not in usage_by_anchor:
                try:
                    usage_by_anchor[anchor] = shutil.disk_usage(usage_path)
                except OSError:
                    continue
        for anchor, required in required_by_anchor.items():
            usage = usage_by_anchor.get(anchor)
            if usage is not None and usage.free < required:
                return self.context.settings._tr("offline_models_missing_low_disk_space").format(
                    required=self.context.offline_models._format_offline_model_size(required),
                    free=self.context.offline_models._format_offline_model_size(usage.free),
                )
        return ""

    def _offline_model_required_free_bytes(self, spec: dict[str, object]) -> int:
        estimated = int(spec.get("estimated_size", 0) or 0)
        if estimated <= 0 or "target" not in spec:
            return 0
        current_size = self.context.offline_models._offline_model_path_size(Path(spec["target"]))
        return max(0, estimated - current_size)

    @staticmethod
    def _offline_model_disk_usage_path(spec: dict[str, object]) -> Path:
        target = Path(spec["target"]) if "target" in spec else PROJECT_ROOT
        candidate = target if target.exists() else target.parent
        while not candidate.exists() and candidate != candidate.parent:
            candidate = candidate.parent
        return candidate if candidate.exists() else PROJECT_ROOT

    @classmethod
    def _offline_model_path_size(cls, path: Path) -> int:
        if path.is_file():
            try:
                return max(0, int(path.stat().st_size))
            except OSError:
                return 0
        if not path.is_dir():
            return 0
        total = 0
        try:
            entries = list(path.iterdir())
        except OSError:
            return 0
        for entry in entries:
            total += cls._offline_model_path_size(entry)
        return total

    @staticmethod
    def _format_offline_model_size(size: int) -> str:
        amount = float(max(0, int(size or 0)))
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if amount < 1024 or unit == "TB":
                return f"{int(amount)} B" if unit == "B" else f"{amount:.1f} {unit}"
            amount /= 1024
        return f"{amount:.1f} TB"

    def _offline_model_spec(self, spec_key: str) -> dict[str, object]:
        for spec in self.context.offline_models._offline_model_specs():
            if spec["key"] == spec_key:
                return spec
        return self.context.offline_models._offline_model_specs()[0]

    def _offline_model_name(self, spec_key: str) -> str:
        return self.context.settings._tr(str(self.context.offline_models._offline_model_spec(spec_key)["title_key"]))

    @staticmethod
    def _offline_model_module_ready(module_name: str) -> bool:
        try:
            return importlib.util.find_spec(module_name) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            return False

    @staticmethod
    def _refresh_runtime_plugin_caches() -> None:
        importlib.invalidate_caches()
        try:
            from ai_player.adapters.sources import video_source

            video_source._plugin_ytdlp_extractors.cache_clear()
        except Exception:
            pass

    def _refresh_downloaded_model_combos(self) -> None:
        if self.context.has("_asr_model_combo"):
            current = self.context.settings._selected_asr_model()
            self.context.layout._asr_model_combo.clear()
            for model in available_asr_models():
                self.context.layout._asr_model_combo.addItem(model.name, model.id)
            if current and self.context.layout._asr_model_combo.findData(current) < 0:
                self.context.layout._asr_model_combo.addItem(current, current)
            self.context.layout._asr_model_combo.setCurrentIndex(
                max(0, self.context.layout._asr_model_combo.findData(current))
            )
        if self.context.has("_ocr_model_combo"):
            current = self.context.settings._selected_ocr_model()
            self.context.layout._ocr_model_combo.clear()
            for model in available_ocr_models():
                self.context.layout._ocr_model_combo.addItem(model.name, model.id)
            if current and self.context.layout._ocr_model_combo.findData(current) < 0:
                self.context.layout._ocr_model_combo.addItem(current, current)
            self.context.layout._ocr_model_combo.setCurrentIndex(
                max(0, self.context.layout._ocr_model_combo.findData(current))
            )
        if self.context.has("_speaker_gender_model_combo"):
            current = self.context.settings._selected_speaker_gender_model()
            self.context.layout._speaker_gender_model_combo.clear()
            for model in available_speaker_gender_models():
                self.context.layout._speaker_gender_model_combo.addItem(model.name, model.id)
            if current and self.context.layout._speaker_gender_model_combo.findData(current) < 0:
                self.context.layout._speaker_gender_model_combo.addItem(current, current)
            self.context.layout._speaker_gender_model_combo.setCurrentIndex(
                max(0, self.context.layout._speaker_gender_model_combo.findData(current))
            )
        if self.context.has("_translator_combo") and self.context.has("_nllb_model_combo"):
            self.context.settings._refresh_translation_models(self.context.settings._selected_nllb_model())
            if self.context.layout._nllb_model_combo.count() == 0:
                for model in available_translation_models(self.context.layout._translator_combo.currentData()):
                    self.context.layout._nllb_model_combo.addItem(model.name, model.path)
        if self.context.has("_vieneu_model_combo"):
            self.context.settings._refresh_vieneu_models()
