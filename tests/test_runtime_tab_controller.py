from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import QLabel, QPushButton

from ai_player.ui.player_window_state import RuntimeStatusState
from ai_player.ui.runtime_tab_controller import RuntimeTabController


class _FakeOwner:
    _document_mode = False
    _document_pages = []
    _document_duration_ms = 0
    _runtime_warmup = None
    _video_url = None
    _provider_preview = None

    def __init__(self) -> None:
        self._video_path = ""
        self._settings_tabs = None
        self._whisper_beam_slider = SimpleNamespace(value=lambda: 1)
        self._status_bar = SimpleNamespace(showMessage=lambda _message: None)

    def _tr(self, key: str) -> str:
        translations = {
            "runtime_unavailable": "Unavailable",
            "runtime_unknown": "Unknown",
            "status_no_video": "No video",
            "runtime_stream_source": "Stream: {source}",
            "runtime_folder": "Folder: {folder}",
            "runtime_container": "Container: {container}",
            "runtime_size": "Size: {size}",
            "runtime_duration": "Duration: {duration}",
            "runtime_total_bitrate": "Total bitrate: {bitrate}",
            "runtime_video_codec": "Video: {codec}",
            "runtime_resolution": "Resolution: {width}x{height}",
            "runtime_pixel_format": "Pixel: {format}",
            "runtime_video_bitrate": "Video bitrate: {bitrate}",
            "runtime_audio_stream": "Audio {index}: {codec} {rate} {channels} {bitrate}",
            "runtime_no_audio_stream": "No audio",
            "runtime_no_video_stream": "No video stream",
            "runtime_subtitle_streams": "Subtitles: {count}",
        }
        return translations.get(key, key)

    def _format_bytes(self, value) -> str:
        return f"{value} B"

    @staticmethod
    def _format_seconds(value) -> str:
        return f"{float(value):.1f}s"

    @staticmethod
    def _selected_whisper_device() -> str:
        return "cpu"

    @staticmethod
    def _selected_whisper_compute() -> str:
        return "int8"

    @staticmethod
    def _selected_translation_device() -> str:
        return "cpu"

    @staticmethod
    def _selected_vieneu_device() -> str:
        return "cpu"

    def _current_runtime_config(self):
        return SimpleNamespace()

    @staticmethod
    def _settings_tab_contains(_tab, _content) -> bool:
        return False

    def statusBar(self):
        return self._status_bar


def test_runtime_tab_controller_caches_empty_media_text() -> None:
    state = RuntimeStatusState(media_info_text="old")
    controller = RuntimeTabController(_FakeOwner(), state)

    assert controller.media_info_text_current() == "No video"
    assert state.media_info_path == ""
    assert state.media_info_text == "No video"


def test_runtime_tab_controller_formats_stream_media_without_probe() -> None:
    state = RuntimeStatusState()
    controller = RuntimeTabController(_FakeOwner(), state)

    assert controller.media_info_text_current(force=True) == "No video"
    state.media_path = "https://example.test/video.mp4"

    assert controller.media_info_text_current() == "Stream: https://example.test/video.mp4"
    assert state.media_info_path == "https://example.test/video.mp4"


def test_runtime_tab_controller_refresh_updates_bound_labels(qapp, monkeypatch) -> None:
    owner = _FakeOwner()
    state = RuntimeStatusState(last_wall=1.0, last_process=1.0, gpu_text="GPU old")
    controller = RuntimeTabController(owner, state)
    labels = {
        key: QLabel("")
        for key in (
            "health",
            "privacy",
            "tasks",
            "media",
            "gpu_runtime",
            "process_cpu",
            "process_memory",
            "system_cpu",
            "system_memory",
            "gpu",
            "python",
            "platform",
            "pid",
            "diagnostics",
        )
    }
    button = QPushButton()
    controller.bind(labels=labels, stop_tasks_button=button, tab_widget=QLabel())
    monkeypatch.setattr("ai_player.ui.runtime_tab_controller.time.perf_counter", lambda: 3.0)
    monkeypatch.setattr("ai_player.ui.runtime_tab_controller.time.process_time", lambda: 2.0)
    monkeypatch.setattr("ai_player.ui.runtime_tab_controller.os.cpu_count", lambda: 2)
    monkeypatch.setattr(controller, "system_cpu_percent", lambda: 25.0)
    monkeypatch.setattr(controller, "process_memory_bytes", lambda: 2048)
    monkeypatch.setattr(controller, "system_memory", lambda: (1024, 4096, 25.0))
    monkeypatch.setattr(controller, "media_info_text_current", lambda: "Media ready")
    monkeypatch.setattr(controller, "health_summary", lambda: "Health ready")
    monkeypatch.setattr(controller, "privacy_summary", lambda: "Privacy ready")
    monkeypatch.setattr(controller, "task_summary", lambda tasks=None: "Idle")
    monkeypatch.setattr(controller, "gpu_runtime_text", lambda: "Runtime GPU")

    controller.refresh()

    assert labels["process_cpu"].text() == "25.0%"
    assert labels["process_memory"].text() == "2048 B"
    assert labels["system_cpu"].text() == "25.0%"
    assert labels["system_memory"].text() == "1024 B / 4096 B (25.0%)"
    assert labels["media"].text() == "Media ready"
    assert labels["health"].text() == "Health ready"
    assert labels["privacy"].text() == "Privacy ready"
    assert labels["tasks"].text() == "Idle"
    assert labels["gpu_runtime"].text() == "Runtime GPU"
    assert labels["gpu"].text() == "GPU old"
    assert not button.isEnabled()
