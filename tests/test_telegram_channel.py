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
        ("https://t.me/shunv8388/123", False),
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
    assert videos[1].title == "#103 2026-05-28 10:30"


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


def test_delete_telegram_login_data_removes_config_and_session_files(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "telegram_login.json"
    session_path = tmp_path / "telegram_user.session"
    config_path.write_text("{}", encoding="utf-8")
    session_path.write_text("session", encoding="utf-8")
    session_path.with_suffix(".session-journal").write_text("journal", encoding="utf-8")
    unrelated = tmp_path / "settings.json"
    unrelated.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(telegram_channel, "TELEGRAM_LOGIN_CONFIG_PATH", config_path)
    monkeypatch.setattr(telegram_channel, "TELEGRAM_SESSION_PATH", session_path)

    telegram_channel.delete_telegram_login_data()

    assert not config_path.exists()
    assert not session_path.exists()
    assert not session_path.with_suffix(".session-journal").exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"
