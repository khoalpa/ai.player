from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from ai_player.services import telegram_channel

SAMPLE_CHANNEL_HTML = """
<div class="tgme_widget_message" data-post="shunv8388/101">
  <div class="tgme_widget_message_text">First image only</div>
</div>
<div class="tgme_widget_message" data-post="shunv8388/102">
  <a class="tgme_widget_message_video_player" href="/shunv8388/102">
    <i class="tgme_widget_message_video_thumb" style="background-image:url('/file/thumb102.jpg')"></i>
    <span class="message_video_duration">02:36</span>
  </a>
  <div class="tgme_widget_message_text">Demo <b>video</b><br/>caption</div>
</div>
<div class="tgme_widget_message" data-post="shunv8388/103">
  <video src="https://cdn.example.test/video.mp4"></video>
  <time datetime="2026-05-28T10:30:00+00:00"></time>
</div>
"""


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://t.me/shunv8388", True),
        ("https://t.me/s/shunv8388", True),
        ("https://telegram.me/shunv8388", True),
        ("https://t.me/shunv8388/123", True),
        ("https://web.telegram.org/a/progressive/document123", False),
        ("https://example.com/shunv8388", False),
    ],
)
def test_is_telegram_channel_url(url: str, expected: bool) -> None:
    assert telegram_channel.is_telegram_channel_url(url) is expected


def test_parse_telegram_channel_videos_extracts_public_video_posts() -> None:
    videos = telegram_channel.parse_telegram_channel_videos(SAMPLE_CHANNEL_HTML, "shunv8388")

    assert [video.url for video in videos] == [
        "https://t.me/shunv8388/102",
        "https://t.me/shunv8388/103",
    ]
    assert videos[0].title == "Demo video caption [02:36]"
    assert videos[0].thumbnail_url == "https://t.me/file/thumb102.jpg"
    assert videos[1].title == "#103 2026-05-28 10:30"
    assert videos[1].media_url == "https://cdn.example.test/video.mp4"


def test_parse_telegram_channel_items_keeps_text_posts_for_browser() -> None:
    items = telegram_channel.parse_telegram_channel_items(SAMPLE_CHANNEL_HTML, "shunv8388")

    assert [item.post_id for item in items] == ["101", "102", "103"]
    assert items[0].title == "First image only"
    assert items[0].has_video is False
    assert items[0].media_kind == "text"
    assert items[1].has_video is True
    assert items[1].media_kind == "video"
    assert items[1].text == "Demo video caption"
    assert items[1].media_count == 1


def test_parse_telegram_channel_items_keeps_full_caption_text() -> None:
    long_caption = " ".join(f"word{i}" for i in range(40))
    html = f"""
    <div class="tgme_widget_message" data-post="shunv8388/104">
      <a class="tgme_widget_message_photo_wrap" style="background-image:url('/file/photo104.jpg')"></a>
      <img src="/file/photo104-b.jpg"/>
      <div class="tgme_widget_message_text">{long_caption}</div>
      <time datetime="2026-05-28T10:30:00+00:00"></time>
    </div>
    """

    items = telegram_channel.parse_telegram_channel_items(html, "shunv8388")

    assert items[0].media_kind == "photo"
    assert items[0].text == long_caption
    assert len(items[0].title) < len(long_caption)
    assert items[0].media_count == 2


def test_parse_telegram_channel_items_filters_search() -> None:
    items = telegram_channel.parse_telegram_channel_items(SAMPLE_CHANNEL_HTML, "shunv8388", search="caption")

    assert [item.post_id for item in items] == ["102"]


def test_list_telegram_channel_videos_loads_public_preview(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        text = SAMPLE_CHANNEL_HTML

        def raise_for_status(self):
            return None

    def fake_get(url, headers, timeout):
        captured.update({"url": url, "headers": headers, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=fake_get))

    videos = telegram_channel.list_telegram_channel_videos("https://t.me/shunv8388", language_id="en")

    assert captured["url"] == "https://t.me/s/shunv8388"
    assert captured["timeout"] == 20
    assert videos[0].url == "https://t.me/shunv8388/102"


def test_list_telegram_channel_videos_reports_empty_preview(monkeypatch) -> None:
    class FakeResponse:
        text = "<html></html>"

        def raise_for_status(self):
            return None

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=lambda *_args, **_kwargs: FakeResponse()))

    with pytest.raises(telegram_channel.TelegramChannelError, match="No public video posts"):
        telegram_channel.list_telegram_channel_videos("https://t.me/shunv8388", language_id="en")


def test_list_telegram_channel_items_reports_empty_preview(monkeypatch) -> None:
    class FakeResponse:
        text = "<html></html>"

        def raise_for_status(self):
            return None

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=lambda *_args, **_kwargs: FakeResponse()))

    with pytest.raises(telegram_channel.TelegramChannelError, match="No posts"):
        telegram_channel.list_telegram_channel_items("https://t.me/shunv8388", language_id="en")


def test_private_adapter_missing_disables_login_config(monkeypatch) -> None:
    monkeypatch.setattr(telegram_channel, "_telegram_private_adapter", lambda: None)

    assert telegram_channel.telegram_private_available() is False
    assert telegram_channel.load_telegram_login_config() is None
    telegram_channel.delete_telegram_login_data()

    with pytest.raises(telegram_channel.TelegramChannelError, match="private Telegram client plugin"):
        telegram_channel.start_telegram_login(
            telegram_channel.TelegramLoginConfig(api_id=12345, api_hash="hash-secret", phone="+84901234567"),
            language_id="en",
        )


def test_authenticated_operations_forward_to_private_adapter(monkeypatch) -> None:
    calls = []
    config = telegram_channel.TelegramLoginConfig(api_id=12345, api_hash="hash-secret", phone="+84901234567")
    request = telegram_channel.TelegramLoginRequest(config=config, phone_code_hash="code-hash")
    loaded = telegram_channel.TelegramLoginConfig(api_id=67890, api_hash="cached", phone="+84000000000")
    videos = [telegram_channel.TelegramChannelVideo("Demo", "https://t.me/demo/1", "1", authenticated=True)]

    adapter = SimpleNamespace(
        load_telegram_login_config=lambda: loaded,
        delete_telegram_login_data=lambda: calls.append(("delete",)),
        start_telegram_login=lambda received, language_id=None: calls.append(("start", received, language_id))
        or request,
        complete_telegram_login=lambda received, code, password="", language_id=None: calls.append(
            ("complete", received, code, password, language_id)
        ),
        list_telegram_channel_videos_authenticated=lambda value,
        received,
        limit=50,
        before_post_id="",
        search="",
        language_id=None: calls.append(
            ("list", value, received, limit, before_post_id, search, language_id)
        )
        or videos,
        list_telegram_channel_items_authenticated=lambda value,
        received,
        limit=50,
        before_post_id="",
        search="",
        language_id=None: calls.append(
            ("items", value, received, limit, before_post_id, search, language_id)
        )
        or videos,
        download_telegram_channel_video=lambda value, post_id, received, language_id=None: calls.append(
            ("download", value, post_id, received, language_id)
        )
        or "video.mp4",
    )
    monkeypatch.setattr(telegram_channel, "_telegram_private_adapter", lambda: adapter)

    assert telegram_channel.telegram_private_available() is True
    assert telegram_channel.load_telegram_login_config() == loaded
    telegram_channel.delete_telegram_login_data()
    assert telegram_channel.start_telegram_login(config, language_id="en") == request
    telegram_channel.complete_telegram_login(request, "12345", password="secret", language_id="en")
    assert telegram_channel.list_telegram_channel_videos_authenticated(
        "https://t.me/demo", config, limit=10, before_post_id="99", search="demo", language_id="en"
    ) == videos
    assert telegram_channel.list_telegram_channel_items_authenticated(
        "https://t.me/demo", config, limit=10, before_post_id="99", search="demo", language_id="en"
    ) == videos
    assert telegram_channel.download_telegram_channel_video("https://t.me/demo", "1", config, language_id="en") == (
        "video.mp4"
    )
    assert calls == [
        ("delete",),
        ("start", config, "en"),
        ("complete", request, "12345", "secret", "en"),
        ("list", "https://t.me/demo", config, 10, "99", "demo", "en"),
        ("items", "https://t.me/demo", config, 10, "99", "demo", "en"),
        ("download", "https://t.me/demo", "1", config, "en"),
    ]


def test_authenticated_download_retries_locked_session(monkeypatch) -> None:
    calls = []
    sleeps = []
    config = telegram_channel.TelegramLoginConfig(api_id=12345, api_hash="hash-secret", phone="+84901234567")

    def download(_value, _post_id, _config, language_id=None):
        calls.append(language_id)
        if len(calls) < 3:
            raise telegram_channel.TelegramChannelError("database is locked")
        return "video.mp4"

    adapter = SimpleNamespace(download_telegram_channel_video=download)
    monkeypatch.setattr(telegram_channel, "_telegram_private_adapter", lambda: adapter)
    monkeypatch.setattr(telegram_channel.time, "sleep", lambda seconds: sleeps.append(seconds))

    assert telegram_channel.download_telegram_channel_video("https://t.me/demo", "1", config, language_id="en") == (
        "video.mp4"
    )
    assert calls == ["en", "en", "en"]
    assert sleeps == [0.35, 0.7]


def test_validate_telegram_login_config() -> None:
    assert telegram_channel.validate_telegram_login_config("12345", "hash", "+84901234567") == (
        telegram_channel.TelegramLoginConfig(api_id=12345, api_hash="hash", phone="+84901234567")
    )
