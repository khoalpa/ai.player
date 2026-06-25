from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

from yt_dlp import YoutubeDL

PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "plugins" / "ai-player-adult-extractors"
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

VLXXIE = import_module("yt_dlp_plugins.extractor.adult_sites").VLXXIE
NJAVIE = import_module("yt_dlp_plugins.extractor.adult_sites").NJAVIE


class _FakeHeadResponse:
    def __init__(self, content_type: str) -> None:
        self.headers = {"Content-Type": content_type}

    def close(self) -> None:
        pass


def test_vlxx_ie_matches_video_urls() -> None:
    assert VLXXIE.suitable("https://vlxx.moi/video/demo-title/3170/")
    assert VLXXIE.suitable("https://www.vlxx.example/video/demo-title/3170/")
    assert not VLXXIE.suitable("https://example.com/video/demo-title/3170/")


def test_njav_ie_matches_video_urls() -> None:
    assert NJAVIE.suitable("https://www.njav.com/vi/xvideos/rki-729-uncensored-leak")
    assert NJAVIE.suitable("https://njav.com/xvideos/rki-729-uncensored-leak")
    assert not NJAVIE.suitable("https://example.com/vi/xvideos/rki-729-uncensored-leak")


def test_njav_ie_extracts_mp4_url_from_webpage() -> None:
    extractor = NJAVIE(YoutubeDL({"quiet": True, "no_warnings": True}))

    result = extractor._extract_from_webpage(
        "https://www.njav.com/vi/xvideos/rki-729-uncensored-leak",
        "rki-729-uncensored-leak",
        """
        <html>
          <head><meta property="og:title" content="Demo title"></head>
          <body><script>window.videoUrl = "https:\\/\\/cdn.example.test\\/demo.mp4";</script></body>
        </html>
        """,
        iframe_depth=0,
    )

    assert result["id"] == "rki-729-uncensored-leak"
    assert result["title"] == "Demo title"
    assert result["age_limit"] == 18
    assert result["formats"] == [
        {
            "url": "https://cdn.example.test/demo.mp4",
            "ext": "mp4",
            "http_headers": NJAVIE._adult_site_headers(
                "https://www.njav.com/vi/xvideos/rki-729-uncensored-leak",
            ),
        }
    ]


def test_njav_ie_follows_embed_player_and_hls_url() -> None:
    extractor = NJAVIE(YoutubeDL({"quiet": True, "no_warnings": True}))
    page_url = "https://www.njav.com/vi/xvideos/rki-729-uncensored-leak"
    embed_url = extractor._njav_embed_url(
        page_url,
        """
        <script type="application/ld+json">
        {"embedUrl":"https://www.njav.com/vv/rki-729-uncensored-leak?poster=https://static.example.test/thumb.webp"}
        </script>
        """,
    )
    player_url = extractor._njav_player_url(
        embed_url,
        """<script>videoFrame.src = "/jm/token";</script>""",
    )
    m3u8_url = extractor._njav_m3u8_url(
        "https://upload18.org/play/index/rki-729-uncensored-leak",
        """<script>window.PLAYER_CONFIG = {m3u8: "/play/token_hash?hash=abc&amp;x=1"};</script>""",
    )

    assert embed_url == "https://www.njav.com/vv/rki-729-uncensored-leak?poster=https://static.example.test/thumb.webp"
    assert player_url == "https://www.njav.com/jm/token"
    assert m3u8_url == "https://upload18.org/play/token_hash?hash=abc&x=1"


def test_njav_ie_real_extract_follows_embed_player_and_hls(monkeypatch) -> None:
    extractor = NJAVIE(YoutubeDL({"quiet": True, "no_warnings": True}))
    page_url = "https://www.njav.com/vi/xvideos/rki-729-uncensored-leak"
    embed_url = "https://www.njav.com/vv/rki-729-uncensored-leak"
    player_url = "https://www.njav.com/jm/token"
    final_player_url = "https://upload18.org/play/index/rki-729-uncensored-leak"
    hls_url = "https://upload18.org/play/token_hash?hash=abc&x=1"
    downloaded_pages = []
    m3u8_calls = []

    class FakeUrlHandle:
        def geturl(self) -> str:
            return final_player_url

    def fake_download_webpage(url, video_id, note=None, headers=None):
        downloaded_pages.append((url, video_id, note, headers))
        if url == page_url:
            return f"""
            <html>
              <head>
                <meta property="og:title" content="Demo NJAV title">
                <meta property="og:image" content="/thumb.webp">
              </head>
              <body><script>{{"embedUrl":"{embed_url}"}}</script></body>
            </html>
            """
        if url == embed_url:
            return f"""<script>videoFrame.src = "{player_url}";</script>"""
        raise AssertionError(f"Unexpected webpage URL: {url}")

    def fake_download_webpage_handle(url, video_id, note=None, headers=None):
        assert url == player_url
        assert video_id == "rki-729-uncensored-leak"
        assert "player frame" in note
        assert headers == NJAVIE._adult_site_headers(embed_url)
        return (
            """<script>window.PLAYER_CONFIG = {m3u8: "/play/token_hash?hash=abc&amp;x=1"};</script>""",
            FakeUrlHandle(),
        )

    def fake_extract_m3u8_formats(media_url, video_id, ext, m3u8_id, fatal, headers):
        m3u8_calls.append(
            {
                "media_url": media_url,
                "video_id": video_id,
                "ext": ext,
                "m3u8_id": m3u8_id,
                "fatal": fatal,
                "headers": headers,
            }
        )
        return [{"url": media_url, "format_id": "hls-720p", "height": 720}]

    monkeypatch.setattr(extractor, "_download_webpage", fake_download_webpage)
    monkeypatch.setattr(extractor, "_download_webpage_handle", fake_download_webpage_handle)
    monkeypatch.setattr(extractor, "_extract_m3u8_formats", fake_extract_m3u8_formats)

    result = extractor._real_extract(page_url)

    assert result == {
        "id": "rki-729-uncensored-leak",
        "title": "Demo NJAV title",
        "thumbnail": "https://www.njav.com/thumb.webp",
        "age_limit": 18,
        "formats": [{"url": hls_url, "format_id": "hls-720p", "height": 720}],
    }
    assert downloaded_pages == [
        (page_url, "rki-729-uncensored-leak", None, NJAVIE._adult_site_headers(page_url)),
        (
            embed_url,
            "rki-729-uncensored-leak",
            "Downloading embedded player webpage",
            NJAVIE._adult_site_headers(page_url),
        ),
    ]
    assert m3u8_calls == [
        {
            "media_url": hls_url,
            "video_id": "rki-729-uncensored-leak",
            "ext": "mp4",
            "m3u8_id": "hls",
            "fatal": False,
            "headers": NJAVIE._adult_site_headers(final_player_url),
        }
    ]


def test_vlxx_ie_extracts_mp4_url_from_webpage() -> None:
    extractor = VLXXIE(YoutubeDL({"quiet": True, "no_warnings": True}))

    result = extractor._extract_from_webpage(
        "https://vlxx.moi/video/demo-title/3170/",
        "3170",
        """
        <html>
          <head><meta property="og:title" content="Demo title"></head>
          <body><script>window.video_url = "https:\\/\\/cdn.example.test\\/demo.mp4";</script></body>
        </html>
        """,
        iframe_depth=0,
    )

    assert result["id"] == "3170"
    assert result["title"] == "Demo title"
    assert result["age_limit"] == 18
    assert result["formats"] == [
        {
            "url": "https://cdn.example.test/demo.mp4",
            "ext": "mp4",
            "http_headers": VLXXIE._adult_site_headers("https://vlxx.moi/video/demo-title/3170/"),
        }
    ]


def test_vlxx_ie_treats_media_vl_manifest_as_hls(monkeypatch) -> None:
    extractor = VLXXIE(YoutubeDL({"quiet": True, "no_warnings": True}))
    captured = {}

    def fake_extract_m3u8_formats(media_url, video_id, ext, m3u8_id, fatal, headers):
        captured.update(
            {
                "media_url": media_url,
                "video_id": video_id,
                "ext": ext,
                "m3u8_id": m3u8_id,
                "fatal": fatal,
                "headers": headers,
            }
        )
        return [{"url": media_url, "format_id": "hls"}]

    monkeypatch.setattr(extractor, "_extract_m3u8_formats", fake_extract_m3u8_formats)
    monkeypatch.setattr(
        extractor,
        "_download_webpage",
        lambda *_args, **_kwargs: "#EXTM3U\n#EXTINF:10,\nhttps://cdn.example.test/segment-1.ts\n",
    )
    monkeypatch.setattr(
        extractor,
        "_request_webpage",
        lambda *_args, **_kwargs: _FakeHeadResponse("video/mp2t"),
    )

    formats = extractor._extract_media_formats(
        "https://play.vlstream.net/embed/token/s1",
        "3170",
        '<script>SRC = [{"type":"hls","file":"https://cdn.example.test/manifest-s1/03170.vl"}];</script>',
    )

    assert formats == [{"url": "https://cdn.example.test/manifest-s1/03170.vl", "format_id": "hls"}]
    assert captured["video_id"] == "3170"
    assert captured["ext"] == "mp4"
    assert captured["m3u8_id"] == "hls"
    assert captured["fatal"] is False
    assert captured["headers"]["Referer"] == "https://play.vlstream.net/embed/token/s1"


def test_vlxx_ie_skips_image_vl_manifest(monkeypatch) -> None:
    extractor = VLXXIE(YoutubeDL({"quiet": True, "no_warnings": True}))

    def fail_extract_m3u8_formats(*_args, **_kwargs):
        raise AssertionError("image playlist should not be extracted as video")

    monkeypatch.setattr(extractor, "_extract_m3u8_formats", fail_extract_m3u8_formats)
    monkeypatch.setattr(
        extractor,
        "_download_webpage",
        lambda *_args, **_kwargs: "#EXTM3U\n#EXTINF:10,\nhttps://cdn.example.test/image-segment\n",
    )
    monkeypatch.setattr(
        extractor,
        "_request_webpage",
        lambda *_args, **_kwargs: _FakeHeadResponse("image/png"),
    )

    assert (
        extractor._extract_media_formats(
            "https://play.vlstream.net/embed/token/s1",
            "3170",
            '<script>SRC = [{"type":"hls","file":"https://cdn.example.test/manifest-s1/03170.vl"}];</script>',
        )
        == []
    )


def test_vlxx_ie_uses_ajax_player_iframe(monkeypatch) -> None:
    extractor = VLXXIE(YoutubeDL({"quiet": True, "no_warnings": True}))
    captured_payloads = []
    extracted = {}

    def fake_download_webpage(url, video_id, headers):
        assert url == "https://vlxx.moi/video/demo-title/3170/"
        assert video_id == "3170"
        assert headers["Referer"] == url
        return '<div id="video" data-id="3170" data-sv="1"></div><li onclick="server(2,3170)"></li>'

    def fake_download_json(url, video_id, note, data, headers, fatal):
        captured_payloads.append(data.decode())
        assert url == "https://vlxx.moi/ajax.php"
        assert video_id == "3170"
        assert "server" in note
        assert headers["X-Requested-With"] == "XMLHttpRequest"
        assert fatal is False
        return {"player": '<iframe src="https://play.example.test/embed/token/s1"></iframe>'}

    def fake_extract_from_webpage(url, video_id, webpage, iframe_depth):
        extracted["webpage"] = webpage
        assert url == "https://vlxx.moi/video/demo-title/3170/"
        assert video_id == "3170"
        assert iframe_depth == 2
        return {"id": video_id, "title": "Demo", "formats": []}

    monkeypatch.setattr(extractor, "_download_webpage", fake_download_webpage)
    monkeypatch.setattr(extractor, "_download_json", fake_download_json)
    monkeypatch.setattr(extractor, "_extract_from_webpage", fake_extract_from_webpage)

    assert extractor._real_extract("https://vlxx.moi/video/demo-title/3170/") == {
        "id": "3170",
        "title": "Demo",
        "formats": [],
    }
    assert captured_payloads[:2] == ["vlxx_server=1&id=3170&server=2", "vlxx_server=1&id=3170&server=1"]
    assert '<iframe src="https://play.example.test/embed/token/s1"></iframe>' in extracted["webpage"]
