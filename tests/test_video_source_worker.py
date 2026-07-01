from __future__ import annotations

from ai_player.services.video_source import VideoSource
from ai_player.workers import player_window_workers
from ai_player.workers.player_window_workers import VideoSourceWorker


def test_video_source_worker_falls_back_to_stream_when_full_cache_is_forbidden(monkeypatch, qapp) -> None:
    calls: list[bool] = []
    stream_source = VideoSource(
        input_url="https://www.njav.com/vi/xvideos/demo",
        playback_url="https://media.example.test/demo.m3u8",
        title="Demo",
        provider="njav-com",
        is_resolved=True,
    )

    def fake_resolve_video_source(_url, _quality, *, full_cache=True, **_kwargs):
        calls.append(full_cache)
        if full_cache:
            raise RuntimeError("unable to download video data: HTTP Error 403: Forbidden")
        return stream_source

    monkeypatch.setattr(player_window_workers, "resolve_video_source", fake_resolve_video_source)
    worker = VideoSourceWorker(
        "https://www.njav.com/vi/xvideos/demo",
        "best",
        full_cache=True,
        play_after_cache_percent=15,
    )
    resolved = []
    failed = []
    worker.resolved.connect(resolved.append)
    worker.failed.connect(failed.append)

    worker.run()

    assert calls == [False, True]
    assert resolved == [stream_source]
    assert failed == []


def test_video_source_worker_reports_forbidden_when_no_stream_fallback(monkeypatch, qapp) -> None:
    def fake_resolve_video_source(_url, _quality, *, full_cache=True, **_kwargs):
        raise RuntimeError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(player_window_workers, "resolve_video_source", fake_resolve_video_source)
    worker = VideoSourceWorker(
        "https://www.njav.com/vi/xvideos/demo",
        "best",
        full_cache=True,
        play_after_cache_percent=0,
    )
    resolved = []
    failed = []
    worker.resolved.connect(resolved.append)
    worker.failed.connect(failed.append)

    worker.run()

    assert resolved == []
    assert failed == ["HTTP Error 403: Forbidden"]


def test_video_source_worker_falls_back_to_stream_when_full_cache_format_is_missing(monkeypatch, qapp) -> None:
    calls: list[bool] = []
    stream_source = VideoSource(
        input_url="https://buomtv.example/video/116957",
        playback_url="https://cdn.example.test/buomtv.m3u8",
        title="Demo",
        provider="buomtv-baby",
        is_resolved=True,
    )

    def fake_resolve_video_source(_url, _quality, *, full_cache=True, **_kwargs):
        calls.append(full_cache)
        if full_cache:
            raise RuntimeError(
                "[buomtv] 116957: Requested format is not available. "
                "Use --list-formats for a list of available formats"
            )
        return stream_source

    monkeypatch.setattr(player_window_workers, "resolve_video_source", fake_resolve_video_source)
    worker = VideoSourceWorker(
        "https://buomtv.example/video/116957",
        "best",
        full_cache=True,
        play_after_cache_percent=15,
    )
    resolved = []
    failed = []
    worker.resolved.connect(resolved.append)
    worker.failed.connect(failed.append)

    worker.run()

    assert calls == [False, True]
    assert resolved == [stream_source]
    assert failed == []
