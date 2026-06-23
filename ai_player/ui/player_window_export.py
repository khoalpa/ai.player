from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
)

from ai_player.core.config import AppConfig
from ai_player.ui.export_progress_dialog import ExportProgressDialog
from ai_player.ui.player_window_utils import repair_mojibake as _repair_mojibake
from ai_player.ui.player_window_utils import safe_native_dubbing_config as _safe_native_dubbing_config
from ai_player.workers.export_worker import (
    STAGED_EXPORT_STAGE_LABEL_KEYS,
    STAGED_EXPORT_STAGES,
    DocumentReviewExportWorker,
    DubbingExportWorker,
    ExportRange,
    StagedDubbingExportWorker,
)
from ai_player.workers.staged_export_utils import StagedExportPaths


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
        stage_dialog = _StagedExportStageDialog(self._tr, Path(output_dir), self)
        if stage_dialog.exec() != QDialog.Accepted:
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
            stage_dialog.start_stage(),
            stage_dialog.end_stage(),
            stage_dialog.force_stage(),
            stage_dialog.artifact_overrides(),
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
        self._worker_lifecycle_state.begin_export(worker)
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
        self._export_progress_text = clean
        self._set_background_task_detail("Export", clean)
        self.statusBar().showMessage(clean)
        if self._export_dialog is not None:
            self._export_dialog.update_status(clean)

    def _export_progress_percent_changed(self, value: int) -> None:
        detail = getattr(self, "_export_progress_text", "")
        if detail:
            self._set_background_task_detail("Export", f"{value}% | {detail}")
        if self._export_dialog is not None:
            self._export_dialog.update_progress(value)

    def _cancel_export(self) -> None:
        if not self._worker_lifecycle_state.request_export_stop():
            return
        self.statusBar().showMessage(self._tr("status_cancel_export"))
        if self._export_dialog is not None:
            self._export_dialog.update_status(self._tr("status_cancel_export_requested"))

    def _keep_partial_export(self) -> None:
        if not self._worker_lifecycle_state.request_export_stop(keep_partial=True):
            return
        self.statusBar().showMessage(self._tr("status_keep_partial_export_requested"))

    def _export_finished(self, output_path: str) -> None:
        self._export_terminal = True
        self._export_button.setEnabled(True)
        if self._export_dialog is not None:
            self._export_dialog.mark_finished(output_path)
        self.statusBar().showMessage(f"{self._tr('status_export_done_prefix')} {output_path}")
        self._clear_background_task_detail("Export")

    def _export_partial_finished(self, output_path: str) -> None:
        self._export_terminal = True
        self._export_button.setEnabled(True)
        if self._export_dialog is not None:
            self._export_dialog.mark_partial_finished(output_path)
        self.statusBar().showMessage(f"{self._tr('status_export_partial_done_prefix')} {output_path}")
        self._clear_background_task_detail("Export")

    def _export_failed(self, message: str) -> None:
        self._export_terminal = True
        self._export_button.setEnabled(True)
        if self._export_dialog is not None:
            self._export_dialog.mark_failed(message)
        self.statusBar().showMessage(self._tr("status_export_stopped"))
        self._clear_background_task_detail("Export")

    def _export_worker_finished(self, worker) -> None:
        cancelled = self._worker_lifecycle_state.finish_export(worker, terminal=self._export_terminal)
        if cancelled:
            self._export_button.setEnabled(True)
            self.statusBar().showMessage(self._tr("status_cancel_export"))
            if self._export_dialog is not None:
                self._export_dialog.mark_cancelled(self._tr("status_cancel_export"))
            self._clear_background_task_detail("Export")
        worker.deleteLater()

    def _choose_export_range(self) -> ExportRange | None:
        duration_seconds = max(0.0, self._player.get_length_ms() / 1000.0)
        dialog = _ExportRangeDialog(self._tr, duration_seconds, self)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.export_range()


class _StagedExportStageDialog(QDialog):
    _ARTIFACT_LABEL_KEYS = {
        "source_video": "staged_export_artifact_source_video",
        "source_full": "staged_export_artifact_source_full",
        "source_srt": "staged_export_artifact_source_srt",
        "words_json": "staged_export_artifact_words_json",
        "target_srt": "staged_export_artifact_target_srt",
        "source_voice": "staged_export_artifact_source_voice",
        "background": "staged_export_artifact_background",
        "tts_dir": "staged_export_artifact_tts_dir",
        "target_voice": "staged_export_artifact_target_voice",
        "final_mix": "staged_export_artifact_final_mix",
        "final_video": "staged_export_artifact_final_video",
    }
    _ARTIFACT_FILTERS = {
        "source_video": "MP4 video (*.mp4);;All files (*.*)",
        "source_full": "WAV audio (*.wav);;All files (*.*)",
        "source_srt": "Subtitle files (*.srt);;All files (*.*)",
        "words_json": "JSON files (*.json);;All files (*.*)",
        "target_srt": "Subtitle files (*.srt);;All files (*.*)",
        "source_voice": "WAV audio (*.wav);;All files (*.*)",
        "background": "WAV audio (*.wav);;All files (*.*)",
        "target_voice": "WAV audio (*.wav);;All files (*.*)",
        "final_mix": "WAV audio (*.wav);;All files (*.*)",
        "final_video": "MP4 video (*.mp4);;All files (*.*)",
    }
    _OVERRIDABLE_ARTIFACTS = {
        "source_full",
        "source_srt",
        "words_json",
        "target_srt",
        "source_voice",
        "background",
        "tts_dir",
        "target_voice",
        "final_mix",
        "final_video",
    }
    _STAGE_OUTPUTS = {
        "source_audio_extracted": ("source_full",),
        "source_transcribed": ("source_srt", "words_json"),
        "target_subtitles_ready": ("target_srt",),
        "source_voice_filtered": ("source_voice", "background"),
        "target_voice_segments_ready": ("tts_dir",),
        "target_voice_aligned": ("target_voice",),
        "final_mix_ready": ("final_mix",),
        "dubbed_video_ready": ("final_video",),
    }
    _STAGE_REQUIREMENTS = {
        "source_audio_extracted": (),
        "source_transcribed": ("source_full",),
        "target_subtitles_ready": ("source_srt",),
        "source_voice_filtered": ("source_full",),
        "target_voice_segments_ready": ("target_srt", "source_voice"),
        "target_voice_aligned": ("tts_dir",),
        "final_mix_ready": ("background", "target_voice"),
        "dubbed_video_ready": ("source_video", "final_mix"),
    }

    def __init__(self, tr, output_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self._tr = tr
        self._output_dir = output_dir
        self._paths = StagedExportPaths.from_output_dir(output_dir)
        self._manifest = self._read_manifest()
        self._artifact_overrides = self._read_artifact_overrides()
        self._paths = self._paths_with_overrides()
        self.setWindowTitle(self._tr("staged_export_stage_dialog_title"))
        self.resize(760, 540)

        layout = QVBoxLayout(self)
        intro = QLabel(self._tr("staged_export_stage_dialog_intro"), self)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel(self._tr("staged_export_preset"), self))
        self._preset_combo = QComboBox(self)
        self._add_presets()
        preset_row.addWidget(self._preset_combo, 1)
        self._refresh_button = QPushButton(self._tr("staged_export_check_artifacts"), self)
        self._open_folder_button = QPushButton(self._tr("staged_export_open_folder"), self)
        self._manifest_button = QPushButton(self._tr("staged_export_view_manifest"), self)
        preset_row.addWidget(self._refresh_button)
        preset_row.addWidget(self._open_folder_button)
        preset_row.addWidget(self._manifest_button)
        layout.addLayout(preset_row)

        body = QHBoxLayout()
        self._stage_list = QListWidget(self)
        self._stage_list.setMinimumWidth(300)
        body.addWidget(self._stage_list, 1)

        right = QVBoxLayout()
        form = QFormLayout()
        self._start_combo = QComboBox(self)
        self._end_combo = QComboBox(self)
        for stage in STAGED_EXPORT_STAGES:
            label = self._stage_label(stage)
            self._start_combo.addItem(label, stage)
            self._end_combo.addItem(label, stage)
        form.addRow(self._tr("staged_export_start_stage"), self._start_combo)
        form.addRow(self._tr("staged_export_end_stage"), self._end_combo)
        right.addLayout(form)

        self._force_check = QCheckBox(self._tr("staged_export_force_stage"), self)
        self._force_check.setChecked(True)
        self._force_hint = QLabel(self._tr("staged_export_force_stage_hint"), self)
        self._force_hint.setWordWrap(True)
        right.addWidget(self._force_check)
        right.addWidget(self._force_hint)

        self._tabs = QTabWidget(self)
        self._file_table = QTableWidget(0, 6, self)
        self._file_table.setHorizontalHeaderLabels(
            [
                self._tr("staged_export_file_role"),
                self._tr("staged_export_file_type"),
                self._tr("staged_export_file_path"),
                self._tr("staged_export_file_status"),
                self._tr("staged_export_file_choose"),
                self._tr("staged_export_file_open"),
            ]
        )
        self._file_table.verticalHeader().setVisible(False)
        self._file_table.setWordWrap(False)
        self._file_table.setColumnWidth(0, 120)
        self._file_table.setColumnWidth(1, 170)
        self._file_table.setColumnWidth(2, 360)
        self._file_table.setColumnWidth(3, 130)
        self._tabs.addTab(self._file_table, self._tr("staged_export_tab_files"))

        self._detail = QTextEdit(self)
        self._detail.setReadOnly(True)
        self._tabs.addTab(self._detail, self._tr("staged_export_tab_detail"))

        self._manifest_view = QTextEdit(self)
        self._manifest_view.setReadOnly(True)
        self._tabs.addTab(self._manifest_view, self._tr("staged_export_tab_manifest"))
        right.addWidget(self._tabs, 1)
        body.addLayout(right, 2)
        layout.addLayout(body, 1)

        self._buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        run_button = self._buttons.button(QDialogButtonBox.Ok)
        cancel_button = self._buttons.button(QDialogButtonBox.Cancel)
        if run_button is not None:
            run_button.setText(self._tr("staged_export_run"))
        if cancel_button is not None:
            cancel_button.setText(self._tr("cancel"))
        self._buttons.accepted.connect(self._accept_if_valid)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self._preset_combo.currentIndexChanged.connect(self._apply_selected_preset)
        self._start_combo.currentIndexChanged.connect(self._sync_from_combos)
        self._end_combo.currentIndexChanged.connect(self._sync_from_combos)
        self._stage_list.currentRowChanged.connect(self._update_detail_for_row)
        self._refresh_button.clicked.connect(self._refresh_artifacts)
        self._open_folder_button.clicked.connect(self._open_output_folder)
        self._manifest_button.clicked.connect(self._show_manifest)

        self._refresh_stage_list()
        self._preset_combo.setCurrentIndex(0)
        self._apply_selected_preset()

    def start_stage(self) -> str:
        return str(self._start_combo.currentData())

    def end_stage(self) -> str:
        return str(self._end_combo.currentData())

    def force_stage(self) -> bool:
        return self._force_check.isChecked()

    def artifact_overrides(self) -> dict[str, str]:
        return {key: str(path) for key, path in self._artifact_overrides.items()}

    def _add_presets(self) -> None:
        suggested_start, suggested_end, suggested_force = self._suggested_range()
        presets = [
            (
                self._tr("staged_export_preset_continue"),
                suggested_start,
                suggested_end,
                suggested_force,
            ),
            (
                self._tr("staged_export_preset_all"),
                STAGED_EXPORT_STAGES[0],
                STAGED_EXPORT_STAGES[-1],
                True,
            ),
            (
                self._tr("staged_export_preset_subtitles"),
                STAGED_EXPORT_STAGES[0],
                "target_subtitles_ready",
                True,
            ),
            (
                self._tr("staged_export_preset_voice"),
                "target_voice_segments_ready",
                "target_voice_aligned",
                True,
            ),
            (
                self._tr("staged_export_preset_mix_mp4"),
                "final_mix_ready",
                "dubbed_video_ready",
                True,
            ),
            (
                self._tr("staged_export_preset_mp4"),
                "dubbed_video_ready",
                "dubbed_video_ready",
                True,
            ),
        ]
        for label, start, end, force in presets:
            self._preset_combo.addItem(label, (start, end, force))

    def _suggested_range(self) -> tuple[str, str, bool]:
        for stage in STAGED_EXPORT_STAGES:
            status = self._stage_status(stage)
            if status in {"missing", "stale", "blocked", "partial"}:
                return stage, STAGED_EXPORT_STAGES[-1], True
        return "dubbed_video_ready", "dubbed_video_ready", True

    def _apply_selected_preset(self) -> None:
        data = self._preset_combo.currentData()
        if not isinstance(data, tuple) or len(data) != 3:
            return
        start, end, force = data
        self._set_stage_range(str(start), str(end))
        self._force_check.setChecked(bool(force))

    def _set_stage_range(self, start_stage: str, end_stage: str) -> None:
        self._start_combo.setCurrentIndex(max(0, STAGED_EXPORT_STAGES.index(start_stage)))
        self._end_combo.setCurrentIndex(max(0, STAGED_EXPORT_STAGES.index(end_stage)))
        self._sync_stage_selection()

    def _sync_from_combos(self) -> None:
        self._sync_stage_selection()

    def _sync_stage_selection(self) -> None:
        start_index = self._start_combo.currentIndex()
        end_index = self._end_combo.currentIndex()
        for row in range(self._stage_list.count()):
            item = self._stage_list.item(row)
            stage = str(item.data(32))
            stage_index = STAGED_EXPORT_STAGES.index(stage)
            selected = start_index <= stage_index <= end_index
            prefix = "> " if selected else "  "
            item.setText(prefix + self._stage_item_text(stage))
        if 0 <= start_index < self._stage_list.count():
            self._stage_list.setCurrentRow(start_index)

    def _refresh_artifacts(self) -> None:
        self._paths = StagedExportPaths.from_output_dir(self._output_dir)
        self._manifest = self._read_manifest()
        self._artifact_overrides = self._read_artifact_overrides()
        self._paths = self._paths_with_overrides()
        self._refresh_stage_list()
        self._sync_stage_selection()

    def _refresh_stage_list(self) -> None:
        self._stage_list.clear()
        for stage in STAGED_EXPORT_STAGES:
            item = QListWidgetItem(self._stage_item_text(stage))
            item.setData(32, stage)
            item.setToolTip(self._stage_detail_text(stage))
            self._stage_list.addItem(item)

    def _stage_item_text(self, stage: str) -> str:
        index = STAGED_EXPORT_STAGES.index(stage) + 1
        return f"{index}. {self._stage_label(stage)} - {self._status_label(self._stage_status(stage))}"

    def _stage_label(self, stage: str) -> str:
        label_key = STAGED_EXPORT_STAGE_LABEL_KEYS.get(stage, stage)
        return self._tr(label_key)

    def _stage_status(self, stage: str) -> str:
        manifest_stage = str(self._manifest.get("stage") or "")
        manifest_status = str(self._manifest.get("status") or "")
        if stage == manifest_stage and manifest_status in {"cancelled", "partial", "running"}:
            return "partial"
        requirements = self._paths_for_names(self._STAGE_REQUIREMENTS.get(stage, ()))
        outputs = self._paths_for_names(self._STAGE_OUTPUTS.get(stage, ()))
        if any(not self._artifact_ready(path) for path in requirements):
            return "blocked"
        if not outputs or any(not self._artifact_ready(path) for path in outputs):
            return "missing"
        if requirements and outputs:
            latest_input = max((path.stat().st_mtime for path in requirements if path.exists()), default=0.0)
            oldest_output = min((path.stat().st_mtime for path in outputs if path.exists()), default=0.0)
            if latest_input > oldest_output:
                return "stale"
        return "ready"

    def _status_label(self, status: str) -> str:
        return self._tr(f"staged_export_status_{status}")

    def _paths_for_names(self, names: tuple[str, ...]) -> list[Path]:
        return [self._artifact_path(name) for name in names]

    def _artifact_path(self, name: str) -> Path:
        override = self._artifact_overrides.get(name)
        if override is not None:
            return override
        if name == "source_video":
            return Path(str(self._manifest.get("source_video") or ""))
        return Path(getattr(self._paths, name))

    def _paths_with_overrides(self) -> StagedExportPaths:
        path_overrides = {
            key: path
            for key, path in self._artifact_overrides.items()
            if key != "source_video"
        }
        if not path_overrides:
            return self._paths
        return replace(self._paths, **path_overrides)

    def _artifact_ready(self, path: Path) -> bool:
        if path.is_dir():
            return any(child.name.endswith("-aligned.wav") for child in path.glob("*-aligned.wav"))
        return path.exists() and path.stat().st_size > 0

    def _update_detail_for_row(self, row: int) -> None:
        if row < 0:
            return
        item = self._stage_list.item(row)
        if item is None:
            return
        stage = str(item.data(32))
        self._detail.setPlainText(self._stage_detail_text(stage))
        self._refresh_file_table(stage)
        self._refresh_manifest_view()

    def _refresh_file_table(self, stage: str) -> None:
        rows = self._file_rows(stage)
        self._file_table.setRowCount(len(rows))
        for row, (role, artifact_name) in enumerate(rows):
            path = self._artifact_path(artifact_name)
            self._set_table_item(row, 0, role)
            self._set_table_item(row, 1, self._artifact_label(artifact_name))
            self._set_table_item(row, 2, str(path))
            self._set_table_item(row, 3, self._artifact_status_text(path))

            choose_button = QPushButton(self._tr("staged_export_file_choose"), self)
            choose_button.setEnabled(artifact_name in self._OVERRIDABLE_ARTIFACTS or artifact_name == "source_video")
            choose_button.clicked.connect(
                lambda _checked=False, name=artifact_name, file_role=role: self._choose_artifact(name, file_role)
            )
            self._file_table.setCellWidget(row, 4, choose_button)

            open_button = QPushButton(self._tr("staged_export_file_open"), self)
            open_button.setEnabled(bool(str(path)) and path.exists())
            open_button.clicked.connect(lambda _checked=False, selected=path: self._open_artifact(selected))
            self._file_table.setCellWidget(row, 5, open_button)

    def _set_table_item(self, row: int, column: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setToolTip(text)
        self._file_table.setItem(row, column, item)

    def _file_rows(self, stage: str) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        for name in self._STAGE_REQUIREMENTS.get(stage, ()):
            rows.append((self._tr("staged_export_file_input"), name))
        for name in self._STAGE_OUTPUTS.get(stage, ()):
            rows.append((self._tr("staged_export_file_output"), name))
        return rows

    def _artifact_label(self, name: str) -> str:
        return self._tr(self._ARTIFACT_LABEL_KEYS.get(name, name))

    def _artifact_status_text(self, path: Path) -> str:
        if self._artifact_ready(path):
            summary = self._artifact_summary(path)
            if summary:
                return f"{self._tr('staged_export_artifact_exists')} - {summary}"
            return self._tr("staged_export_artifact_exists")
        return self._tr("staged_export_artifact_missing")

    def _artifact_summary(self, path: Path) -> str:
        try:
            if path.is_dir():
                count = sum(1 for child in path.glob("*-aligned.wav"))
                return f"{count} aligned WAV"
            size = path.stat().st_size
        except OSError:
            return ""
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        if size >= 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size} B"

    def _choose_artifact(self, artifact_name: str, role: str) -> None:
        current = self._artifact_path(artifact_name)
        if artifact_name == "tts_dir":
            selected = QFileDialog.getExistingDirectory(
                self,
                self._artifact_label(artifact_name),
                str(current if current.exists() else self._output_dir),
            )
            if not selected:
                return
            self._set_artifact_override(artifact_name, Path(selected))
            return

        if role == self._tr("staged_export_file_output"):
            selected, _ = QFileDialog.getSaveFileName(
                self,
                self._artifact_label(artifact_name),
                str(current),
                self._ARTIFACT_FILTERS.get(artifact_name, "All files (*.*)"),
            )
        else:
            selected, _ = QFileDialog.getOpenFileName(
                self,
                self._artifact_label(artifact_name),
                str(current.parent if current.parent.exists() else self._output_dir),
                self._ARTIFACT_FILTERS.get(artifact_name, "All files (*.*)"),
            )
        if selected:
            self._set_artifact_override(artifact_name, Path(selected))

    def _set_artifact_override(self, artifact_name: str, path: Path) -> None:
        self._artifact_overrides[artifact_name] = path
        self._paths = StagedExportPaths.from_output_dir(self._output_dir)
        self._paths = self._paths_with_overrides()
        self._refresh_stage_list()
        self._sync_stage_selection()

    def _open_artifact(self, path: Path) -> None:
        target = path if path.exists() else path.parent
        if target:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _stage_detail_text(self, stage: str) -> str:
        lines = [
            self._stage_label(stage),
            f"{self._tr('staged_export_detail_status')}: {self._status_label(self._stage_status(stage))}",
            "",
            self._tr("staged_export_detail_requires"),
            *self._artifact_lines(self._paths_for_names(self._STAGE_REQUIREMENTS.get(stage, ()))),
            "",
            self._tr("staged_export_detail_outputs"),
            *self._artifact_lines(self._paths_for_names(self._STAGE_OUTPUTS.get(stage, ()))),
        ]
        if self._manifest:
            lines.extend(
                [
                    "",
                    self._tr("staged_export_detail_manifest"),
                    f"{self._tr('staged_export_detail_manifest_status')}: {self._manifest.get('status', '')}",
                    f"{self._tr('staged_export_detail_manifest_stage')}: {self._manifest.get('stage', '')}",
                ]
            )
        return "\n".join(lines)

    def _artifact_lines(self, paths: list[Path]) -> list[str]:
        if not paths:
            return [f"- {self._tr('staged_export_detail_none')}"]
        lines: list[str] = []
        for path in paths:
            state = self._tr("staged_export_artifact_exists") if self._artifact_ready(path) else self._tr(
                "staged_export_artifact_missing"
            )
            lines.append(f"- {state}: {path}")
        return lines

    def _show_manifest(self) -> None:
        self._refresh_manifest_view()
        self._tabs.setCurrentWidget(self._manifest_view)

    def _refresh_manifest_view(self) -> None:
        if not self._paths.manifest.exists():
            self._manifest_view.setPlainText(self._tr("staged_export_manifest_missing"))
            return
        try:
            self._manifest_view.setPlainText(self._paths.manifest.read_text(encoding="utf-8"))
        except OSError as exc:
            self._manifest_view.setPlainText(str(exc))

    def _open_output_folder(self) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._output_dir)))

    def _read_manifest(self) -> dict[str, object]:
        try:
            data = json.loads(self._paths.manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _read_artifact_overrides(self) -> dict[str, Path]:
        raw = self._manifest.get("artifact_overrides")
        if not isinstance(raw, dict):
            return {}
        overrides: dict[str, Path] = {}
        for key, value in raw.items():
            if key in self._OVERRIDABLE_ARTIFACTS or key == "source_video":
                text = str(value or "").strip()
                if text:
                    overrides[key] = Path(text)
        return overrides

    def _accept_if_valid(self) -> None:
        start_index = self._start_combo.currentIndex()
        end_index = self._end_combo.currentIndex()
        if start_index > end_index:
            QMessageBox.warning(self, self.windowTitle(), self._tr("staged_export_stage_invalid"))
            return
        self.accept()


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
