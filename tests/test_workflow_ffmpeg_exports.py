from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_player.core.config import AppConfig
from ai_player.workers import export_worker
from ai_player.workers.dubbing_worker import DubbingWorker, _segment_start_key


@pytest.mark.parametrize(
    ("quality", "crf", "copy"),
    [
        ("compact", 28, False),
        ("balanced", 23, False),
        ("high", 18, False),
        ("archival", 16, False),
        ("source", 18, False),
    ],
)
def test_video_quality_settings(quality: str, crf: int, copy: bool) -> None:
    settings = export_worker._video_quality_settings(quality)

    assert settings.crf == crf
    assert settings.copy_source_video is copy


@pytest.mark.parametrize(
    ("func", "needle"),
    [
        (export_worker._scale_filter, "force_original_aspect_ratio=decrease"),
        (export_worker._document_scale_filter, "pad="),
    ],
)
def test_scale_filters_contain_expected_operations(func, needle: str) -> None:
    assert needle in func(1280, 720)


@pytest.mark.parametrize(("value", "seconds"), [("00:00:01,500", 1.5), ("01:02:03.004", 3723.004)])
def test_parse_srt_time(value: str, seconds: float) -> None:
    assert export_worker._parse_srt_time(value) == seconds


def test_read_srt_cues_parses_multiline_text(tmp_path) -> None:
    path = tmp_path / "demo.srt"
    path.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello\nworld\n\n", encoding="utf-8")

    cues = export_worker._read_srt_cues(path)

    assert cues == [export_worker.TranscriptCue(0.0, 2.0, "Hello world")]


def test_export_range_filters_and_shifts_transcript_cues(monkeypatch, tmp_path) -> None:
    transcript = tmp_path / "demo.srt"
    transcript.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nskip\n\n"
        "2\n00:00:05,000 --> 00:00:07,000\nkeep\n\n",
        encoding="utf-8",
    )
    config = AppConfig(audio_source="transcript", transcript_path=str(transcript), tts_provider="none")
    worker = export_worker.DubbingExportWorker(
        "video.mp4",
        str(tmp_path / "out.mp4"),
        "video",
        config,
        export_worker.ExportRange(4.0, 8.0),
    )
    worker._temp_dir = tmp_path
    worker._translator = SimpleNamespace(translate_many=lambda texts, _language: [f"{text}-vi" for text in texts])
    monkeypatch.setattr(export_worker, "_export_worker_count", lambda: 1)

    cues = worker._build_transcript_cues()

    assert [cue.original for cue in cues] == ["keep"]
    assert cues[0].start_seconds == 1.0


def test_video_mux_applies_export_range(tmp_path) -> None:
    config = AppConfig(export_video_quality="balanced")
    worker = export_worker.DubbingExportWorker(
        "video.mp4",
        str(tmp_path / "out.mp4"),
        "video",
        config,
        export_worker.ExportRange(10.0, 15.5),
    )
    captured: dict[str, list[object]] = {}
    worker._run_ffmpeg = lambda args, **_kwargs: captured.setdefault("args", args)

    worker._mux_video(tmp_path / "dubbed.wav")

    args = captured["args"]
    assert args[:4] == ["-ss", "10.000", "-i", "video.mp4"]
    assert args[args.index("-t") + 1] == "5.500"


def test_source_export_voice_selector_runs_before_parallel_cue_build(monkeypatch, tmp_path) -> None:
    config = AppConfig(dubbing_auto_voice_gender=True, dubbing_auto_voice_gender_mode="stable")
    worker = export_worker.DubbingExportWorker("video.mp4", str(tmp_path / "out.wav"), "audio", config)
    worker._temp_dir = tmp_path
    worker._translator = SimpleNamespace(translate_many=lambda texts, _language: [f"{text}-vi" for text in texts])
    worker._transcript_cleaner = SimpleNamespace(clean=lambda text, _language: text)
    worker._transcribe_with_fallback = lambda _source_audio: (
        [
            SimpleNamespace(text="first", start=0.0, end=1.0),
            SimpleNamespace(text="second", start=1.0, end=2.0),
        ],
        SimpleNamespace(language="en"),
    )
    calls: list[str] = []

    def fake_extract(_source_audio, _start, _duration, reference_path: Path, **_kwargs) -> None:
        reference_path.write_bytes(b"ref")

    class FakeSelector:
        def select_voice(self, reference_path: Path, *, provider: str, config: AppConfig):
            calls.append(reference_path.stem)
            return SimpleNamespace(voice=f"voice-{reference_path.stem}")

    def fake_build(index, original, translated, start_seconds, duration_seconds, reference_path, voice, tts_suffix):
        return export_worker.ExportCue(
            start_seconds=start_seconds,
            original=original,
            translated=translated,
            audio_path=reference_path,
            duration_seconds=duration_seconds,
        )

    monkeypatch.setattr(export_worker, "extract_audio_range", fake_extract)
    monkeypatch.setattr(export_worker, "_export_worker_count", lambda: 2)
    worker._voice_selector = FakeSelector()
    worker._build_source_export_cue = fake_build

    cues = worker._build_cues(tmp_path / "source.wav")

    assert calls == ["cue-00000-ref", "cue-00001-ref"]
    assert [cue.original for cue in cues] == ["first", "second"]


def test_source_export_skips_reference_extract_when_unused(monkeypatch, tmp_path) -> None:
    config = AppConfig(
        dubbing_auto_match_audio=False,
        dubbing_auto_voice_gender=False,
        tts_provider="vieneu",
    )
    worker = export_worker.DubbingExportWorker("video.mp4", str(tmp_path / "out.wav"), "audio", config)
    worker._temp_dir = tmp_path
    worker._translator = SimpleNamespace(translate_many=lambda texts, _language: [f"{text}-vi" for text in texts])
    worker._transcript_cleaner = SimpleNamespace(clean=lambda text, _language: text)
    worker._transcribe_with_fallback = lambda _source_audio: (
        [SimpleNamespace(text="first", start=0.0, end=1.0)],
        SimpleNamespace(language="en"),
    )
    source_audio = tmp_path / "source.wav"
    seen_references: list[Path] = []

    def fail_extract(*_args, **_kwargs) -> None:
        raise AssertionError("reference audio should not be extracted")

    def fake_build(index, original, translated, start_seconds, duration_seconds, reference_path, voice, tts_suffix):
        seen_references.append(reference_path)
        return export_worker.ExportCue(
            start_seconds=start_seconds,
            original=original,
            translated=translated,
            audio_path=reference_path,
            duration_seconds=duration_seconds,
        )

    monkeypatch.setattr(export_worker, "extract_audio_range", fail_extract)
    monkeypatch.setattr(export_worker, "_export_worker_count", lambda: 1)
    worker._build_source_export_cue = fake_build

    cues = worker._build_cues(source_audio)

    assert seen_references == [source_audio]
    assert [cue.original for cue in cues] == ["first"]


def test_export_aligned_audio_mixes_cues_at_source_starts(tmp_path) -> None:
    config = AppConfig(dubbing_overlap_policy="strict_start")
    worker = export_worker.DubbingExportWorker("video.mp4", str(tmp_path / "out.wav"), "audio", config)
    worker._temp_dir = tmp_path
    captured: dict[str, list[object]] = {}
    source_a = tmp_path / "a.wav"
    source_b = tmp_path / "b.wav"
    source_a.write_bytes(b"a")
    source_b.write_bytes(b"b")

    def fake_to_wav(_input_path: Path, output_path: Path) -> None:
        output_path.write_bytes(b"wav")

    worker._to_wav = fake_to_wav
    worker._run_ffmpeg = lambda args, **_kwargs: captured.setdefault("args", args)

    worker._build_aligned_audio(
        [
            export_worker.ExportCue(0.0, "first", "mot", source_a, duration_seconds=3.0),
            export_worker.ExportCue(1.0, "second", "hai", source_b, duration_seconds=1.0),
        ],
        tmp_path / "mixed.wav",
    )

    args = captured["args"]
    filter_complex = args[args.index("-filter_complex") + 1]
    assert "adelay=0:all=1" in filter_complex
    assert "adelay=1000:all=1" in filter_complex
    assert "amix=inputs=2" in filter_complex
    assert "-f" not in args


def test_export_aligned_audio_uses_smart_overlap_policy(tmp_path) -> None:
    config = AppConfig(dubbing_overlap_policy="smart")
    worker = export_worker.DubbingExportWorker("video.mp4", str(tmp_path / "out.wav"), "audio", config)
    worker._temp_dir = tmp_path
    captured: dict[str, list[object]] = {}
    source_a = tmp_path / "a.wav"
    source_b = tmp_path / "b.wav"
    source_a.write_bytes(b"a")
    source_b.write_bytes(b"b")

    worker._to_wav = lambda _input_path, output_path: Path(output_path).write_bytes(b"wav")
    worker._run_ffmpeg = lambda args, **_kwargs: captured.setdefault("args", args)

    worker._build_aligned_audio(
        [
            export_worker.ExportCue(0.0, "first", "mot", source_a, duration_seconds=3.0),
            export_worker.ExportCue(1.0, "second", "hai", source_b, duration_seconds=1.0),
        ],
        tmp_path / "mixed.wav",
    )

    args = captured["args"]
    filter_complex = args[args.index("-filter_complex") + 1]
    assert "adelay=0:all=1" in filter_complex
    assert "adelay=1750:all=1" in filter_complex


def test_dubbing_worker_queues_audio_at_source_start_even_when_previous_audio_extends(qapp, tmp_path) -> None:
    config = AppConfig(audio_source="original", dubbing_overlap_policy="strict_start")
    worker = DubbingWorker("video.mp4", lambda: 0, lambda: False, config)
    worker._scheduled_audio_until = 10.0
    audio_path = tmp_path / "target.wav"

    worker._queue_pending_audio(2.0, 1.0, audio_path, "hello", "xin chao")

    assert worker._pending_audio == [(2.0, 2.0, audio_path, "hello", "xin chao")]
    assert worker._scheduled_audio_until == 10.0


def test_dubbing_worker_smart_policy_pushes_large_overlap_only_briefly(qapp, tmp_path) -> None:
    config = AppConfig(audio_source="original", dubbing_overlap_policy="smart")
    worker = DubbingWorker("video.mp4", lambda: 0, lambda: False, config)
    worker._scheduled_audio_until = 10.0
    audio_path = tmp_path / "target.wav"

    worker._queue_pending_audio(2.0, 1.0, audio_path, "hello", "xin chao")

    assert worker._pending_audio == [(2.75, 2.0, audio_path, "hello", "xin chao")]
    assert worker._scheduled_audio_until == 10.0


def test_dubbing_worker_avoid_overlap_policy_queues_after_previous_audio(qapp, tmp_path) -> None:
    config = AppConfig(audio_source="original", dubbing_overlap_policy="avoid_overlap")
    worker = DubbingWorker("video.mp4", lambda: 0, lambda: False, config)
    worker._scheduled_audio_until = 10.0
    audio_path = tmp_path / "target.wav"

    worker._queue_pending_audio(2.0, 1.0, audio_path, "hello", "xin chao")

    assert worker._pending_audio == [(10.0, 2.0, audio_path, "hello", "xin chao")]
    assert worker._scheduled_audio_until == 11.0


def test_dubbing_worker_keeps_document_audio_sequential(qapp, tmp_path) -> None:
    config = AppConfig(audio_source="document_editor", dubbing_overlap_policy="strict_start")
    worker = DubbingWorker("document.txt", lambda: 0, lambda: False, config)
    worker._scheduled_audio_until = 10.0
    audio_path = tmp_path / "target.wav"

    worker._queue_pending_audio(2.0, 1.0, audio_path, "hello", "xin chao")

    assert worker._pending_audio == [(10.0, 2.0, audio_path, "hello", "xin chao")]
    assert worker._scheduled_audio_until == 11.0


def test_document_review_export_cue_uses_initialized_tts_lock(tmp_path) -> None:
    config = AppConfig(tts_provider="vieneu")
    worker = export_worker.DocumentReviewExportWorker("document.srt", [], str(tmp_path / "out.mp4"), config)
    worker._temp_dir = tmp_path
    worker._tts_provider = SimpleNamespace(synthesize=lambda _text, path, voice=None: Path(path).write_bytes(b"tts"))
    worker._to_wav = lambda _input_path, output_path: Path(output_path).write_bytes(b"wav")
    worker._trim_leading_silence = lambda audio_path: audio_path

    cue = worker._build_document_export_cue(
        0,
        export_worker.TranscriptCue(0.0, 1.0, "hello"),
        "hello",
        "xin chao",
        "wav",
    )

    assert cue.audio_path.exists()


def test_dubbing_worker_advances_async_segments_in_timeline_order(qapp) -> None:
    config = AppConfig(segment_seconds=4, dubbing_lookahead_segments=2)
    worker = DubbingWorker("video.mp4", lambda: 0, lambda: False, config)
    worker._covered_until = 0.0

    worker._completed_segment_starts.add(_segment_start_key(4.0))
    worker._advance_covered_until()
    assert worker._covered_until == 0.0

    worker._completed_segment_starts.add(_segment_start_key(0.0))
    worker._advance_covered_until()
    assert worker._covered_until == 8.0


def test_dubbing_worker_prebuffer_does_not_wait_for_full_target_ready_ahead(qapp) -> None:
    config = AppConfig(
        segment_seconds=12,
        dubbing_prebuffer_segments=2,
        dubbing_min_ready_ahead_seconds=40,
    )
    worker = DubbingWorker("video.mp4", lambda: 0, lambda: False, config)
    resumed: list[str] = []
    worker._launch_due_audio = lambda _current: False
    worker._request_resume = resumed.append
    worker._covered_until = 24.0
    worker._prepared_segments = 2
    worker._buffering = True

    worker._resume_if_buffer_ready(0.0)

    assert not worker._buffering
    assert resumed


def test_dubbing_worker_prebuffer_still_requires_prebuffer_ready_ahead(qapp) -> None:
    config = AppConfig(
        segment_seconds=12,
        dubbing_prebuffer_segments=2,
        dubbing_min_ready_ahead_seconds=40,
    )
    worker = DubbingWorker("video.mp4", lambda: 0, lambda: False, config)
    worker._launch_due_audio = lambda _current: False
    worker._request_resume = lambda _message: None
    worker._covered_until = 12.0
    worker._prepared_segments = 2
    worker._buffering = True

    worker._resume_if_buffer_ready(0.0)

    assert worker._buffering
