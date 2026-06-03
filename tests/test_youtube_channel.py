from __future__ import annotations

import sys
from types import SimpleNamespace

from ai_player.services import youtube_channel

SAMPLE_INITIAL_DATA = {
    "contents": {
        "twoColumnBrowseResultsRenderer": {
            "tabs": [
                {
                    "tabRenderer": {
                        "content": {
                            "richGridRenderer": {
                                "contents": [
                                    {
                                        "richItemRenderer": {
                                            "content": {
                                                "lockupViewModel": {
                                                    "contentImage": {
                                                        "thumbnailViewModel": {
                                                            "image": {
                                                                "sources": [
                                                                    {
                                                                        "url": "https://i.ytimg.com/vi/abc/hqdefault.jpg",
                                                                        "width": 168,
                                                                    },
                                                                    {
                                                                        "url": "https://i.ytimg.com/vi/abc/maxresdefault.jpg",
                                                                        "width": 1280,
                                                                    },
                                                                ]
                                                            },
                                                            "overlays": [
                                                                {
                                                                    "thumbnailBottomOverlayViewModel": {
                                                                        "badges": [
                                                                            {
                                                                                "thumbnailBadgeViewModel": {
                                                                                    "text": "1:23"
                                                                                }
                                                                            }
                                                                        ]
                                                                    }
                                                                }
                                                            ],
                                                        }
                                                    },
                                                    "metadata": {
                                                        "lockupMetadataViewModel": {
                                                            "title": {"content": "AI document processing demo"},
                                                            "metadata": {
                                                                "contentMetadataViewModel": {
                                                                    "metadataRows": [
                                                                        {
                                                                            "metadataParts": [
                                                                                {"text": {"content": "86 views"}},
                                                                                {"text": {"content": "2 months ago"}},
                                                                            ]
                                                                        }
                                                                    ]
                                                                }
                                                            },
                                                        }
                                                    },
                                                    "contentId": "abc",
                                                    "contentType": "LOCKUP_CONTENT_TYPE_VIDEO",
                                                    "rendererContext": {
                                                        "accessibilityContext": {
                                                            "label": (
                                                                "AI document processing demo 1 minute, 23 seconds"
                                                            )
                                                        }
                                                    },
                                                }
                                            }
                                        }
                                    },
                                    {
                                        "continuationItemRenderer": {
                                            "continuationEndpoint": {
                                                "continuationCommand": {"token": "next-token"}
                                            }
                                        }
                                    },
                                ]
                            }
                        }
                    }
                }
            ]
        }
    }
}


def test_youtube_channel_url_detection() -> None:
    assert youtube_channel.is_youtube_channel_url("https://www.youtube.com/@stapleai")
    assert youtube_channel.is_youtube_channel_url("https://www.youtube.com/channel/UCdemo/videos")
    assert youtube_channel.is_youtube_channel_url("https://youtube.com/c/demo")
    assert youtube_channel.is_youtube_channel_url("https://youtube.com/user/demo")
    assert not youtube_channel.is_youtube_channel_url("https://www.youtube.com/watch?v=abc")
    assert not youtube_channel.is_youtube_channel_url("https://youtu.be/abc")


def test_youtube_playlist_url_detection() -> None:
    assert youtube_channel.is_youtube_playlist_url("https://www.youtube.com/playlist?list=PLdemo")
    assert not youtube_channel.is_youtube_playlist_url("https://www.youtube.com/watch?v=abc&list=PLdemo")


def test_parse_youtube_initial_items_extracts_lockups() -> None:
    page = youtube_channel.parse_youtube_initial_items(SAMPLE_INITIAL_DATA)

    assert page.continuation == "next-token"
    assert len(page.items) == 1
    item = page.items[0]
    assert item.title == "AI document processing demo"
    assert item.url == "https://www.youtube.com/watch?v=abc"
    assert item.post_id == "abc"
    assert item.duration == "1:23"
    assert item.date == "2 months ago"
    assert item.view_count_text == "86 views"
    assert item.thumbnail_url == "https://i.ytimg.com/vi/abc/maxresdefault.jpg"
    assert item.provider == "youtube"


def test_parse_youtube_initial_items_filters_search() -> None:
    assert youtube_channel.parse_youtube_initial_items(SAMPLE_INITIAL_DATA, search="document").items
    assert not youtube_channel.parse_youtube_initial_items(SAMPLE_INITIAL_DATA, search="missing").items


def test_parse_youtube_initial_items_extracts_playlist_renderer() -> None:
    data = {
        "playlistVideoRenderer": {
            "videoId": "xyz",
            "title": {"runs": [{"text": "Playlist video"}]},
            "lengthText": {"simpleText": "3:45"},
            "thumbnail": {"thumbnails": [{"url": "https://thumb.test/xyz.jpg", "width": 320}]},
        }
    }

    page = youtube_channel.parse_youtube_initial_items(data)

    assert [(item.post_id, item.title, item.duration) for item in page.items] == [
        ("xyz", "Playlist video", "3:45")
    ]


def test_list_youtube_channel_items_loads_public_page(monkeypatch) -> None:
    captured = {}
    html = (
        '<html><script>"INNERTUBE_API_KEY":"api-key","INNERTUBE_CLIENT_VERSION":"1.2.3";'
        f"var ytInitialData = {youtube_channel.json.dumps(SAMPLE_INITIAL_DATA)};</script></html>"
    )

    class FakeResponse:
        text = html

        def raise_for_status(self):
            return None

    def fake_get(url, headers, timeout):
        captured.update({"url": url, "headers": headers, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=fake_get))

    page = youtube_channel.list_youtube_channel_items("https://www.youtube.com/@stapleai")

    assert captured["url"] == "https://www.youtube.com/@stapleai/videos"
    assert captured["timeout"] == 20
    assert page.items[0].post_id == "abc"
    assert page.continuation == "next-token"


def test_list_youtube_channel_items_uses_adapter(monkeypatch) -> None:
    returned = youtube_channel.YouTubeChannelPage(
        [youtube_channel.YouTubeChannelItem("Adapter", "https://www.youtube.com/watch?v=a", "a")],
        continuation="adapter-next",
    )
    adapter = SimpleNamespace(
        list_youtube_channel_items=lambda value, limit=50, continuation="", search="", language_id=None: returned
    )
    monkeypatch.setattr(youtube_channel, "_youtube_client_adapter", lambda: adapter)

    page = youtube_channel.list_youtube_channel_items("https://www.youtube.com/@demo", language_id="en")

    assert page == returned
