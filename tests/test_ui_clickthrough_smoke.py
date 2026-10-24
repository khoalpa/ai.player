from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from ai_player.ui.features.channel_browser import PlayerChannelBrowserFeature
from ai_player.ui.features.channel_flow import PlayerChannelFlowFeature
from ai_player.ui.features.media import PlayerMediaFeature
from ai_player.ui.features.runtime import PlayerRuntimeFeature
from ai_player.ui.features.sources import PlayerSourceFeature
from ai_player.ui.player_window import PlayerWindow


@pytest.fixture(autouse=True)
def disable_clickthrough_background_startups(monkeypatch) -> None:
    monkeypatch.setattr(PlayerRuntimeFeature, "_start_runtime_warmup", lambda self: None)
    monkeypatch.setattr(PlayerChannelFlowFeature, "_start_telegram_worker", lambda self, *args, **kwargs: None)


class _Signal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback, *_connection_options) -> None:
        self._callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in list(self._callbacks):
            callback(*args)


class _FakeDubbingWorker:
    started_paths: list[str] = []
    stopped_count = 0
    deleted_count = 0

    def __init__(self, video_path, _get_time_ms, _is_playing, config, source_http_headers=None, parent=None) -> None:
        self.video_path = str(video_path)
        self.config = config
        self.source_http_headers = source_http_headers or {}
        self.parent = parent
        self.status_changed = _Signal()
        self.segment_ready = _Signal()
        self.subtitle_ready = _Signal()
        self.audio_started = _Signal()
        self.playback_pause_requested = _Signal()
        self.playback_resume_requested = _Signal()
        self.failed = _Signal()
        self.finished = _Signal()
        self._running = False

    def start(self) -> None:
        self._running = True
        self.started_paths.append(self.video_path)
        self.status_changed.emit("Mock dubbing started")

    def stop(self) -> None:
        if self._running:
            type(self).stopped_count += 1
        self._running = False

    def wait(self, _timeout_ms: int) -> bool:
        return True

    def isRunning(self) -> bool:
        return self._running

    def deleteLater(self) -> None:
        type(self).deleted_count += 1


def test_source_ui_clickthrough_smoke_video_transcript_document_preset_and_dubbing(
    qapp,
    tmp_path,
    monkeypatch,
) -> None:
    sample_video = Path("samples/demo-video.mp4").resolve()
    if not sample_video.exists():
        pytest.skip("sample video is not available")
    transcript_path = tmp_path / "clickthrough.srt"
    transcript_path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nHello from click-through smoke.\n",
        encoding="utf-8",
    )
    document_path = tmp_path / "clickthrough.md"
    document_path.write_text("Small document for click-through smoke.", encoding="utf-8")

    open_file_results = iter([(str(sample_video), ""), (str(transcript_path), ""), (str(document_path), "")])
    loaded_documents: list[str] = []
    loaded_videos: list[str | None] = []
    shown_video = []

    monkeypatch.setattr(
        "ai_player.ui.features.sources.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: next(open_file_results),
    )
    monkeypatch.setattr("ai_player.ui.features.dubbing.DubbingWorker", _FakeDubbingWorker)
    monkeypatch.setattr(PlayerMediaFeature, "_auto_select_video_aspect_ratio", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(
        PlayerMediaFeature,
        "_load_current_video_for_playback",
        lambda self: loaded_videos.append(self.context.channel_browser._video_path),
    )
    monkeypatch.setattr(PlayerChannelBrowserFeature, "_show_video_output", lambda self: shown_video.append(True))
    monkeypatch.setattr(
        PlayerSourceFeature,
        "_load_document",
        lambda self, path, start_dubbing=True: loaded_documents.append(path),
    )

    _FakeDubbingWorker.started_paths = []
    _FakeDubbingWorker.stopped_count = 0
    _FakeDubbingWorker.deleted_count = 0
    window = PlayerWindow()
    try:
        window.show()
        qapp.processEvents()

        QTest.mouseClick(window.features.layout._open_file_button, Qt.MouseButton.LeftButton)
        qapp.processEvents()

        assert loaded_videos == [str(sample_video)]
        assert shown_video == [True]
        assert window.features.channel_browser._video_path == str(sample_video)
        assert window.features.layout._source_label.text() == str(sample_video)

        window.features.settings._set_combo_data(window.features.layout._audio_source_combo, "transcript")
        qapp.processEvents()
        QTest.mouseClick(window.features.layout._transcript_file_button, Qt.MouseButton.LeftButton)
        qapp.processEvents()

        assert window.features.settings._selected_audio_source() == "transcript"
        assert window.features.layout._transcript_path_edit.text() == str(transcript_path)

        window.features.settings._set_combo_data(window.features.layout._performance_preset_combo, "offline_lite")
        window.features.settings._apply_selected_performance_preset()
        qapp.processEvents()

        assert window.features.settings._current_runtime_config().performance_preset == "offline_lite"

        window.features.settings._set_combo_data(window.features.layout._audio_source_combo, "transcript")
        window.features.layout._transcript_path_edit.setText(str(transcript_path))
        QTest.mouseClick(window.features.layout._dub_button, Qt.MouseButton.LeftButton)
        qapp.processEvents()

        assert _FakeDubbingWorker.started_paths == [str(sample_video)]
        assert window.features.lifecycle.workers.dubbing_worker is not None
        assert window.features.layout._dub_button.isChecked()
        assert window.statusBar().currentMessage() == window.features.settings._tr("status_dubbing_starting")

        QTest.mouseClick(window.features.layout._dub_button, Qt.MouseButton.LeftButton)
        qapp.processEvents()

        assert window.features.lifecycle.workers.dubbing_worker is None
        assert not window.features.layout._dub_button.isChecked()
        assert _FakeDubbingWorker.stopped_count == 1
        assert _FakeDubbingWorker.deleted_count == 1

        QTest.mouseClick(window.features.layout._start_dubbing_button, Qt.MouseButton.LeftButton)
        qapp.processEvents()

        assert _FakeDubbingWorker.started_paths == [str(sample_video), str(sample_video)]
        assert window.features.lifecycle.workers.dubbing_worker is not None
        assert window.features.layout._dub_button.isChecked()

        QTest.mouseClick(window.features.layout._open_document_button, Qt.MouseButton.LeftButton)
        qapp.processEvents()

        assert loaded_documents == [str(document_path)]
        window.features.layout._settings_save_timer.stop()
    finally:
        if window.features.lifecycle.workers.dubbing_worker is not None:
            window.features.lifecycle.workers.dubbing_worker.stop()
            window.features.lifecycle.workers.dubbing_worker.wait(5000)
            window.features.lifecycle.workers.dubbing_worker = None
        window.close()
