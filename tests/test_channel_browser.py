from __future__ import annotations

from types import SimpleNamespace

from ai_player.ui import channel_browser


def test_channel_browser_detects_provider_and_ids() -> None:
    assert channel_browser.current_channel_provider("", "https://www.youtube.com/@demo") == "youtube"
    assert channel_browser.current_channel_provider("", "https://www.youtube.com/playlist?list=PLdemo") == "youtube"
    assert channel_browser.current_channel_provider("", "https://t.me/demo") == "telegram"
    assert channel_browser.current_channel_provider("youtube", "https://t.me/demo") == "youtube"
    assert channel_browser.youtube_video_id_from_url("https://www.youtube.com/watch?v=abc&list=PLdemo") == "abc"
    assert channel_browser.telegram_post_id_from_url("https://t.me/demo/123") == "123"
    assert channel_browser.telegram_post_id_from_url("https://t.me/demo") == ""


def test_telegram_channel_key_normalizes_public_preview_and_private_urls() -> None:
    assert channel_browser.telegram_channel_key("https://t.me/Demo/123") == "t.me/demo"
    assert channel_browser.telegram_channel_key("https://telegram.me/s/Demo/123") == "telegram.me/demo"
    assert channel_browser.telegram_channel_key("https://t.me/c/12345/678") == "t.me/c/12345"
    assert channel_browser.telegram_channel_key("https://example.com/Demo") == ""


def test_filter_channel_items_handles_blacklist_media_kind_and_search() -> None:
    items = [
        SimpleNamespace(title="Demo video", text="", url="https://t.me/demo/1", post_id="1"),
        SimpleNamespace(title="Photo item", text="", url="https://t.me/demo/2", post_id="2", media_kind="photo"),
        SimpleNamespace(title="Needs translation", text="", url="https://t.me/demo/3", post_id="3"),
        SimpleNamespace(title="Blocked", text="", url="https://t.me/demo/4", post_id="4"),
    ]
    blacklisted = {id(items[3])}
    translations = {id(items[2]): "translated needle"}

    def is_blacklisted(item) -> bool:
        return id(item) in blacklisted

    def translation_for_item(item) -> str:
        return translations.get(id(item), "")

    assert channel_browser.filter_channel_items(items, is_blacklisted=is_blacklisted) == items[:3]
    assert channel_browser.filter_channel_items(items, media_filter="blacklist", is_blacklisted=is_blacklisted) == [
        items[3]
    ]
    assert channel_browser.filter_channel_items(items, media_filter="photo", is_blacklisted=is_blacklisted) == [
        items[1]
    ]
    assert channel_browser.filter_channel_items(
        items,
        query="translated needle",
        is_blacklisted=is_blacklisted,
        translation_for_item=translation_for_item,
    ) == [items[2]]


def test_channel_item_media_kind_defaults_from_has_video() -> None:
    assert channel_browser.channel_item_media_kind(SimpleNamespace(has_video=True)) == "video"
    assert channel_browser.channel_item_media_kind(SimpleNamespace(has_video=False)) == "text"
    assert channel_browser.normalize_channel_filter("unknown") == "all"
