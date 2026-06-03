from __future__ import annotations

from collections.abc import Callable, Iterable
from urllib.parse import parse_qs, urlparse

from ai_player.services.youtube_channel import is_youtube_channel_url, is_youtube_playlist_url

CHANNEL_MEDIA_FILTERS = {"all", "video", "photo", "document", "audio", "text", "blacklist"}


def current_channel_provider(provider: object = "", pending_url: object = "") -> str:
    normalized = str(provider or "").strip().lower()
    if normalized:
        return normalized
    url = str(pending_url or "")
    if is_youtube_channel_url(url) or is_youtube_playlist_url(url):
        return "youtube"
    return "telegram"


def youtube_video_id_from_url(url: object) -> str:
    parsed = urlparse(str(url or "").strip())
    return str(parse_qs(parsed.query).get("v", [""])[0] or "")


def telegram_post_id_from_url(url: object) -> str:
    parts = [part for part in urlparse(str(url or "").strip()).path.strip("/").split("/") if part]
    if len(parts) == 2 and parts[1].isdigit():
        return parts[1]
    return ""


def telegram_channel_key(url: object) -> str:
    parsed = urlparse(str(url or "").strip())
    host = parsed.netloc.lower()
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if host not in {"t.me", "telegram.me"}:
        return ""
    if len(parts) >= 2 and parts[0] == "s":
        return f"{host}/{parts[1].lower()}"
    if len(parts) >= 3 and parts[0] == "c":
        return f"{host}/c/{parts[1]}"
    if parts:
        return f"{host}/{parts[0].lower()}"
    return ""


def normalize_channel_filter(value: object) -> str:
    normalized = str(value or "all")
    return normalized if normalized in CHANNEL_MEDIA_FILTERS else "all"


def channel_item_media_kind(channel_item: object) -> str:
    media_kind = str(getattr(channel_item, "media_kind", "") or "").strip().lower()
    if media_kind:
        return media_kind
    return "video" if getattr(channel_item, "has_video", True) else "text"


def channel_item_search_text(
    channel_item: object,
    *,
    translation_for_item: Callable[[object], object] | None = None,
) -> str:
    translation = translation_for_item(channel_item) if translation_for_item is not None else ""
    return " ".join(
        str(value or "")
        for value in (
            getattr(channel_item, "title", ""),
            getattr(channel_item, "text", ""),
            translation,
            getattr(channel_item, "file_name", ""),
            getattr(channel_item, "duration", ""),
            getattr(channel_item, "url", ""),
            getattr(channel_item, "media_url", ""),
            channel_item_media_kind(channel_item),
            getattr(channel_item, "post_id", ""),
            getattr(channel_item, "date", ""),
        )
    ).lower()


def filter_channel_items(
    items: Iterable[object] | None,
    *,
    media_filter: object = "all",
    query: object = "",
    is_blacklisted: Callable[[object], bool],
    translation_for_item: Callable[[object], object] | None = None,
) -> list[object]:
    normalized_filter = normalize_channel_filter(media_filter)
    normalized_query = " ".join(str(query or "").lower().split())
    filtered = []
    for item in list(items or []):
        blacklisted = is_blacklisted(item)
        if normalized_filter == "blacklist":
            if not blacklisted:
                continue
        elif blacklisted:
            continue

        media_kind = channel_item_media_kind(item)
        if normalized_filter not in {"all", "blacklist"} and media_kind != normalized_filter:
            continue
        if normalized_query and normalized_query not in channel_item_search_text(
            item,
            translation_for_item=translation_for_item,
        ):
            continue
        filtered.append(item)
    return filtered
