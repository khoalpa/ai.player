from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox, QStyle

from ai_player.ui.player_window_utils import repair_mojibake as _repair_mojibake
from ai_player.workers.meeting_worker import MeetingResult, MeetingWorker


class PlayerMeetingMixin:
    def _toggle_meeting(self) -> None:
        if self._meeting_worker is not None:
            self._finish_meeting()
        else:
            self._start_meeting()

    def _start_meeting(self) -> None:
        if self._meeting_worker is not None:
            return
        self._save_settings()
        self._stop_dubbing()
        self._player.stop()
        self._set_document_mode(False)
        self._document_editor_active = False
        self._video_path = None
        self._media_stack.setCurrentWidget(self._document_view)
        self._document_view.setReadOnly(True)
        self._document_view.setPlainText(self._tr("meeting_recording_text"))
        self._clear_transcript()
        self._source_label.setText(self._tr("meeting_source_label"))
        self._set_combo_data(self._audio_source_combo, "system_microphone")
        self._subtitle_mode_combo.setCurrentIndex(max(0, self._subtitle_mode_combo.findData("target")))
        output_dir = Path.home() / "Documents" / "AI Player Meetings"
        self._meeting_worker = MeetingWorker(output_dir, self._current_runtime_config(), self)
        self._meeting_worker.status_changed.connect(self._meeting_status_changed)
        self._meeting_worker.elapsed_changed.connect(self._meeting_elapsed_changed)
        self._meeting_worker.segment_ready.connect(self._append_segment)
        self._meeting_worker.finished_successfully.connect(self._meeting_finished)
        self._meeting_worker.failed.connect(self._meeting_failed)
        self._meeting_button.setText(self._tr("meeting_stop_label"))
        self._meeting_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self._meeting_worker.start()
        self.statusBar().showMessage(self._tr("status_meeting_recording"))

    def _finish_meeting(self) -> None:
        worker = self._meeting_worker
        if worker is None:
            return
        self._meeting_button.setEnabled(False)
        self.statusBar().showMessage(self._tr("status_meeting_finishing"))
        self._document_view.setPlainText(self._tr("meeting_finishing_text").format(elapsed=self._meeting_elapsed))
        worker.stop()

    def _stop_meeting(self, wait_ms: int = 5000) -> bool:
        worker = self._meeting_worker
        if worker is None:
            return True
        worker.stop()
        if not worker.wait(wait_ms):
            return False
        worker.deleteLater()
        self._meeting_worker = None
        if hasattr(self, "_meeting_button"):
            self._reset_meeting_button()
        return True

    def _meeting_status_changed(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def _meeting_elapsed_changed(self, elapsed: str) -> None:
        self._meeting_elapsed = elapsed
        if (
            self._meeting_worker is not None
            and self._meeting_button.isEnabled()
            and not self._live_subtitle_source_text
            and not self._live_subtitle_target_text
        ):
            self._document_view.setPlainText(self._tr("meeting_recording_elapsed_text").format(elapsed=elapsed))

    def _meeting_finished(self, result: MeetingResult) -> None:
        worker = self._meeting_worker
        self._meeting_worker = None
        if worker is not None:
            worker.deleteLater()
        self._reset_meeting_button()
        text = _repair_mojibake(result.transcript_text.strip())
        self._set_transcript_text(text)
        self._document_view.setPlainText(text)
        self._source_label.setText(f"Meeting: {result.started_at.strftime('%Y%m%d-%H%M%S')}")
        self.statusBar().showMessage(
            self._tr("status_meeting_exported").format(
                transcript_path=result.transcript_path,
                audio_path=result.audio_path,
            )
        )

    def _meeting_failed(self, message: str) -> None:
        worker = self._meeting_worker
        self._meeting_worker = None
        if worker is not None:
            worker.deleteLater()
        self._reset_meeting_button()
        QMessageBox.warning(self, "Meeting", _repair_mojibake(message))
        self.statusBar().showMessage(self._tr("status_meeting_failed"))

    def _reset_meeting_button(self) -> None:
        self._meeting_button.setEnabled(True)
        self._meeting_button.setText(self._tr("meeting_start_label"))
        self._meeting_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
