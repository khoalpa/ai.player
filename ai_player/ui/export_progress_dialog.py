from __future__ import annotations

import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QProgressBar, QTextEdit, QVBoxLayout

from ai_player.core.config import AppConfig
from ai_player.ui.player_window_utils import UI_TEXT
from ai_player.ui.player_window_utils import repair_mojibake as _repair_mojibake


class ExportProgressDialog(QDialog):
    def __init__(self, title: str, output_path: str, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self._language = config.gui_language
        self.setWindowTitle(title)
        self.setModal(False)
        self.resize(620, 420)
        self._started_at = time.monotonic()
        self._progress_value = 0
        self._output_path = output_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self._summary = QLabel(self)
        preset_line = (
            f"{self._tr('preset')}: {config.performance_preset} | "
            f"{self._tr('export_summary_quality')}: {config.export_video_quality}"
        )
        source_line = (
            f"{self._tr('export_summary_audio_source')}: {config.audio_source} | "
            f"{self._tr('export_summary_translator')}: {config.translator_provider} | "
            f"TTS: {config.tts_provider}"
        )
        self._summary.setText(
            "\n".join(
                [
                    f"{self._tr('export_summary_file')}: {output_path}",
                    preset_line,
                    source_line,
                ]
            )
        )
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)

        self._status = QLabel(self._tr("export_initial_status"), self)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 100)
        self._progress.setValue(self._progress_value)
        layout.addWidget(self._progress)

        self._time_label = QLabel(self._time_text("00:00", self._tr("export_calculating")), self)
        layout.addWidget(self._time_label)

        self._log = QTextEdit(self)
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(150)
        layout.addWidget(self._log, 1)

        self._buttons = QDialogButtonBox(QDialogButtonBox.Cancel, self)
        self._done = False
        self._buttons.rejected.connect(self._handle_rejected)
        layout.addWidget(self._buttons)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh_time)
        self._timer.start()
        self._refresh_time()

    def update_status(self, message: str) -> None:
        clean = _repair_mojibake(message)
        self._status.setText(clean)
        self._log.append(f"[{self._format_elapsed()}] {clean}")
        self._refresh_time()

    def update_progress(self, value: int) -> None:
        self._progress_value = max(0, min(100, int(value)))
        self._progress.setValue(self._progress_value)
        self._refresh_time()

    def mark_finished(self, output_path: str) -> None:
        self._timer.stop()
        self._done = True
        self._progress_value = 100
        self._progress.setValue(100)
        self._status.setText(f"{self._tr('export_finished_prefix')} {output_path}")
        self._log.append(f"[{self._format_elapsed()}] {self._tr('export_log_finished')}: {output_path}")
        self._set_done_button(self._tr("done"))
        self._refresh_time(done=True)

    def mark_failed(self, message: str) -> None:
        self._timer.stop()
        self._done = True
        clean = _repair_mojibake(message)
        self._status.setText(f"{self._tr('export_failed_prefix')} {clean}")
        self._log.append(f"[{self._format_elapsed()}] {self._tr('export_log_error')}: {clean}")
        self._set_done_button(self._tr("close"))
        self._refresh_time(done=True)

    def mark_cancelled(self, message: str) -> None:
        self._timer.stop()
        self._done = True
        clean = _repair_mojibake(message)
        self._status.setText(clean)
        self._log.append(f"[{self._format_elapsed()}] {clean}")
        self._set_done_button(self._tr("close"))
        self._refresh_time(done=True)

    def _handle_rejected(self) -> None:
        if self._done:
            self.accept()
        else:
            self.reject()

    def _set_done_button(self, label: str) -> None:
        cancel_button = self._buttons.button(QDialogButtonBox.Cancel)
        if cancel_button is not None:
            cancel_button.setText(label)

    def _refresh_time(self, done: bool = False) -> None:
        elapsed = max(0.0, time.monotonic() - self._started_at)
        if done:
            eta = "00:00"
        elif self._progress_value >= 10:
            remaining = elapsed * (100 - self._progress_value) / max(1, self._progress_value)
            eta = self._format_seconds(remaining)
        else:
            eta = self._tr("export_calculating")
        self._time_label.setText(self._time_text(self._format_seconds(elapsed), eta))

    def _tr(self, key: str) -> str:
        fallback = UI_TEXT.get("vi", {})
        return UI_TEXT.get(self._language, fallback).get(key, fallback.get(key, key))

    def _time_text(self, elapsed: str, eta: str) -> str:
        return f"{self._tr('export_elapsed')}: {elapsed} | {self._tr('export_eta')}: {eta}"

    def _format_elapsed(self) -> str:
        return self._format_seconds(time.monotonic() - self._started_at)

    @staticmethod
    def _format_seconds(value: float) -> str:
        seconds = max(0, int(value))
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"
