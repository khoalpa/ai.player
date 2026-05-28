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


def test_resolve_rejects_telegram_web_progressive_url() -> None:
    with pytest.raises(video_source.VideoSourceError) as exc_info:
        video_source.resolve_video_source(
            "https://web.telegram.org/a/progressive/document6303332284653118021",
            language_id="en",
        )

    assert "Telegram Web progressive" in str(exc_info.value)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://youtu.be/demo", True),
        ("https://youtu.be/demo.mp4", False),
        ("https://video.example.test/watch/demo", False),
        ("https://media.example.test/videos/demo.mp4", False),
    ],
)
def test_should_resolve_with_ytdlp(url: str, expected: bool) -> None:
    assert video_source._should_resolve_with_ytdlp(url) is expected


@pytest.mark.parametrize(
    "url",
    [
        "https://video.example.test/watch/demo",
        "https://sub.video.example.test/watch/demo",
        "https://another.example.test/show/demo",
    ],
)
def test_should_resolve_extra_ytdlp_hosts_when_configured(monkeypatch, url: str) -> None:
    monkeypatch.setenv("AI_PLAYER_EXTRA_YTDLP_HOSTS", "video.example.test,another.example.test")

    assert video_source._should_resolve_with_ytdlp(url) is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("video.example.test", "video.example.test"),
        ("https://www.video.example.test/watch/demo", "video.example.test"),
        ("*.video.example.test", "video.example.test"),
        ("", ""),
    ],
)
def test_normalize_extra_ytdlp_host(value: str, expected: str) -> None:
    assert video_source._normalize_extra_ytdlp_host(value) == expected


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


def test_resolve_page_url_cleans_ytdlp_color_codes(monkeypatch) -> None:
    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download):
            assert download is True
            raise RuntimeError("\x1b[0;31mERROR:\x1b[0m [youtube] demo: This video is not available")

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    with pytest.raises(video_source.VideoSourceError) as exc_info:
        video_source.resolve_video_source("https://youtu.be/demo", full_cache=True)

    message = str(exc_info.value)
    assert "This video is not available" in message
    assert "ERROR:" not in message
    assert "\x1b" not in message
    assert "[0;31m" not in message


def test_clean_download_error_removes_bare_ansi_codes() -> None:
    message = video_source._clean_download_error("[][0;31mERROR:[][0m [youtube] demo: unavailable")

    assert message == "[youtube] demo: unavailable"


def test_downloaded_file_path_ignores_malformed_requested_downloads(tmp_path) -> None:
    downloaded = tmp_path / "demo.mp4"
    downloaded.write_text("video", encoding="utf-8")

    assert (
        video_source._downloaded_file_path(
            {"requested_downloads": ["bad", {"filepath": str(downloaded)}]},
            tmp_path,
        )
        == str(downloaded)
    )


def test_stream_playback_url_ignores_malformed_format_items() -> None:
    assert (
        video_source._stream_playback_url(
            {
                "requested_formats": ["bad"],
                "formats": [
                    "bad",
                    {"url": "https://cdn.example.test/video.mp4", "vcodec": "h264", "acodec": "aac"},
                ],
            }
        )
        == "https://cdn.example.test/video.mp4"
    )


def test_cleanup_cache_root_removes_old_files(tmp_path) -> None:
    old_file = tmp_path / "old.mp4"
    old_file.write_text("old", encoding="utf-8")
    old_time = time.time() - 100
    os.utime(old_file, (old_time, old_time))

    video_source._cleanup_cache_root(tmp_path, max_age_seconds=1, max_bytes=1024)

    assert not old_file.exists()
