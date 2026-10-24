from __future__ import annotations

from concurrent.futures import Future
from types import SimpleNamespace

from ai_player.application.workflows.realtime import DubbingWorker
from ai_player.domain.dubbing_runtime import (
    adaptive_resume_ready_ahead_seconds,
    can_process_segments_async,
    is_http_source,
    is_live_capture_source,
    pause_below_seconds,
    required_ready_ahead_seconds,
    segment_worker_count,
    source_audio_cache_input,
)


def test_dubbing_runtime_classifies_audio_sources() -> None:
    assert is_live_capture_source("system_microphone")
    assert not is_live_capture_source("original")
    assert can_process_segments_async("original")
    assert can_process_segments_async("subtitle")
    assert not can_process_segments_async("microphone")


def test_segment_worker_count_uses_env_override_and_caps_values() -> None:
    assert segment_worker_count(audio_source="original", lookahead_segments=4, env_value="3") == 3
    assert segment_worker_count(audio_source="subtitle", lookahead_segments=4, env_value="99") == 8
    assert segment_worker_count(audio_source="subtitle", lookahead_segments=4, env_value="bad", cpu_count=8) == 4
    assert segment_worker_count(audio_source="original", lookahead_segments=4, env_value="", cpu_count=8) == 1


def test_source_audio_cache_input_accepts_direct_media_urls_and_local_files(tmp_path) -> None:
    media_file = tmp_path / "demo.mp4"
    media_file.write_bytes(b"demo")

    assert source_audio_cache_input("original", "https://cdn.example.test/video.mp4?token=abc")
    assert source_audio_cache_input("original", str(media_file)) == str(media_file)
    assert source_audio_cache_input("subtitle", str(media_file)) is None


def test_source_audio_cache_input_rejects_stream_manifests_and_missing_files(tmp_path) -> None:
    assert source_audio_cache_input("original", "https://cdn.example.test/live.m3u8") is None
    assert source_audio_cache_input("original", str(tmp_path / "missing.mp4")) is None


def test_is_http_source_uses_url_scheme() -> None:
    assert is_http_source("HTTP://example.test/video.mp4")
    assert is_http_source("https://example.test/video.mp4")
    assert not is_http_source("C:/videos/demo.mp4")


def test_required_ready_ahead_seconds_handles_transcript_and_segment_sources() -> None:
    assert (
        required_ready_ahead_seconds(
            audio_source="transcript",
            min_ready_ahead_seconds=10,
            segment_seconds=5,
            prebuffer_segments=2,
        )
        == 0.5
    )


def test_dubbing_buffer_uses_separate_pause_and_resume_watermarks() -> None:
    assert pause_below_seconds(resume_ready_ahead_seconds=15, segment_seconds=6) == 4.5
    assert pause_below_seconds(resume_ready_ahead_seconds=6, segment_seconds=3) == 2.25


def test_adaptive_buffer_uses_p95_processing_time_and_caps_at_lookahead() -> None:
    assert (
        adaptive_resume_ready_ahead_seconds(
            configured_seconds=10,
            processing_samples=[2, 3, 4, 12],
            segment_seconds=6,
            lookahead_segments=3,
        )
        == 18
    )
    assert (
        adaptive_resume_ready_ahead_seconds(
            configured_seconds=10,
            processing_samples=[1, 2, 3],
            segment_seconds=6,
            lookahead_segments=3,
        )
        == 10
    )
    assert (
        required_ready_ahead_seconds(
            audio_source="original",
            min_ready_ahead_seconds=3,
            segment_seconds=5,
            prebuffer_segments=2,
        )
        == 3.0
    )
    assert (
        required_ready_ahead_seconds(
            audio_source="original",
            min_ready_ahead_seconds=999,
            segment_seconds=5,
            prebuffer_segments=2,
        )
        == 10.0
    )


def test_submit_segment_work_reports_when_bounded_queue_is_full() -> None:
    pending = Future()
    worker = SimpleNamespace(
        _segment_executor=SimpleNamespace(submit=lambda *_args: Future()),
        _config=SimpleNamespace(dubbing_lookahead_segments=1),
        _segment_futures={pending: 0.0},
        _stop_requested=False,
        _next_segment_start=4.0,
        _segment_seconds=lambda: 4.0,
        _process_segment=lambda _start: None,
    )

    assert DubbingWorker._submit_segment_work(worker, 8.0) is False


def test_submit_segment_work_reports_new_submission() -> None:
    submitted: list[float] = []

    def submit(_callback, start_seconds: float) -> Future:
        submitted.append(start_seconds)
        return Future()

    worker = SimpleNamespace(
        _segment_executor=SimpleNamespace(submit=submit),
        _config=SimpleNamespace(dubbing_lookahead_segments=1),
        _segment_futures={},
        _stop_requested=False,
        _next_segment_start=4.0,
        _segment_seconds=lambda: 4.0,
        _process_segment=lambda _start: None,
    )

    assert DubbingWorker._submit_segment_work(worker, 8.0) is True
    assert submitted == [4.0]
