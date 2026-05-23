from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ai_player.core.config import AppConfig
from ai_player.workers import meeting_worker
from ai_player.workers.dubbing_worker import DubbingWorker
from ai_player.workers.export_worker import DubbingExportWorker
from ai_player.workers.meeting_worker import MeetingWorker


class FakeWhisperModel:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def transcribe(self, audio_path: str, **kwargs):
        self.calls.append({"audio_path": audio_path, **kwargs})
        return [], SimpleNamespace(language=kwargs.get("language"))


def test_dubbing_worker_uses_configured_asr_options() -> None:
    model = FakeWhisperModel()
    worker = SimpleNamespace(
        _config=AppConfig(whisper_beam_size=4, whisper_vad_filter=False, source_language="vi"),
        _model=model,
        _load_whisper_model=lambda: model,
        _selected_whisper_language=lambda: "vi",
    )

    DubbingWorker._transcribe_with_fallback(worker, Path("sample.wav"))

    assert model.calls == [{"audio_path": "sample.wav", "beam_size": 4, "vad_filter": False, "language": "vi"}]


def test_export_worker_uses_configured_asr_options() -> None:
    model = FakeWhisperModel()
    worker = SimpleNamespace(
        _config=AppConfig(whisper_beam_size=3, whisper_vad_filter=True, source_language="en"),
        _load_whisper_model=lambda: model,
        _selected_whisper_language=lambda: "en",
    )

    DubbingExportWorker._transcribe_with_fallback(worker, Path("source.wav"))

    assert model.calls == [{"audio_path": "source.wav", "beam_size": 3, "vad_filter": True, "language": "en"}]


def test_meeting_worker_uses_configured_asr_options() -> None:
    model = FakeWhisperModel()
    worker = SimpleNamespace(
        _config=AppConfig(whisper_beam_size=2, whisper_vad_filter=False, source_language="auto"),
        _model=model,
        _load_model=lambda: model,
        _selected_whisper_language=lambda: None,
    )

    MeetingWorker._transcribe_segments(worker, Path("meeting.wav"))

    assert model.calls == [{"audio_path": "meeting.wav", "beam_size": 2, "vad_filter": False, "language": None}]


def test_meeting_worker_sanitizes_segment_text_language_and_timing(tmp_path) -> None:
    ready_segments: list[tuple[str, str]] = []
    translated_calls: list[tuple[str, str | None]] = []
    worker = SimpleNamespace(
        _config=AppConfig(tts_provider="none"),
        _transcript_cleaner=SimpleNamespace(clean=lambda text, _language: text),
        _transcribe_segments=lambda _audio_path: (
            [SimpleNamespace(text=b" hello   world ", start=float("inf"), end=float("nan"))],
            SimpleNamespace(language=b"EN"),
        ),
        _translate=lambda text, language: translated_calls.append((text, language)) or "xin chao",
        segment_ready=SimpleNamespace(emit=lambda original, translated: ready_segments.append((original, translated))),
        _tr=lambda key: {"transcript_label_source": "Source", "transcript_label_target": "Target"}[key],
    )
    worker._transcript_line = lambda start, end, source, target: MeetingWorker._transcript_line(
        worker, start, end, source, target
    )

    lines = MeetingWorker._process_chunk(worker, Path("meeting.wav"), float("inf"), tmp_path, 0)

    assert translated_calls == [("hello world", "en")]
    assert ready_segments == [("hello world", "xin chao")]
    assert lines == ["[00:00:00 - 00:00:00]\nSource: hello world\nTarget: xin chao"]
    assert meeting_worker._format_elapsed(float("inf")) == "00:00:00"
    assert meeting_worker._format_timestamp(float("nan")) == "00:00:00"
