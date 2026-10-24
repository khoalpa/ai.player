from __future__ import annotations

import os
import sys
import time
from types import SimpleNamespace

import pytest

from ai_player.adapters.sources import video_source


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
    ("url", "kind", "provider", "requires_ytdlp", "direct_media"),
    [
        ("https://example.com/video.mp4", "direct_media", "example-com", False, True),
        ("https://youtu.be/demo", "page", "youtube", True, False),
        ("https://www.njav.com/vi/xvideos/rki-729-uncensored-leak", "page", "njav-com", True, False),
        ("rtsp://camera.local/live", "network_stream", "rtsp", False, False),
        ("https://web.telegram.org/a/progressive/document123", "telegram_web", "telegram", False, False),
        ("https://t.me/+s91pFSI1prtmZjMx", "private_telegram", "telegram", False, False),
    ],
)
def test_inspect_video_url_classifies_source(
    url: str,
    kind: str,
    provider: str,
    requires_ytdlp: bool,
    direct_media: bool,
) -> None:
    preflight = video_source.inspect_video_url(url)

    assert preflight.supported is True
    assert preflight.source_kind == kind
    assert preflight.provider == provider
    assert preflight.requires_ytdlp is requires_ytdlp
    assert preflight.direct_media is direct_media


def test_inspect_video_url_reports_unsupported_url() -> None:
    preflight = video_source.inspect_video_url("file:///demo.mp4")

    assert preflight.supported is False
    assert preflight.source_kind == "unsupported"


def test_resolve_rejects_telegram_web_progressive_url() -> None:
    with pytest.raises(video_source.VideoSourceError) as exc_info:
        video_source.resolve_video_source(
            "https://web.telegram.org/a/progressive/document6303332284653118021",
            language_id="en",
        )

    assert "Telegram Web progressive" in str(exc_info.value)
    assert exc_info.value.code == video_source.VIDEO_ERROR_PROVIDER_UNSUPPORTED
    assert exc_info.value.provider == "telegram"


def test_resolve_rejects_private_telegram_url_before_ytdlp() -> None:
    with pytest.raises(video_source.VideoSourceError) as exc_info:
        video_source.resolve_video_source("https://t.me/+s91pFSI1prtmZjMx", language_id="en")

    assert "Telegram invite/private URLs" in str(exc_info.value)
    assert exc_info.value.code == video_source.VIDEO_ERROR_PROVIDER_UNSUPPORTED
    assert exc_info.value.provider == "telegram"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://youtu.be/demo", True),
        ("https://youtu.be/demo.mp4", False),
        ("https://www.njav.com/vi/xvideos/rki-729-uncensored-leak", True),
        ("https://t.me/+s91pFSI1prtmZjMx", False),
        ("https://t.me/c/123456789/42", False),
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
        "https://media.internal/watch/demo",
        "https://cdn.media.internal/watch/demo",
    ],
)
def test_should_resolve_extra_ytdlp_hosts_when_configured(monkeypatch, url: str) -> None:
    monkeypatch.setenv(
        "AI_PLAYER_EXTRA_YTDLP_HOSTS",
        "video.example.test,another.example.test,*.internal,*.media.internal",
    )

    assert video_source._should_resolve_with_ytdlp(url) is True


def test_should_resolve_private_plugin_extractor_without_extra_hosts(monkeypatch) -> None:
    monkeypatch.delenv("AI_PLAYER_EXTRA_YTDLP_HOSTS", raising=False)
    monkeypatch.setattr(video_source, "_has_plugin_ytdlp_extractor", lambda value: "private.example" in value)

    assert video_source._should_resolve_with_ytdlp("https://private.example/watch/demo") is True


def test_should_resolve_plugin_registry_hosts_without_extra_hosts(monkeypatch) -> None:
    monkeypatch.delenv("AI_PLAYER_EXTRA_YTDLP_HOSTS", raising=False)
    monkeypatch.setattr(video_source, "_plugin_ytdlp_hosts", lambda: ("eporner.com",))
    monkeypatch.setattr(video_source, "_has_plugin_ytdlp_extractor", lambda _value: False)

    assert video_source._should_resolve_with_ytdlp("https://www.eporner.com/video-demo/demo-title/") is True


def test_plugin_ytdlp_extractors_only_keeps_plugin_classes(monkeypatch) -> None:
    class PluginIE:
        IE_NAME = "private"
        __module__ = "yt_dlp_plugins.extractor.private_site"

    class BuiltinIE:
        IE_NAME = "builtin"
        __module__ = "yt_dlp.extractor.builtin_site"

    class GenericIE:
        IE_NAME = "generic"
        __module__ = "yt_dlp_plugins.extractor.generic"

    class FakeYoutubeDL:
        def __init__(self, _options) -> None:
            self._ies = {
                "Private": PluginIE,
                "Builtin": BuiltinIE,
                "Generic": GenericIE,
            }

    fake_ytdlp = SimpleNamespace(YoutubeDL=FakeYoutubeDL)
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_ytdlp)
    video_source._plugin_ytdlp_extractors.cache_clear()
    try:
        assert video_source._plugin_ytdlp_extractors() == (PluginIE,)
    finally:
        video_source._plugin_ytdlp_extractors.cache_clear()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("video.example.test", "video.example.test"),
        ("https://www.video.example.test/watch/demo", "video.example.test"),
        ("*.video.example.test", "*.video.example.test"),
        ("video.*", "video.*"),
        ("", ""),
    ],
)
def test_normalize_extra_ytdlp_host(value: str, expected: str) -> None:
    assert video_source._normalize_extra_ytdlp_host(value) == expected


@pytest.mark.parametrize(
    ("host", "domain", "expected"),
    [
        ("video.example.test", "video.example.test", True),
        ("sub.video.example.test", "video.example.test", True),
        ("video.example.test", "*.example.test", True),
        ("sub.video.example.test", "*.example.test", False),
        ("video.example.test", "video.*", False),
        ("video.internal", "*.internal", True),
    ],
)
def test_host_matches_supports_extra_host_wildcards(host: str, domain: str, expected: bool) -> None:
    assert video_source._host_matches(host, domain) is expected


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


def test_format_selector_does_not_fallback_to_video_only_best() -> None:
    assert not video_source._format_selector("best").endswith("/best")
    assert not video_source._format_selector("720p").endswith("/best")
    assert "best*[vcodec!=none]" in video_source._format_selector("best")


def test_default_playback_quality_prefers_best(tmp_path) -> None:
    assert video_source._normalize_playback_quality("") == "best"
    assert video_source._normalize_playback_quality("unknown") == "best"
    assert video_source._source_cache_dir("Demo", cache_root=tmp_path).name == "best"


def test_stream_format_selector_prefers_single_playable_stream() -> None:
    selector = video_source._stream_format_selector("720p")

    assert "height<=720" in selector
    assert "acodec!=none" in selector
    assert "best*[vcodec!=none]" in selector
    assert "bestvideo" not in selector
    assert not selector.endswith("/best")


def test_buomtv_uses_relaxed_format_selector_for_unknown_codecs() -> None:
    assert video_source._provider_format_selector("buomtv-baby", "best", full_cache=False) == "best/best*"
    assert video_source._provider_format_selector("buomtv-baby", "best", full_cache=True) == "best/best*"
    assert video_source._provider_format_selector("youtube", "best", full_cache=False) != "best/best*"


def test_prefer_local_ytdlp_plugins_adds_workspace_plugin_first(monkeypatch) -> None:
    plugin_root = str(video_source.LOCAL_ADULT_EXTRACTOR_PLUGIN)
    monkeypatch.setattr(sys, "path", [item for item in sys.path if item != plugin_root])

    video_source._prefer_local_ytdlp_plugins()

    assert sys.path[0] == plugin_root


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
                "http_headers": {
                    "Referer": "https://youtu.be/demo",
                    "User-Agent": "DemoAgent/1.0",
                },
                "width": 1080,
                "height": 1920,
            }

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    source = video_source.resolve_video_source("https://youtu.be/demo", full_cache=False)

    assert source.playback_url == "https://cdn.example.test/demo.mp4"
    assert source.title == "Demo"
    assert source.provider == "youtube"
    assert (source.width, source.height) == (1080, 1920)
    assert source.http_headers == {
        "Referer": "https://youtu.be/demo",
        "User-Agent": "DemoAgent/1.0",
    }
    assert captured_options["skip_download"] is True
    assert "outtmpl" not in captured_options
    assert "progress_hooks" not in captured_options


def test_resolve_page_url_preserves_selected_format_headers(monkeypatch) -> None:
    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, url, download):
            assert url == "https://www.njav.com/vi/xvideos/demo"
            assert download is False
            return {
                "id": "demo",
                "title": "Demo",
                "formats": [
                    {
                        "url": "https://media.example.test/demo.m3u8",
                        "vcodec": "h264",
                        "acodec": "aac",
                        "http_headers": {
                            "Referer": "https://www.njav.com/vi/xvideos/demo",
                            "User-Agent": "DemoAgent/1.0",
                        },
                    }
                ],
            }

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    source = video_source.resolve_video_source("https://www.njav.com/vi/xvideos/demo", full_cache=False)

    assert source.playback_url == "https://media.example.test/demo.m3u8"
    assert source.http_headers == {
        "Referer": "https://www.njav.com/vi/xvideos/demo",
        "User-Agent": "DemoAgent/1.0",
    }


def test_resolve_telegram_limits_ytdlp_extractors(monkeypatch) -> None:
    captured_options = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            captured_options.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, url, download):
            assert url == "https://t.me/demo/123"
            assert download is False
            return {
                "id": "123",
                "title": "Telegram demo",
                "url": "https://cdn.example.test/telegram.mp4",
            }

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    source = video_source.resolve_video_source("https://t.me/demo/123", full_cache=False)

    assert source.playback_url == "https://cdn.example.test/telegram.mp4"
    assert source.provider == "telegram"
    assert captured_options["allowed_extractors"] == ["telegram:embed"]


def test_resolve_tiktok_limits_ytdlp_extractors(monkeypatch) -> None:
    captured_options = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            captured_options.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, url, download):
            assert url == "https://www.tiktok.com/@demo/video/123"
            assert download is False
            return {
                "id": "123",
                "title": "TikTok demo",
                "url": "https://cdn.example.test/tiktok.mp4",
            }

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    source = video_source.resolve_video_source("https://www.tiktok.com/@demo/video/123", full_cache=False)

    assert source.playback_url == "https://cdn.example.test/tiktok.mp4"
    assert source.provider == "tiktok"
    assert captured_options["allowed_extractors"] == [r"tiktok(:.*)?", r"vm\.tiktok"]


@pytest.mark.parametrize("full_cache", [False, True])
def test_resolve_page_url_rejects_empty_ytdlp_info(monkeypatch, full_cache: bool) -> None:
    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download):
            assert download is full_cache
            return None

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    with pytest.raises(video_source.VideoSourceError) as exc_info:
        video_source.resolve_video_source("https://t.me/demo/123", full_cache=full_cache, language_id="en")

    assert "Could not read video information from telegram" in str(exc_info.value)
    assert exc_info.value.code == video_source.VIDEO_ERROR_YTDLP_FORMAT_MISSING
    assert exc_info.value.provider == "telegram"


def test_video_dimensions_from_info_uses_requested_formats() -> None:
    assert video_source._video_dimensions_from_info(
        {
            "requested_formats": [
                {"vcodec": "h264", "width": 720, "height": 1280},
                {"acodec": "aac"},
            ]
        }
    ) == (720, 1280)


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
    assert exc_info.value.code == video_source.VIDEO_ERROR_YTDLP_DOWNLOAD_FAILED
    assert exc_info.value.provider == "youtube"


def test_resolve_page_url_reports_missing_usable_media(monkeypatch) -> None:
    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download):
            assert download is False
            raise RuntimeError("ERROR: [vlxx] demo: Unable to find embedded media URL")

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    monkeypatch.setattr(video_source, "_has_plugin_ytdlp_extractor", lambda _value: True)
    monkeypatch.setattr(video_source, "_resolve_vlxx_wrapped_hls", lambda *_args, **_kwargs: None)

    with pytest.raises(video_source.VideoSourceError) as exc_info:
        video_source.resolve_video_source("https://vlxx.example/video/demo", full_cache=False, language_id="en")

    message = str(exc_info.value)
    assert "usable audio/video stream" in message
    assert "Unable to find embedded media URL" not in message
    assert exc_info.value.code == video_source.VIDEO_ERROR_YTDLP_FORMAT_MISSING
    assert exc_info.value.provider == "vlxx-example"


def test_clean_download_error_removes_bare_ansi_codes() -> None:
    message = video_source._clean_download_error("[][0;31mERROR:[][0m [youtube] demo: unavailable")

    assert message == "[youtube] demo: unavailable"


def test_clean_download_error_redacts_url_query_secrets() -> None:
    message = video_source._clean_download_error(
        "ERROR: download failed https://googleapis.test/media?key=download-secret&id=1"
    )

    assert "download-secret" not in message
    assert "key=[redacted]" in message
    assert "id=1" in message


def test_downloaded_file_path_ignores_malformed_requested_downloads(tmp_path) -> None:
    downloaded = tmp_path / "demo.mp4"
    downloaded.write_text("video", encoding="utf-8")

    assert video_source._downloaded_file_path(
        {"requested_downloads": ["bad", {"filepath": str(downloaded)}]},
        tmp_path,
    ) == str(downloaded)


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


def test_source_cache_dir_uses_custom_root(tmp_path) -> None:
    cache_dir = video_source._source_cache_dir("Example Provider", "best", cache_root=tmp_path)

    assert cache_dir == tmp_path / "ai-player-sources" / "example-provider" / "best"
    assert cache_dir.is_dir()


def test_resolve_page_url_uses_custom_cache_dir(monkeypatch, tmp_path) -> None:
    captured_options = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            captured_options.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download):
            assert download is True
            downloaded = tmp_path / "ai-player-sources" / "youtube" / "best" / "demo.mp4"
            downloaded.parent.mkdir(parents=True, exist_ok=True)
            downloaded.write_text("video", encoding="utf-8")
            return {
                "id": "demo",
                "title": "Demo",
                "requested_downloads": [{"filepath": str(downloaded)}],
            }

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    monkeypatch.setattr(video_source, "_video_file_has_audio", lambda _path: True)

    source = video_source.resolve_video_source("https://youtu.be/demo", full_cache=True, cache_dir=tmp_path)

    assert source.playback_url == str(tmp_path / "ai-player-sources" / "youtube" / "best" / "demo.mp4")
    assert str(tmp_path / "ai-player-sources" / "youtube" / "best") in captured_options["outtmpl"]
    assert captured_options["ffmpeg_location"]


def test_resolve_page_url_rejects_cached_file_without_audio(monkeypatch, tmp_path) -> None:
    downloaded = tmp_path / "ai-player-sources" / "youtube" / "720p" / "demo.mp4"

    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download):
            assert download is True
            downloaded.parent.mkdir(parents=True, exist_ok=True)
            downloaded.write_text("video", encoding="utf-8")
            return {
                "id": "demo",
                "title": "Demo",
                "requested_downloads": [{"filepath": str(downloaded)}],
            }

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    monkeypatch.setattr(video_source, "_video_file_has_audio", lambda _path: False)

    with pytest.raises(video_source.VideoSourceError) as exc_info:
        video_source.resolve_video_source(
            "https://youtu.be/demo",
            full_cache=True,
            cache_dir=tmp_path,
            language_id="en",
        )

    assert "no audio stream" in str(exc_info.value)
    assert exc_info.value.code == video_source.VIDEO_ERROR_VIDEO_NO_AUDIO
    assert exc_info.value.provider == "youtube"
    assert not downloaded.exists()
