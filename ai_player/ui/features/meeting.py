from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox, QStyle

from ai_player.application.workflows.meeting import MeetingResult
from ai_player.ui.features.base import Feature
from ai_player.ui.player_window_utils import repair_mojibake as _repair_mojibake
from ai_player.workers.meeting_worker import MeetingWorker


class PlayerMeetingFeature(Feature):
    def _toggle_meeting(self) -> None:
        if self.context.lifecycle.workers.meeting_worker is not None:
            self.context.meeting._finish_meeting()
        else:
            self.context.meeting._start_meeting()

    def _start_meeting(self) -> None:
        if self.context.lifecycle.workers.meeting_worker is not None:
            return
        self.context.settings._save_settings()
        self.context.dubbing._stop_dubbing()
        self.context.layout._player.stop()
        self.context.media._set_document_mode(False)
        self.context.media.document.editor_active = False
        self.context.channel_browser._video_path = None
        self.context.channel_browser._video_source_http_headers = {}
        self.context.layout._media_stack.setCurrentWidget(self.context.layout._document_view)
        self.context.layout._document_view.setReadOnly(True)
        self.context.layout._document_view.setPlainText(self.context.settings._tr("meeting_recording_text"))
        self.context.transcript._clear_transcript()
        self.context.layout._source_label.setText(self.context.settings._tr("meeting_source_label"))
        self.context.settings._set_combo_data(self.context.layout._audio_source_combo, "system_microphone")
        self.context.layout._subtitle_mode_combo.setCurrentIndex(
            max(0, self.context.layout._subtitle_mode_combo.findData("target"))
        )
        output_dir = Path.home() / "Documents" / "AI Player Meetings"
        self.context.lifecycle.workers.meeting_worker = MeetingWorker(
            output_dir, self.context.settings._current_runtime_config(), self.context.window
        )
        self.context.lifecycle.workers.meeting_worker.status_changed.connect(
            self.context.meeting._meeting_status_changed
        )
        self.context.lifecycle.workers.meeting_worker.elapsed_changed.connect(
            self.context.meeting._meeting_elapsed_changed
        )
        self.context.lifecycle.workers.meeting_worker.segment_ready.connect(self.context.transcript._append_segment)
        self.context.lifecycle.workers.meeting_worker.finished_successfully.connect(
            self.context.meeting._meeting_finished
        )
        self.context.lifecycle.workers.meeting_worker.failed.connect(self.context.meeting._meeting_failed)
        self.context.layout._meeting_button.setText(self.context.settings._tr("meeting_stop_label"))
        self.context.layout._meeting_button.setIcon(self.context.ui._app_icon(QStyle.StandardPixmap.SP_MediaStop))
        self.context.lifecycle.workers.meeting_worker.start()
        self.context.window.statusBar().showMessage(self.context.settings._tr("status_meeting_recording"))

    def _finish_meeting(self) -> None:
        worker = self.context.lifecycle.workers.meeting_worker
        if worker is None:
            return
        self.context.layout._meeting_button.setEnabled(False)
        self.context.window.statusBar().showMessage(self.context.settings._tr("status_meeting_finishing"))
        self.context.layout._document_view.setPlainText(
            self.context.settings._tr("meeting_finishing_text").format(
                elapsed=self.context.lifecycle.workers.meeting_elapsed
            )
        )
        worker.stop()

    def _stop_meeting(self, wait_ms: int = 5000) -> bool:
        worker = self.context.lifecycle.workers.meeting_worker
        if worker is None:
            return True
        worker.stop()
        if not worker.wait(wait_ms):
            return False
        worker.deleteLater()
        self.context.lifecycle.workers.meeting_worker = None
        if self.context.has("_meeting_button"):
            self.context.meeting._reset_meeting_button()
        return True

    def _meeting_status_changed(self, message: str) -> None:
        self.context.window.statusBar().showMessage(message)

    def _meeting_elapsed_changed(self, elapsed: str) -> None:
        self.context.lifecycle.workers.meeting_elapsed = elapsed
        if (
            self.context.lifecycle.workers.meeting_worker is not None
            and self.context.layout._meeting_button.isEnabled()
            and not self.context.transcript.state.live_source_text
            and not self.context.transcript.state.live_target_text
        ):
            self.context.layout._document_view.setPlainText(
                self.context.settings._tr("meeting_recording_elapsed_text").format(elapsed=elapsed)
            )

    def _meeting_finished(self, result: MeetingResult) -> None:
        worker = self.context.lifecycle.workers.meeting_worker
        self.context.lifecycle.workers.meeting_worker = None
        if worker is not None:
            worker.deleteLater()
        self.context.meeting._reset_meeting_button()
        text = _repair_mojibake(result.transcript_text.strip())
        self.context.transcript._set_transcript_text(text)
        self.context.layout._document_view.setPlainText(text)
        self.context.layout._source_label.setText(
            self.context.settings._tr("meeting_result_label").format(
                started_at=result.started_at.strftime("%Y%m%d-%H%M%S")
            )
        )
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("status_meeting_exported").format(
                transcript_path=result.transcript_path,
                audio_path=result.audio_path,
            )
        )

    def _meeting_failed(self, message: str) -> None:
        worker = self.context.lifecycle.workers.meeting_worker
        self.context.lifecycle.workers.meeting_worker = None
        if worker is not None:
            worker.deleteLater()
        self.context.meeting._reset_meeting_button()
        QMessageBox.warning(
            self.context.window, self.context.settings._tr("meeting_dialog_title"), _repair_mojibake(message)
        )
        self.context.window.statusBar().showMessage(self.context.settings._tr("status_meeting_failed"))

    def _reset_meeting_button(self) -> None:
        self.context.layout._meeting_button.setEnabled(True)
        self.context.layout._meeting_button.setText(self.context.settings._tr("meeting_start_label"))
        self.context.layout._meeting_button.setIcon(self.context.ui._app_icon(QStyle.StandardPixmap.SP_MediaPlay))
