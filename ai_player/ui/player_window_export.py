from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFileDialog, QMenu, QMessageBox

from ai_player.core.config import AppConfig
from ai_player.ui.export_progress_dialog import ExportProgressDialog
from ai_player.ui.player_window_utils import repair_mojibake as _repair_mojibake
from ai_player.ui.player_window_utils import safe_native_dubbing_config as _safe_native_dubbing_config
from ai_player.workers.export_worker import DocumentReviewExportWorker, DubbingExportWorker


class PlayerExportMixin:
    def _show_export_menu(self) -> None:
        menu = QMenu(self)
        save_transcript = QAction(self._tr("export_menu_save_transcript"), self)
        export_audio = QAction(self._tr("export_menu_audio"), self)
        export_video = QAction(self._tr("export_menu_dubbed_video"), self)
        export_review = QAction(self._tr("export_menu_document_video"), self)
        save_transcript.triggered.connect(self._save_transcript)
        export_audio.triggered.connect(lambda: self._export_dubbed_media("audio"))
        export_video.triggered.connect(lambda: self._export_dubbed_media("video"))
        export_review.triggered.connect(self._export_high_quality_review)
        menu.addAction(save_transcript)
        menu.addSeparator()
        menu.addAction(export_audio)
        menu.addAction(export_video)
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

        self._pause_active_source()
        self._stop_dubbing()
        self._export_button.setEnabled(False)
        self._show_export_progress_dialog(title, path, export_config)
        worker = DubbingExportWorker(
            self._video_path,
            path,
            export_kind,
            export_config,
            self,
        )
        self._start_export_worker(worker)
        self.statusBar().showMessage(self._tr("status_export_running"))

    def _export_high_quality_review(self) -> None:
        if self._document_mode:
            self._export_document_review()
            return
        self._export_dubbed_media("video")

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
        worker.failed.connect(self._export_failed)
        worker.finished.connect(lambda worker=worker: self._export_worker_finished(worker))
        worker.start()

    def _show_export_progress_dialog(self, title: str, output_path: str, config: AppConfig) -> None:
        if self._export_dialog is not None:
            self._export_dialog.close()
        self._export_dialog = ExportProgressDialog(title, output_path, config, self)
        self._export_dialog.rejected.connect(self._cancel_export)
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

    def _export_finished(self, output_path: str) -> None:
        self._export_terminal = True
        self._export_button.setEnabled(True)
        if self._export_dialog is not None:
            self._export_dialog.mark_finished(output_path)
        self.statusBar().showMessage(f"{self._tr('status_export_done_prefix')} {output_path}")

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
