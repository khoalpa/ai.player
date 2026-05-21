from __future__ import annotations

import pytest
import yt_dlp

from yt_dlp_plugins.extractor.adult_sites import (
    JAVGGIE,
    JAVHDIE,
    R18IE,
    JAVLibraryIE,
    JAVMostIE,
    LiveJasminIE,
    MissAVIE,
    SupJavIE,
)

EXTRACTOR_CASES = [
    (MissAVIE, "https://missav.ws/demo-id", "demo-id"),
    (SupJavIE, "https://supjav.com/category/demo-id", "demo-id"),
    (JAVMostIE, "https://javmost.cx/demo-id", "demo-id"),
    (JAVGGIE, "https://javgg.net/jav/demo-id", "demo-id"),
    (R18IE, "https://www.r18.com/videos/vod/movies/detail/-/id=demo-id/", "demo-id"),
    (JAVLibraryIE, "https://www.javlibrary.com/en/?v=demo-id", "demo-id"),
    (JAVHDIE, "https://javhd.com/videos/demo-id", "demo-id"),
    (LiveJasminIE, "https://www.livejasmin.com/en/demo-room", "demo-room"),
]


@pytest.mark.parametrize(("extractor_cls", "url", "expected_id"), EXTRACTOR_CASES)
def test_adult_site_extractors_match_supported_urls(extractor_cls, url: str, expected_id: str) -> None:
    assert extractor_cls.suitable(url)
    assert extractor_cls._match_id(url) == expected_id


def test_ytdlp_loads_adult_site_plugin_extractors() -> None:
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        names = {ie.IE_NAME for ie in ydl._ies.values()}

    assert names >= {"missav", "supjav", "javmost", "javgg", "r18", "javlibrary", "javhd", "livejasmin"}


def test_adult_site_extractor_returns_direct_mp4(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="Demo title">
        <meta property="og:image" content="/thumb.jpg">
      </head>
      <body>
        <video src="https://cdn.example.test/video.mp4"></video>
      </body>
    </html>
    """

    def fake_download_webpage(self, url, video_id, **_kwargs):
        assert url == "https://missav.ws/demo-id"
        assert video_id == "demo-id"
        return html

    monkeypatch.setattr(MissAVIE, "_download_webpage", fake_download_webpage)

    result = MissAVIE(yt_dlp.YoutubeDL({"quiet": True}))._real_extract("https://missav.ws/demo-id")

    assert result["id"] == "demo-id"
    assert result["title"] == "Demo title"
    assert result["thumbnail"] == "https://missav.ws/thumb.jpg"
    assert result["age_limit"] == 18
    assert result["formats"] == [
        {
            "url": "https://cdn.example.test/video.mp4",
            "ext": "mp4",
            "http_headers": MissAVIE._adult_site_headers("https://missav.ws/demo-id"),
        }
    ]


def test_adult_site_extractor_follows_embedded_player(monkeypatch) -> None:
    pages = {
        "https://supjav.com/watch/demo-id": '<iframe src="https://player.example.test/embed/demo-id"></iframe>',
        "https://player.example.test/embed/demo-id": '<script>var hls = "https://cdn.example.test/master.m3u8";</script>',
    }

    def fake_download_webpage(self, url, video_id, **_kwargs):
        assert video_id == "demo-id"
        return pages[url]

    def fake_extract_m3u8_formats(self, media_url, video_id, *args, **kwargs):
        assert media_url == "https://cdn.example.test/master.m3u8"
        assert video_id == "demo-id"
        assert kwargs["headers"]["Referer"] == "https://player.example.test/embed/demo-id"
        return [{"url": media_url, "format_id": "hls-720"}]

    monkeypatch.setattr(SupJavIE, "_download_webpage", fake_download_webpage)
    monkeypatch.setattr(SupJavIE, "_extract_m3u8_formats", fake_extract_m3u8_formats)

    result = SupJavIE(yt_dlp.YoutubeDL({"quiet": True}))._real_extract("https://supjav.com/watch/demo-id")

    assert result["id"] == "demo-id"
    assert result["formats"] == [{"url": "https://cdn.example.test/master.m3u8", "format_id": "hls-720"}]
