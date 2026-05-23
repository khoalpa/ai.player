from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QVBoxLayout,
)

from ai_player.core.config import AppConfig
from ai_player.ui.export_progress_dialog import ExportProgressDialog
from ai_player.ui.player_window_utils import repair_mojibake as _repair_mojibake
from ai_player.ui.player_window_utils import safe_native_dubbing_config as _safe_native_dubbing_config
from ai_player.workers.export_worker import (
    DocumentReviewExportWorker,
    DubbingExportWorker,
    ExportRange,
    StagedDubbingExportWorker,
)


class PlayerExportMixin:
    def _show_export_menu(self) -> None:
        menu = QMenu(self)
        save_transcript = QAction(self._tr("export_menu_save_transcript"), self)
        export_audio = QAction(self._tr("export_menu_audio"), self)
        export_video = QAction(self._tr("export_menu_dubbed_video"), self)
        export_staged = QAction(self._tr("export_menu_staged_dubbing"), self)
        export_review = QAction(self._tr("export_menu_document_video"), self)
        save_transcript.setToolTip(self._tr("export_menu_save_transcript"))
        export_audio.setToolTip(self._tr("export_menu_audio"))
        export_video.setToolTip(self._tr("export_menu_dubbed_video"))
        export_staged.setToolTip(self._tr("export_menu_staged_dubbing"))
        export_review.setToolTip(self._tr("export_menu_document_video"))
        save_transcript.triggered.connect(self._save_transcript)
        export_audio.triggered.connect(lambda: self._export_dubbed_media("audio"))
        export_video.triggered.connect(lambda: self._export_dubbed_media("video"))
        export_staged.triggered.connect(self._export_staged_dubbing)
        export_review.triggered.connect(self._export_high_quality_review)
        menu.addAction(save_transcript)
        menu.addSeparator()
        menu.addAction(export_audio)
        menu.addAction(export_video)
        menu.addAction(export_staged)
        menu.addAction(export_review)
        menu.exec(self._export_button.mapToGlobal(self._export_button.rect().bottomLeft()))

    def _export_dubbed_media(self, export_kind: str) -> None:
        if self._selected_audio_source() == "document_editor" and not self._document_mode:
            if not self._prepare_document_editor_source():
                return
        if self._document_mode:
            if export_kind == "video":
                self._export_document_review()
            else:
                QMessageBox.information(self, self._tr("app_title"), self._tr("msg_export_video_only"))
            return
        if not self._video_path:
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_open_video_first"))
            return
        if self._export_worker is not None:
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_export_running"))
            return
        self._save_settings()
        export_config = _safe_native_dubbing_config(self._config)
        if export_config.audio_source in {"system", "microphone", "system_microphone", "subtitle"}:
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_export_source_unsupported"))
            return

        suffix = ".wav" if export_kind == "audio" else ".mp4"
        title = self._tr("export_audio_title") if export_kind == "audio" else self._tr("export_video_title")
        filter_text = self._tr("file_filter_wav") if export_kind == "audio" else self._tr("file_filter_mp4")
        path, _ = QFileDialog.getSaveFileName(
            self,
            title,
            str(Path.home() / f"ai-player-dubbed{suffix}"),
            filter_text,
        )
        if not path:
            return
        if not Path(path).suffix:
            path += suffix
        export_range = ExportRange()
        if export_kind == "video":
            export_range = self._choose_export_range()
            if export_range is None:
                return

        self._pause_active_source()
        self._stop_dubbing()
        self._export_button.setEnabled(False)
        self._show_export_progress_dialog(title, path, export_config)
        worker = DubbingExportWorker(
            self._video_path,
            path,
            export_kind,
            export_config,
            export_range,
            self,
        )
        self._start_export_worker(worker)
        self.statusBar().showMessage(self._tr("status_export_running"))

    def _export_high_quality_review(self) -> None:
        if self._document_mode:
            self._export_document_review()
            return
        self._export_dubbed_media("video")

    def _export_staged_dubbing(self) -> None:
        if self._document_mode:
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_export_video_only"))
            return
        if not self._video_path:
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_open_video_first"))
            return
        if self._export_worker is not None:
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_export_running"))
            return
        self._save_settings()
        export_config = _safe_native_dubbing_config(self._config)
        if export_config.audio_source != "original":
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_staged_export_source_unsupported"))
            return
        output_dir = QFileDialog.getExistingDirectory(
            self,
            self._tr("export_staged_title"),
            str(Path.home() / "ai-player-staged-dubbing"),
        )
        if not output_dir:
            return
        export_range = self._choose_export_range()
        if export_range is None:
            return

        self._pause_active_source()
        self._stop_dubbing()
        self._export_button.setEnabled(False)
        self._show_export_progress_dialog(self._tr("export_staged_title"), output_dir, export_config)
        worker = StagedDubbingExportWorker(
            self._video_path,
            output_dir,
            export_config,
            export_range,
            self,
        )
        self._start_export_worker(worker)
        self.statusBar().showMessage(self._tr("status_staged_export_running"))

    def _export_document_review(self) -> None:
        if not self._document_mode or not self._document_pages:
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_open_document_first"))
            return
        if self._export_worker is not None:
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_export_running"))
            return
        transcript_path = self._transcript_path_edit.text().strip()
        if not transcript_path:
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_document_no_transcript"))
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            self._tr("export_document_video_title"),
            str(Path.home() / "ai-player-document-review.mp4"),
            self._tr("file_filter_mp4"),
        )
        if not path:
            return
        if not Path(path).suffix:
            path += ".mp4"

        self._save_settings()
        export_config = _safe_native_dubbing_config(self._config)
        self._pause_active_source()
        self._stop_dubbing()
        self._export_button.setEnabled(False)
        self._show_export_progress_dialog(self._tr("export_document_video_title"), path, export_config)
        worker = DocumentReviewExportWorker(
            transcript_path,
            self._document_pages,
            path,
            export_config,
            self,
        )
        self._start_export_worker(worker)
        self.statusBar().showMessage(self._tr("status_document_export_running"))

    def _start_export_worker(self, worker) -> None:
        self._export_worker = worker
        self._export_terminal = False
        worker.progress_changed.connect(self._export_progress_changed)
        worker.progress_percent.connect(self._export_progress_percent_changed)
        worker.export_finished.connect(self._export_finished)
        worker.partial_finished.connect(self._export_partial_finished)
        worker.failed.connect(self._export_failed)
        worker.finished.connect(lambda worker=worker: self._export_worker_finished(worker))
        worker.start()

    def _show_export_progress_dialog(self, title: str, output_path: str, config: AppConfig) -> None:
        if self._export_dialog is not None:
            self._export_dialog.close()
        self._export_dialog = ExportProgressDialog(title, output_path, config, self)
        self._export_dialog.rejected.connect(self._cancel_export)
        self._export_dialog.keep_partial_requested.connect(self._keep_partial_export)
        self._export_dialog.show()
        self._export_dialog.raise_()

    def _export_progress_changed(self, message: str) -> None:
        clean = _repair_mojibake(message)
        self.statusBar().showMessage(clean)
        if self._export_dialog is not None:
            self._export_dialog.update_status(clean)

    def _export_progress_percent_changed(self, value: int) -> None:
        if self._export_dialog is not None:
            self._export_dialog.update_progress(value)

    def _cancel_export(self) -> None:
        worker = self._export_worker
        if worker is None:
            return
        worker.stop()
        self.statusBar().showMessage(self._tr("status_cancel_export"))
        if self._export_dialog is not None:
            self._export_dialog.update_status(self._tr("status_cancel_export_requested"))

    def _keep_partial_export(self) -> None:
        worker = self._export_worker
        if worker is None:
            return
        worker.stop(keep_partial=True)
        self.statusBar().showMessage(self._tr("status_keep_partial_export_requested"))

    def _export_finished(self, output_path: str) -> None:
        self._export_terminal = True
        self._export_button.setEnabled(True)
        if self._export_dialog is not None:
            self._export_dialog.mark_finished(output_path)
        self.statusBar().showMessage(f"{self._tr('status_export_done_prefix')} {output_path}")

    def _export_partial_finished(self, output_path: str) -> None:
        self._export_terminal = True
        self._export_button.setEnabled(True)
        if self._export_dialog is not None:
            self._export_dialog.mark_partial_finished(output_path)
        self.statusBar().showMessage(f"{self._tr('status_export_partial_done_prefix')} {output_path}")

    def _export_failed(self, message: str) -> None:
        self._export_terminal = True
        self._export_button.setEnabled(True)
        if self._export_dialog is not None:
            self._export_dialog.mark_failed(message)
        self.statusBar().showMessage(self._tr("status_export_stopped"))

    def _export_worker_finished(self, worker) -> None:
        if self._export_worker is worker and not self._export_terminal:
            self._export_button.setEnabled(True)
            self.statusBar().showMessage(self._tr("status_cancel_export"))
            if self._export_dialog is not None:
                self._export_dialog.mark_cancelled(self._tr("status_cancel_export"))
        if self._export_worker is worker:
            self._export_worker = None
        worker.deleteLater()

    def _choose_export_range(self) -> ExportRange | None:
        duration_seconds = max(0.0, self._player.get_length_ms() / 1000.0)
        dialog = _ExportRangeDialog(self._tr, duration_seconds, self)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.export_range()


class _ExportRangeDialog(QDialog):
    def __init__(self, tr, duration_seconds: float, parent=None) -> None:
        super().__init__(parent)
        self._tr = tr
        self._duration_seconds = duration_seconds
        self.setWindowTitle(self._tr("export_range_title"))
        self.resize(360, 160)

        layout = QVBoxLayout(self)
        self._full_check = QCheckBox(self._tr("export_range_full"), self)
        self._full_check.setChecked(True)
        self._full_check.setToolTip(self._tr("export_range_full"))
        layout.addWidget(self._full_check)

        form = QFormLayout()
        self._start_edit = QLineEdit("00:00:00", self)
        self._end_edit = QLineEdit(_format_time(duration_seconds) if duration_seconds > 0 else "", self)
        self._start_edit.setToolTip(self._tr("export_range_start"))
        self._end_edit.setToolTip(self._tr("export_range_end"))
        form.addRow(self._tr("export_range_start"), self._start_edit)
        form.addRow(self._tr("export_range_end"), self._end_edit)
        layout.addLayout(form)

        self._buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        ok_button = self._buttons.button(QDialogButtonBox.Ok)
        cancel_button = self._buttons.button(QDialogButtonBox.Cancel)
        if ok_button is not None:
            ok_button.setToolTip(self._tr("done"))
        if cancel_button is not None:
            cancel_button.setToolTip(self._tr("close"))
        self._buttons.accepted.connect(self._accept_if_valid)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self._full_check.toggled.connect(self._sync_enabled)
        self._sync_enabled(True)

    def export_range(self) -> ExportRange:
        if self._full_check.isChecked():
            return ExportRange()
        return ExportRange(_parse_time(self._start_edit.text()), _parse_time(self._end_edit.text()))

    def _sync_enabled(self, full: bool) -> None:
        self._start_edit.setEnabled(not full)
        self._end_edit.setEnabled(not full)

    def _accept_if_valid(self) -> None:
        if self._full_check.isChecked():
            self.accept()
            return
        try:
            start = _parse_time(self._start_edit.text())
            end = _parse_time(self._end_edit.text())
        except ValueError:
            QMessageBox.warning(self, self.windowTitle(), self._tr("export_range_invalid"))
            return
        if start < 0 or end <= start or (self._duration_seconds > 0 and end > self._duration_seconds + 0.5):
            QMessageBox.warning(self, self.windowTitle(), self._tr("export_range_invalid"))
            return
        self.accept()


def _parse_time(value: str) -> float:
    text = value.strip()
    if not text:
        raise ValueError("empty time")
    parts = text.split(":")
    try:
        if len(parts) == 1:
            return _finite_time_value(float(parts[0]))
        if len(parts) == 2:
            minutes, seconds = parts
            return _finite_time_value(int(minutes) * 60 + float(seconds))
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return _finite_time_value(int(hours) * 3600 + int(minutes) * 60 + float(seconds))
    except (OverflowError, ValueError) as exc:
        raise ValueError("invalid time") from exc
    raise ValueError("invalid time")


def _format_time(seconds_value: float) -> str:
    if not math.isfinite(seconds_value):
        seconds_value = 0.0
    total_seconds = max(0, int(round(seconds_value)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _finite_time_value(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("invalid time")
    return max(0.0, value)
