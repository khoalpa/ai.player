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


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://youtu.be/demo", True),
        ("https://youtu.be/demo.mp4", False),
        ("https://buomtv.com/watch/demo", True),
        ("https://phim.buomtv.cc/watch/demo", True),
        ("https://buomtv.io/videos/demo.mp4", False),
        ("https://missav.ws/demo", True),
        ("https://supjav.com/demo", True),
        ("https://javmost.cx/demo", True),
        ("https://javgg.net/demo", True),
        ("https://www.r18.com/videos/demo", True),
        ("https://www.javlibrary.com/en/?v=demo", True),
        ("https://javhd.com/demo", True),
        ("https://chaturbate.eu/demo/", True),
        ("https://en.chaturbate.com/demo/", True),
        ("https://de.bongacams.net/demo", True),
        ("https://stripchat.com/demo", True),
        ("https://www.cam4.com/demo", True),
        ("https://www.camsoda.com/demo", True),
        ("https://www.livejasmin.com/en/demo", True),
        ("https://www.cam4.com/demo.mp4", False),
    ],
)
def test_should_resolve_with_ytdlp(url: str, expected: bool) -> None:
    assert video_source._should_resolve_with_ytdlp(url) is expected


@pytest.mark.parametrize(
    ("url", "provider"),
    [
        ("https://www.youtube.com/watch?v=x", "youtube"),
        ("https://vm.tiktok.com/x", "tiktok"),
        ("https://x.com/demo/status/1", "x-twitter"),
        ("https://phim.buomtv.cc/watch/demo", "buomtv"),
        ("https://missav.ws/demo", "missav"),
        ("https://supjav.com/demo", "supjav"),
        ("https://javmost.cx/demo", "javmost"),
        ("https://javgg.net/demo", "javgg"),
        ("https://www.r18.com/videos/demo", "r18"),
        ("https://www.javlibrary.com/en/?v=demo", "javlibrary"),
        ("https://javhd.com/demo", "javhd"),
        ("https://chaturbate.global/demo/", "chaturbate"),
        ("https://de.bongacams.net/demo", "bongacams"),
        ("https://stripchat.com/demo", "stripchat"),
        ("https://www.cam4.com/demo", "cam4"),
        ("https://www.camsoda.com/demo", "camsoda"),
        ("https://www.livejasmin.com/en/demo", "livejasmin"),
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


def test_buomtv_url_without_full_cache_uses_pwa_stream(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeSession:
        def __init__(self):
            self.posts = []
            self.gets = []

        def post(self, url, data, headers, timeout):
            self.posts.append((url, data, headers, timeout))
            return FakeResponse({"status": {"code": 200}, "response": {"token": "demo token"}})

        def get(self, url, headers, timeout):
            self.gets.append((url, headers, timeout))
            return FakeResponse(
                {
                    "status": {"code": 200},
                    "response": {
                        "video_title": "Demo BuomTV",
                        "video_main_tag": "Free",
                        "video_urls": {
                            "240": "/mediapwa2/long/token/240/106746.m3u8?sign=low",
                            "480": "/mediapwa2/long/token/480/106746.m3u8?sign=high",
                        },
                    },
                }
            )

    fake_session = FakeSession()
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(Session=lambda: fake_session))

    source = video_source.resolve_video_source(
        "https://buomtv.life/movie/SSIS-245/106746",
        playback_quality="720p",
        full_cache=False,
    )

    assert source.provider == "buomtv"
    assert source.title == "Demo BuomTV"
    assert source.playback_url == "https://api.buomtv.life/mediapwa2/long/token/480/106746.m3u8?sign=high"
    assert "pwa/register/pwatoken" in fake_session.posts[0][0]
    assert "pwa/video/info/106746" in fake_session.gets[0][0]
    assert "token=demo%20token" in fake_session.gets[0][0]


def test_buomtv_url_wraps_http_errors(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self):
            raise RuntimeError("500 Server Error")

        def json(self):
            return {}

    class FakeSession:
        def post(self, url, data, headers, timeout):
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(Session=FakeSession))

    with pytest.raises(video_source.VideoSourceError, match="BuomTV token API lỗi HTTP"):
        video_source.resolve_video_source("https://buomtv.life/movie/SSIS-245/106746", full_cache=False)


def test_buomtv_url_wraps_invalid_json(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("invalid json")

    class FakeSession:
        def post(self, url, data, headers, timeout):
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(Session=FakeSession))

    with pytest.raises(video_source.VideoSourceError, match="BuomTV token API không trả JSON hợp lệ"):
        video_source.resolve_video_source("https://buomtv.life/movie/SSIS-245/106746", full_cache=False)


def test_cleanup_cache_root_removes_old_files(tmp_path) -> None:
    old_file = tmp_path / "old.mp4"
    old_file.write_text("old", encoding="utf-8")
    old_time = time.time() - 100
    os.utime(old_file, (old_time, old_time))

    video_source._cleanup_cache_root(tmp_path, max_age_seconds=1, max_bytes=1024)

    assert not old_file.exists()
