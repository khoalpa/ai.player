from __future__ import annotations

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

from ai_player.core.config import (
    INTERNAL_VIENEU_STANDARD_CODEC,
    INTERNAL_VIENEU_STANDARD_GGUF,
    INTERNAL_VIENEU_TURBO_GGUF,
    LOCAL_SPEAKER_GENDER_MODEL_PATH,
    LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH,
    LOCAL_TRANSLATION_MODEL_PATH,
    LOCAL_WHISPER_MODEL_PATH,
    MODEL_ROOT,
    PROJECT_ROOT,
)
from ai_player.core.runtime_catalog import available_asr_models, available_ocr_models, available_speaker_gender_models
from ai_player.services.translation import available_translation_models


class PlayerOfflineModelsMixin:
    def _offline_models_tab(self) -> QWidget:
        tab = QWidget()
        self._offline_models_tab_widget = tab
        self._offline_model_process: QProcess | None = None
        self._offline_model_rows: dict[str, dict[str, object]] = {}
        self._offline_model_action_buttons: list[QPushButton] = []

        layout = QVBoxLayout(tab)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(8)

        summary = QLabel(self._tr("offline_models_summary"))
        summary.setProperty("i18n_key", "offline_models_summary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(6)
        self._offline_models_run_all_button = self._make_button(
            "offline_models_run_all",
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward),
        )
        self._offline_models_run_all_button.clicked.connect(
            lambda _checked=False: self._run_offline_model_script("all")
        )
        self._offline_models_refresh_button = self._make_button(
            "offline_models_refresh",
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
        )
        self._offline_models_refresh_button.clicked.connect(self._refresh_offline_model_statuses)
        self._offline_models_stop_button = self._make_button(
            "offline_models_stop",
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop),
        )
        self._offline_models_stop_button.clicked.connect(self._stop_offline_model_process)
        self._offline_models_stop_button.setEnabled(False)
        toolbar_layout.addWidget(self._offline_models_run_all_button)
        toolbar_layout.addWidget(self._offline_models_refresh_button)
        toolbar_layout.addWidget(self._offline_models_stop_button)
        toolbar_layout.addStretch(1)
        layout.addWidget(toolbar)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(7)
        headers = (
            (0, "offline_models_component"),
            (1, "offline_models_status"),
            (2, "offline_models_location"),
            (3, "offline_models_action"),
        )
        for column, key in headers:
            label = self._field_label(key)
            grid.addWidget(label, 0, column)

        for row, spec in enumerate(self._offline_model_specs(), 1):
            name = QLabel(self._tr(spec["title_key"]))
            name.setProperty("i18n_key", spec["title_key"])
            name.setWordWrap(True)
            status = QLabel("...")
            status.setWordWrap(True)
            target = QLabel(self._offline_model_target_text(spec))
            target.setTextInteractionFlags(target.textInteractionFlags() | Qt.TextSelectableByMouse)
            target.setWordWrap(True)
            button = self._make_button(
                "offline_models_run",
                self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward),
            )
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            button.clicked.connect(lambda _checked=False, key=spec["key"]: self._run_offline_model_script(key))
            grid.addWidget(name, row, 0)
            grid.addWidget(status, row, 1)
            grid.addWidget(target, row, 2)
            grid.addWidget(button, row, 3)
            self._offline_model_rows[spec["key"]] = {"status": status, "target": target, "button": button}
            self._offline_model_action_buttons.append(button)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 2)
        layout.addLayout(grid)

        self._offline_models_log = QPlainTextEdit()
        self._offline_models_log.setReadOnly(True)
        self._offline_models_log.setMaximumBlockCount(400)
        self._offline_models_log.setPlaceholderText(self._tr("offline_models_log_placeholder"))
        self._offline_models_log.setProperty("i18n_key", "offline_models_log_placeholder")
        self._offline_models_log.setMinimumHeight(110)
        layout.addWidget(self._offline_models_log)
        layout.addStretch(1)

        self._offline_model_action_buttons.append(self._offline_models_run_all_button)
        self._refresh_offline_model_statuses()
        self._sync_offline_model_buttons()
        return tab

    def _offline_model_specs(self) -> tuple[dict[str, object], ...]:
        whisper = Path(LOCAL_WHISPER_MODEL_PATH)
        translation = Path(LOCAL_TRANSLATION_MODEL_PATH)
        translation_ct2 = Path(LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH)
        ocr = MODEL_ROOT / "ocr" / "tessdata"
        portable = PROJECT_ROOT / "dist" / "portable" / "AI Player Lite"
        common_required = (
            whisper / "config.json",
            whisper / "model.bin",
            translation / "config.json",
            translation_ct2 / "model.bin",
            Path(INTERNAL_VIENEU_STANDARD_GGUF),
            Path(INTERNAL_VIENEU_STANDARD_CODEC) / "pytorch_model.bin",
            Path(INTERNAL_VIENEU_TURBO_GGUF),
            ocr / "eng.traineddata",
            ocr / "vie.traineddata",
            ocr / "osd.traineddata",
            LOCAL_SPEAKER_GENDER_MODEL_PATH / "config.json",
        )
        return (
            {
                "key": "all",
                "title_key": "offline_models_all",
                "script": "download_offline_models.ps1",
                "target": MODEL_ROOT,
                "required": common_required,
            },
            {
                "key": "whisper",
                "title_key": "offline_models_whisper",
                "script": "download_whisper_model.ps1",
                "target": whisper,
                "required": (whisper / "config.json", whisper / "model.bin"),
            },
            {
                "key": "translation",
                "title_key": "offline_models_translation",
                "script": "download_translator_models.ps1",
                "target": translation,
                "required": (translation / "config.json", translation / "pytorch_model.bin"),
            },
            {
                "key": "vieneu",
                "title_key": "offline_models_vieneu",
                "script": "download_vieneu_tts_models.ps1",
                "target": MODEL_ROOT / "tts" / "vieneu",
                "required": (
                    Path(INTERNAL_VIENEU_STANDARD_GGUF),
                    Path(INTERNAL_VIENEU_STANDARD_CODEC) / "pytorch_model.bin",
                    Path(INTERNAL_VIENEU_TURBO_GGUF),
                ),
            },
            {
                "key": "ocr",
                "title_key": "offline_models_ocr",
                "script": "download_tessdata_models.ps1",
                "target": ocr,
                "required": (ocr / "eng.traineddata", ocr / "vie.traineddata", ocr / "osd.traineddata"),
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
            },
            {
                "key": "portable",
                "title_key": "offline_models_portable",
                "script": "build_portable.ps1",
                "target": portable,
                "required": (portable / "Run AI Player.bat",),
            },
            {
                "key": "backup",
                "title_key": "offline_models_backup",
                "script": "backup_local.ps1",
                "target": PROJECT_ROOT.parent,
                "required": (),
            },
        )

    def _offline_models_tab_changed(self, index: int) -> None:
        if hasattr(self, "_offline_models_tab_widget") and self._settings_tab_contains(
            self._settings_tabs.widget(index), self._offline_models_tab_widget
        ):
            self._refresh_offline_model_statuses()

    def _run_offline_model_script(self, spec_key: str) -> None:
        if self._offline_model_process is not None:
            self.statusBar().showMessage(self._tr("offline_models_running"))
            return
        spec = self._offline_model_spec(spec_key)
        script = PROJECT_ROOT / "scripts" / str(spec["script"])
        if not script.exists():
            self.statusBar().showMessage(f"{self._tr('offline_models_missing_script')}: {script}")
            return

        program = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
        process = QProcess(self)
        process.setWorkingDirectory(str(PROJECT_ROOT))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._offline_model_process_output_ready)
        process.finished.connect(self._offline_model_process_finished)
        self._offline_model_process = process
        self._offline_model_running_key = spec_key
        self._offline_models_log.appendPlainText(
            self._tr("offline_models_started").format(name=self._tr(str(spec["title_key"])))
        )
        self._sync_offline_model_buttons()
        args = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        process.start(program, args)
        if not process.waitForStarted(3000):
            detail = process.errorString()
            process.deleteLater()
            self._offline_model_process = None
            self._sync_offline_model_buttons()
            self.statusBar().showMessage(self._tr("offline_models_failed").format(detail=detail))

    def _offline_model_process_output_ready(self) -> None:
        process = self._offline_model_process
        if process is None:
            return
        data = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace").strip()
        if data:
            self._offline_models_log.appendPlainText(data)

    def _offline_model_process_finished(self, exit_code: int, _exit_status) -> None:
        process = self._offline_model_process
        running_key = getattr(self, "_offline_model_running_key", "")
        self._offline_model_process_output_ready()
        if process is not None:
            process.deleteLater()
        self._offline_model_process = None
        self._offline_model_running_key = ""
        self._sync_offline_model_buttons()
        self._refresh_offline_model_statuses()
        self._refresh_downloaded_model_combos()
        if exit_code == 0:
            message = self._tr("offline_models_finished").format(name=self._offline_model_name(running_key))
        else:
            message = self._tr("offline_models_failed").format(detail=f"exit code {exit_code}")
        self._offline_models_log.appendPlainText(message)
        self.statusBar().showMessage(message)

    def _stop_offline_model_process(self, wait_ms: int = 5000) -> bool:
        process = getattr(self, "_offline_model_process", None)
        if process is None:
            return True
        try:
            process.readyReadStandardOutput.disconnect(self._offline_model_process_output_ready)
            process.finished.disconnect(self._offline_model_process_finished)
        except (RuntimeError, TypeError):
            pass
        self._offline_model_process_output_ready()
        if process.state() != QProcess.ProcessState.NotRunning:
            process.terminate()
            if not process.waitForFinished(wait_ms):
                process.kill()
                if not process.waitForFinished(wait_ms):
                    return False
        process.deleteLater()
        self._offline_model_process = None
        self._offline_model_running_key = ""
        self._sync_offline_model_buttons()
        message = self._tr("offline_models_stopped")
        if hasattr(self, "_offline_models_log"):
            self._offline_models_log.appendPlainText(message)
        if hasattr(self, "statusBar"):
            self.statusBar().showMessage(message)
        return True

    def _sync_offline_model_buttons(self) -> None:
        running = getattr(self, "_offline_model_process", None) is not None
        for button in getattr(self, "_offline_model_action_buttons", []):
            button.setEnabled(not running)
        if hasattr(self, "_offline_models_refresh_button"):
            self._offline_models_refresh_button.setEnabled(not running)
        if hasattr(self, "_offline_models_stop_button"):
            self._offline_models_stop_button.setEnabled(running)

    def _refresh_offline_model_statuses(self) -> None:
        if not hasattr(self, "_offline_model_rows"):
            return
        for spec in self._offline_model_specs():
            row = self._offline_model_rows.get(str(spec["key"]))
            if not row:
                continue
            status_label = row["status"]
            target_label = row["target"]
            if isinstance(target_label, QLabel):
                target_label.setText(self._offline_model_target_text(spec))
            if isinstance(status_label, QLabel):
                status_label.setText(self._offline_model_status_text(spec))

    def _offline_model_status_text(self, spec: dict[str, object]) -> str:
        required = tuple(Path(path) for path in spec.get("required", ()))
        if not required:
            return self._tr("offline_models_utility")
        ready = sum(1 for path in required if self._offline_model_path_ready(path))
        if ready == len(required):
            return self._tr("offline_models_ready")
        if ready:
            return self._tr("offline_models_partial").format(ready=ready, total=len(required))
        return self._tr("offline_models_missing")

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
        target = Path(spec["target"])
        try:
            return str(target.relative_to(PROJECT_ROOT))
        except ValueError:
            return str(target)

    def _offline_model_spec(self, spec_key: str) -> dict[str, object]:
        for spec in self._offline_model_specs():
            if spec["key"] == spec_key:
                return spec
        return self._offline_model_specs()[0]

    def _offline_model_name(self, spec_key: str) -> str:
        return self._tr(str(self._offline_model_spec(spec_key)["title_key"]))

    def _refresh_downloaded_model_combos(self) -> None:
        if hasattr(self, "_asr_model_combo"):
            current = self._selected_asr_model()
            self._asr_model_combo.clear()
            for model in available_asr_models():
                self._asr_model_combo.addItem(model.name, model.id)
            if current and self._asr_model_combo.findData(current) < 0:
                self._asr_model_combo.addItem(current, current)
            self._asr_model_combo.setCurrentIndex(max(0, self._asr_model_combo.findData(current)))
        if hasattr(self, "_ocr_model_combo"):
            current = self._selected_ocr_model()
            self._ocr_model_combo.clear()
            for model in available_ocr_models():
                self._ocr_model_combo.addItem(model.name, model.id)
            if current and self._ocr_model_combo.findData(current) < 0:
                self._ocr_model_combo.addItem(current, current)
            self._ocr_model_combo.setCurrentIndex(max(0, self._ocr_model_combo.findData(current)))
        if hasattr(self, "_speaker_gender_model_combo"):
            current = self._selected_speaker_gender_model()
            self._speaker_gender_model_combo.clear()
            for model in available_speaker_gender_models():
                self._speaker_gender_model_combo.addItem(model.name, model.id)
            if current and self._speaker_gender_model_combo.findData(current) < 0:
                self._speaker_gender_model_combo.addItem(current, current)
            self._speaker_gender_model_combo.setCurrentIndex(
                max(0, self._speaker_gender_model_combo.findData(current))
            )
        if hasattr(self, "_translator_combo") and hasattr(self, "_nllb_model_combo"):
            self._refresh_translation_models(self._selected_nllb_model())
            if self._nllb_model_combo.count() == 0:
                for model in available_translation_models(self._translator_combo.currentData()):
                    self._nllb_model_combo.addItem(model.name, model.path)
        if hasattr(self, "_vieneu_model_combo"):
            self._refresh_vieneu_models()
