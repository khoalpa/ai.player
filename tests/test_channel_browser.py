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


def test_channel_item_summary_and_detail_lines_are_pure() -> None:
    item = SimpleNamespace(
        post_id="42",
        title="Title",
        text="Source text",
        date="2026-06-23",
        duration="1:23",
        file_name="demo-video.mp4",
        file_size=2048,
        media_count=2,
        url="https://t.me/demo/42",
        media_url="https://cdn.example/video.mp4",
    )

    summary = channel_browser.channel_item_summary_lines(
        item,
        kind_label="[Video]",
        post_id_label="#42",
        status_label="opened",
        source_text="Source text",
        translated_text="Translated text",
        format_bytes=lambda value: f"{value} B",
    )
    assert summary == [
        "[Video] #42 opened",
        "Source text",
        "Translated text",
        "2026-06-23 | 1:23 | 2048 B | demo-video.mp4",
    ]

    def format_line(key: str, values: dict[str, object]) -> str:
        return f"{key}:{','.join(f'{name}={value}' for name, value in sorted(values.items()))}"

    detail = channel_browser.channel_item_detail_lines(
        item,
        kind_label="[Video]",
        post_id_label="#42",
        status_label="opened",
        source_text="Source text",
        translated_text="Translated text",
        format_bytes=lambda value: f"{value} B",
        format_line=format_line,
    )
    assert detail[:3] == ["[Video] #42 opened", "Source text", "Translated text"]
    assert "telegram_channel_item_file_size:size=2048 B" in detail
    assert "telegram_channel_item_media_count:count=2" in detail


def test_channel_item_html_height_and_navigation_helpers() -> None:
    html = channel_browser.channel_item_html(
        ["A < B", "Translated text"],
        translated_text="Translated text",
        source_text="Source text",
        translation_color="#123456",
    )
    assert "A &lt; B" in html
    assert '<span style="color:#123456;">Translated text</span>' in html
    assert channel_browser.channel_item_height("line\n" + ("x" * 600)) > 104
    assert channel_browser.summary_excerpt("a  b\nc") == "a b c"
    assert channel_browser.summary_excerpt("abcdef", max_chars=4) == "abc..."

    items = [
        SimpleNamespace(post_id="30"),
        SimpleNamespace(post_id="10"),
        SimpleNamespace(post_id="not-a-number"),
    ]
    assert channel_browser.target_channel_row(items, "10") == 1
    assert channel_browser.target_channel_row(items, "") == -1
    assert channel_browser.oldest_telegram_post_id(items) == "10"


def test_last_channel_settings_helpers_keep_previous_values_without_pending_url() -> None:
    assert channel_browser.last_channel_url_for_settings("", "https://t.me/old") == "https://t.me/old"
    assert channel_browser.last_channel_post_id_for_settings("", configured_post_id="7") == "7"
    assert channel_browser.last_channel_search_for_settings("", configured_search="old search") == "old search"
    assert channel_browser.last_channel_filter_for_settings("", configured_filter="photo") == "photo"

    assert (
        channel_browser.last_channel_post_id_for_settings(
            "https://t.me/demo",
            current_post_id="9",
            pending_post_id="8",
            configured_post_id="7",
        )
        == "9"
    )
    assert channel_browser.last_channel_search_for_settings("https://t.me/demo", current_search="now") == "now"
    assert channel_browser.last_channel_filter_for_settings("https://t.me/demo", current_filter="bad") == "all"
