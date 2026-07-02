from __future__ import annotations

from ai_player.workers.dubbing_runtime import (
    can_process_segments_async,
    is_http_source,
    is_live_capture_source,
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
