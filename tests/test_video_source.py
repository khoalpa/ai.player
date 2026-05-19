from __future__ import annotations

import os
import sys
import time
from types import SimpleNamespace

import pytest

from ai_player.services import video_source


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.com/video.mp4", True),
        ("rtsp://camera.local/live", True),
        ("file:///demo.mp4", False),
    ],
)
def test_supported_video_url(url: str, expected: bool) -> None:
    assert video_source.is_supported_video_url(url) is expected


@pytest.mark.parametrize(("url", "expected"), [("https://youtu.be/demo", True), ("https://youtu.be/demo.mp4", False)])
def test_should_resolve_with_ytdlp(url: str, expected: bool) -> None:
    assert video_source._should_resolve_with_ytdlp(url) is expected


@pytest.mark.parametrize(
    ("url", "provider"),
    [
        ("https://www.youtube.com/watch?v=x", "youtube"),
        ("https://vm.tiktok.com/x", "tiktok"),
        ("https://x.com/demo/status/1", "x-twitter"),
        ("https://example-host.test/watch", "example-host-test"),
    ],
)
def test_provider_name(url: str, provider: str) -> None:
    assert video_source._provider_name(url) == provider


@pytest.mark.parametrize(("quality", "needle"), [("480p", "height<=480"), ("best", "bestvideo")])
def test_format_selector_contains_quality_constraints(quality: str, needle: str) -> None:
    assert needle in video_source._format_selector(quality)


def test_stream_format_selector_prefers_single_playable_stream() -> None:
    selector = video_source._stream_format_selector("720p")

    assert "height<=720" in selector
    assert "acodec!=none" in selector
    assert "bestvideo" not in selector


def test_resolve_page_url_without_full_cache_returns_stream_url(monkeypatch) -> None:
    captured_options = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            captured_options.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, url, download):
            assert url == "https://youtu.be/demo"
            assert download is False
            return {
                "id": "demo",
                "title": "Demo",
                "url": "https://cdn.example.test/demo.mp4",
            }

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    source = video_source.resolve_video_source("https://youtu.be/demo", full_cache=False)

    assert source.playback_url == "https://cdn.example.test/demo.mp4"
    assert source.title == "Demo"
    assert source.provider == "youtube"
    assert captured_options["skip_download"] is True
    assert "outtmpl" not in captured_options
    assert "progress_hooks" not in captured_options


def test_cleanup_cache_root_removes_old_files(tmp_path) -> None:
    old_file = tmp_path / "old.mp4"
    old_file.write_text("old", encoding="utf-8")
    old_time = time.time() - 100
    os.utime(old_file, (old_time, old_time))

    video_source._cleanup_cache_root(tmp_path, max_age_seconds=1, max_bytes=1024)

    assert not old_file.exists()
