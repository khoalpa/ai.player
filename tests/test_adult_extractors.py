from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

from yt_dlp import YoutubeDL

from ai_player.services.adult_extractors import supported_adult_host_summary, supported_adult_hosts

PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "plugins" / "ai-player-adult-extractors"
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

ADULT_SITES = import_module("yt_dlp_plugins.extractor.adult_sites")
ADULT_PROBE = import_module("scripts.probe_adult_site")
VLXXIE = ADULT_SITES.VLXXIE
NJAVIE = ADULT_SITES.NJAVIE
GenericAdultIE = ADULT_SITES.GenericAdultIE
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "adult_extractors"


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


def test_adult_site_registry_lists_internal_hosts() -> None:
    assert "missav.ai" in ADULT_SITES.ADULT_SITE_HOSTS
    assert "vlxx.*" in ADULT_SITES.ADULT_SITE_HOSTS
    assert "eporner.com" in ADULT_SITES.ADULT_SITE_HOSTS
    assert "pornhub.com" in ADULT_SITES.ADULT_SITE_HOSTS
    assert "manyvids.com" in ADULT_SITES.ADULT_SITE_HOSTS
    assert "thisvid.com" in ADULT_SITES.ADULT_SITE_HOSTS
    assert "fc2.com" in ADULT_SITES.ADULT_SITE_HOSTS
    assert "jable.tv" in ADULT_SITES.ADULT_SITE_HOSTS
    assert "hellporno.com" in ADULT_SITES.ADULT_SITE_HOSTS
    assert "members.nubiles-porn.com" in ADULT_SITES.ADULT_SITE_HOSTS
    assert "txxx.com" in ADULT_SITES.ADULT_SITE_HOSTS
    assert "myvidster.com" in ADULT_SITES.ADULT_SITE_HOSTS
    assert "videos.toypics.net" in ADULT_SITES.ADULT_SITE_HOSTS
    assert ADULT_SITES.SITE_REGISTRY["njav"]["iframe_depth"] == 2
    assert ADULT_SITES.SITE_REGISTRY["eporner"]["delegate_to_ytdlp"] is True
    assert ADULT_SITES.SITE_REGISTRY["manyvids"]["delegate_to_ytdlp"] is True
    assert ADULT_SITES.SITE_REGISTRY["hellporno"]["delegate_to_ytdlp"] is True
    assert ADULT_SITES.SITE_REGISTRY["myvidster"]["delegate_to_ytdlp"] is True
    assert ADULT_SITES.SITE_REGISTRY["jable"]["iframe_depth"] == 2


def test_supported_adult_hosts_service_lists_registry_modes() -> None:
    rows = {row.site_key: row for row in supported_adult_hosts()}
    summary = supported_adult_host_summary()

    assert rows["hellporno"].mode == "yt-dlp native"
    assert "hellporno.com" in rows["hellporno"].domains
    assert "delegated to yt-dlp" in rows["hellporno"].description
    assert rows["hellporno"].open_url == "https://hellporno.com"
    assert rows["jable"].mode == "generic"
    assert "JAV/Asia" in rows["jable"].description
    assert rows["jable"].iframe_depth == 2
    assert rows["jable"].open_url == "https://jable.tv"
    assert rows["vlxx"].open_url == ""
    assert summary["sites"] == len(rows)
    assert summary["hosts"] >= len(rows)
    assert summary["delegate"] > summary["generic"]


def test_generic_adult_ie_skips_native_ytdlp_delegate_hosts() -> None:
    assert not GenericAdultIE.suitable("https://www.eporner.com/video-demo/demo-title/")
    assert not GenericAdultIE.suitable("https://www.pornhub.com/view_video.php?viewkey=demo")
    assert not GenericAdultIE.suitable("https://www.manyvids.com/Video/123/demo/")
    assert not GenericAdultIE.suitable("https://video.fc2.com/en/content/20200101demo/")
    assert not GenericAdultIE.suitable("https://hellporno.com/videos/demo/")
    assert not GenericAdultIE.suitable("https://members.nubiles-porn.com/video/watch/12345/demo")
    assert not GenericAdultIE.suitable("https://txxx.com/videos/12345/demo/")
    assert not GenericAdultIE.suitable("https://www.myvidster.com/video/12345")


def test_generic_adult_ie_matches_jav_asia_registry_hosts() -> None:
    assert GenericAdultIE.suitable("https://jable.tv/videos/demo/")
    assert GenericAdultIE.suitable("https://netflav.com/video?id=demo")
    assert GenericAdultIE.suitable("https://avgle.com/video/123/demo")


def test_site_profile_adds_language_header() -> None:
    headers = VLXXIE._adult_site_headers("https://vlxx.moi/video/demo-title/3170/")

    assert headers["Referer"] == "https://vlxx.moi/video/demo-title/3170/"
    assert headers["Accept-Language"].startswith("vi-VN")
    assert "Origin" not in headers
    assert not any(key.startswith("Sec-Fetch-") for key in headers)


def test_generic_adult_ie_only_matches_registry_hosts(monkeypatch) -> None:
    monkeypatch.setitem(
        ADULT_SITES.SITE_REGISTRY,
        "example_generic",
        {"domains": ["new-adult.example"], "iframe_depth": 2},
    )

    assert GenericAdultIE.suitable("https://new-adult.example/watch/demo")
    assert not GenericAdultIE.suitable("https://not-allowed.example/watch/demo")


def test_generic_adult_ie_uses_registry_media_patterns(monkeypatch) -> None:
    monkeypatch.setitem(
        ADULT_SITES.SITE_REGISTRY,
        "example_patterns",
        {
            "domains": ["pattern.example"],
            "media_patterns": [r"""data-stream=["'](?P<url>[^"']+)["']"""],
        },
    )
    extractor = GenericAdultIE(YoutubeDL({"quiet": True, "no_warnings": True}))

    result = extractor._extract_from_webpage(
        "https://pattern.example/watch/demo",
        "demo",
        """<html><body><div data-stream="/media/demo.mp4"></div></body></html>""",
        iframe_depth=0,
    )

    assert result["formats"][0]["url"] == "https://pattern.example/media/demo.mp4"


def test_generic_adult_ie_uses_registry_iframe_patterns(monkeypatch) -> None:
    monkeypatch.setitem(
        ADULT_SITES.SITE_REGISTRY,
        "example_iframe_patterns",
        {
            "domains": ["frame.example"],
            "iframe_patterns": [{"pattern": r"""data-player=["'](?P<url>[^"']+)["']"""}],
        },
    )
    extractor = GenericAdultIE(YoutubeDL({"quiet": True, "no_warnings": True}))

    assert (
        extractor._find_iframe_url(
            "https://frame.example/watch/demo",
            """<div data-player="/embed/demo"></div>""",
        )
        == "https://frame.example/embed/demo"
    )


def test_generic_adult_ie_reads_common_html_and_json_media_urls(monkeypatch) -> None:
    monkeypatch.setitem(
        ADULT_SITES.SITE_REGISTRY,
        "example_common_player",
        {"domains": ["common-player.example"]},
    )
    extractor = GenericAdultIE(YoutubeDL({"quiet": True, "no_warnings": True}))

    result = extractor._extract_from_webpage(
        "https://common-player.example/watch/demo",
        "demo",
        """
        <html>
          <head><meta itemprop="contentUrl" content="/media/meta-demo.mp4"></head>
          <body>
            <script type="application/json">{"streamUrl":"/media/json-demo.webm","sources":"/media/source-demo.mp4"}</script>
            <script>jwplayer("demo").setup({sources: [{file: "/media/jwplayer-demo.mp4", label: "720p"}]});</script>
            <script>videojs("demo").src([{src: "/media/videojs-demo.mp4", type: "video/mp4"}]);</script>
            <script>quality_720p = "/media/quality-demo.mp4";</script>
          </body>
        </html>
        """,
        iframe_depth=0,
    )

    assert {item["url"] for item in result["formats"]} == {
        "https://common-player.example/media/meta-demo.mp4",
        "https://common-player.example/media/json-demo.webm",
        "https://common-player.example/media/source-demo.mp4",
        "https://common-player.example/media/jwplayer-demo.mp4",
        "https://common-player.example/media/videojs-demo.mp4",
        "https://common-player.example/media/quality-demo.mp4",
    }


def test_generic_adult_ie_reads_common_iframe_attributes() -> None:
    extractor = GenericAdultIE(YoutubeDL({"quiet": True, "no_warnings": True}))

    assert (
        extractor._find_iframe_url(
            "https://frame.example/watch/demo",
            """<iframe data-player-src="/player/demo"></iframe>""",
        )
        == "https://frame.example/player/demo"
    )


def test_probe_registry_draft_delegates_to_native_ytdlp() -> None:
    draft = ADULT_PROBE._registry_draft(
        "eporner",
        "eporner.com",
        accept_language="en-US,en;q=0.9",
        iframe_url=None,
        native_ytdlp_extractors=["eporner"],
    )

    assert draft == {"eporner": {"domains": ["eporner.com"], "delegate_to_ytdlp": True}}
    assert ADULT_PROBE._suggested_registry_mode(["eporner"]) == "delegate_to_ytdlp"


def test_probe_registry_draft_uses_generic_when_no_native_extractor() -> None:
    draft = ADULT_PROBE._registry_draft(
        "new_site",
        "new-site.example",
        accept_language="en-US,en;q=0.9",
        iframe_url="https://player.example/embed/demo",
        native_ytdlp_extractors=[],
    )

    assert draft == {
        "new_site": {
            "domains": ["new-site.example"],
            "iframe_depth": 2,
            "accept_language": "en-US,en;q=0.9",
            "media_patterns": [],
            "iframe_patterns": [],
        }
    }
    assert ADULT_PROBE._suggested_registry_mode([]) == "generic"


def test_probe_native_ytdlp_candidates_ignore_plugin_and_generic_extractors(monkeypatch) -> None:
    class NativeIE:
        IE_NAME = "native_site"
        __module__ = "yt_dlp.extractor.native_site"

        @classmethod
        def suitable(cls, _url):
            return True

    class PluginIE:
        IE_NAME = "plugin_site"
        __module__ = "yt_dlp_plugins.extractor.plugin_site"

        @classmethod
        def suitable(cls, _url):
            return True

    class GenericIE:
        IE_NAME = "generic"
        __module__ = "yt_dlp.extractor.generic"

        @classmethod
        def suitable(cls, _url):
            return True

    class NonMatchingIE:
        IE_NAME = "non_matching"
        __module__ = "yt_dlp.extractor.non_matching"

        @classmethod
        def suitable(cls, _url):
            return False

    class FakeYoutubeDL:
        def __init__(self, _options):
            self._ies = {
                "Native": NativeIE,
                "Plugin": PluginIE,
                "Generic": GenericIE,
                "NonMatching": NonMatchingIE,
            }

    monkeypatch.setattr(ADULT_PROBE, "YoutubeDL", FakeYoutubeDL)

    assert ADULT_PROBE._matching_native_ytdlp_extractors("https://native.example/watch/demo") == ["native_site"]


def test_site_registry_merge_extends_profiles() -> None:
    merged = ADULT_SITES._merge_site_registry(
        {"demo": {"domains": ["demo.example"], "iframe_depth": 1}},
        {"demo": {"iframe_depth": 3}, "new": {"domains": ["new.example"]}},
    )

    assert merged["demo"] == {"domains": ["demo.example"], "iframe_depth": 3}
    assert merged["new"] == {"domains": ["new.example"]}


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


def test_base_extractor_reads_nested_next_data_media_urls(monkeypatch) -> None:
    extractor = VLXXIE(YoutubeDL({"quiet": True, "no_warnings": True}))
    monkeypatch.setattr(
        extractor,
        "_extract_m3u8_formats",
        lambda media_url, *_args, **_kwargs: [{"url": media_url, "format_id": "hls"}],
    )

    result = extractor._extract_from_webpage(
        "https://vlxx.moi/video/demo-title/3170/",
        "3170",
        (FIXTURE_ROOT / "nested_next_data.html").read_text(encoding="utf-8"),
        iframe_depth=0,
    )

    assert {item["url"] for item in result["formats"]} == {
        "https://vlxx.moi/media/demo-360.mp4",
        "https://cdn.example.test/demo-720.m3u8?token=abc",
    }


def test_base_extractor_reads_initial_state_media_urls() -> None:
    extractor = NJAVIE(YoutubeDL({"quiet": True, "no_warnings": True}))

    result = extractor._extract_from_webpage(
        "https://www.njav.com/vi/xvideos/rki-729-uncensored-leak",
        "rki-729-uncensored-leak",
        (FIXTURE_ROOT / "state_payload.html").read_text(encoding="utf-8"),
        iframe_depth=0,
    )

    assert result["formats"] == [
        {
            "url": "https://cdn.example.test/state-video.webm",
            "ext": "webm",
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
        "formats": [
            {
                "url": hls_url,
                "format_id": "hls-720p",
                "height": 720,
                "http_headers": NJAVIE._adult_site_headers(final_player_url),
            }
        ],
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

    assert formats == [
        {
            "url": "https://cdn.example.test/manifest-s1/03170.vl",
            "format_id": "hls",
            "http_headers": VLXXIE._adult_site_headers("https://play.vlstream.net/embed/token/s1"),
        }
    ]
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
