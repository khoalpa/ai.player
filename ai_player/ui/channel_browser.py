from __future__ import annotations

from collections.abc import Callable, Iterable
from html import escape as html_escape
from urllib.parse import parse_qs, urlparse

from ai_player.services.youtube_channel import is_youtube_channel_url, is_youtube_playlist_url

CHANNEL_MEDIA_FILTERS = {"all", "video", "photo", "document", "audio", "text", "blacklist"}


def summary_excerpt(value: object, *, max_chars: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 1].rstrip()}..."


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


def channel_item_summary_lines(
    channel_item: object,
    *,
    kind_label: str,
    post_id_label: str = "",
    status_label: str = "",
    source_text: str = "",
    translated_text: str = "",
    format_bytes: Callable[[int], str],
) -> list[str]:
    heading_parts = [kind_label]
    if post_id_label:
        heading_parts.append(post_id_label)
    if status_label:
        heading_parts.append(status_label)
    lines = [" ".join(heading_parts)]

    if source_text:
        lines.append(summary_excerpt(source_text))
    if translated_text and translated_text != source_text:
        lines.append(summary_excerpt(translated_text))

    details = channel_item_summary_details(channel_item, format_bytes=format_bytes)
    if details:
        lines.append(" | ".join(details))
    return lines


def channel_item_summary_details(
    channel_item: object,
    *,
    format_bytes: Callable[[int], str],
) -> list[str]:
    details = []
    date = str(getattr(channel_item, "date", "") or "").strip()
    if date:
        details.append(date)
    duration = str(getattr(channel_item, "duration", "") or "").strip()
    if duration:
        details.append(duration)
    file_size = int(getattr(channel_item, "file_size", 0) or 0)
    if file_size:
        details.append(format_bytes(file_size))
    file_name = str(getattr(channel_item, "file_name", "") or "").strip()
    if file_name:
        details.append(summary_excerpt(file_name, max_chars=70))
    return details


def channel_item_detail_lines(
    channel_item: object,
    *,
    kind_label: str,
    post_id_label: str = "",
    status_label: str = "",
    source_text: str = "",
    translated_text: str = "",
    format_bytes: Callable[[int], str],
    format_line: Callable[[str, dict[str, object]], str],
) -> list[str]:
    heading_parts = [kind_label]
    if post_id_label:
        heading_parts.append(post_id_label)
    if status_label:
        heading_parts.append(status_label)
    lines = [" ".join(heading_parts)]

    text = str(getattr(channel_item, "text", "") or "").strip()
    title = str(getattr(channel_item, "title", "") or "").strip()
    if text:
        lines.append(text)
    elif title:
        lines.append(title)
    if translated_text and translated_text != source_text:
        lines.append(translated_text)

    date = str(getattr(channel_item, "date", "") or "").strip()
    if date:
        lines.append(format_line("telegram_channel_item_date", {"date": date}))
    duration = str(getattr(channel_item, "duration", "") or "").strip()
    if duration:
        lines.append(format_line("telegram_channel_item_duration", {"duration": duration}))
    file_name = str(getattr(channel_item, "file_name", "") or "").strip()
    if file_name:
        lines.append(format_line("telegram_channel_item_file_name", {"name": file_name}))
    file_size = int(getattr(channel_item, "file_size", 0) or 0)
    if file_size:
        lines.append(format_line("telegram_channel_item_file_size", {"size": format_bytes(file_size)}))
    media_count = int(getattr(channel_item, "media_count", 0) or 0)
    if media_count > 1:
        lines.append(format_line("telegram_channel_item_media_count", {"count": media_count}))
    url = str(getattr(channel_item, "url", "") or "").strip()
    if url:
        lines.append(format_line("telegram_channel_item_link", {"url": url}))
    media_url = str(getattr(channel_item, "media_url", "") or "").strip()
    if media_url:
        lines.append(format_line("telegram_channel_item_media_url", {"url": media_url}))
    return lines


def channel_item_html(
    lines: Iterable[object],
    *,
    translated_text: str = "",
    source_text: str = "",
    translation_color: str,
) -> str:
    translated_summary = summary_excerpt(translated_text) if translated_text else ""
    html_lines = []
    for line in lines:
        text = html_escape(str(line or ""))
        if translated_text and translated_text != source_text and line in {translated_text, translated_summary}:
            text = f'<span style="color:{translation_color};">{text}</span>'
        html_lines.append(text)
    return "<br>".join(html_lines)


def channel_item_height(
    label: object,
    *,
    chars_per_line: int = 96,
    line_height: int = 18,
    min_height: int = 104,
    padding: int = 14,
) -> int:
    text = str(label or "")
    line_count = 0
    for line in text.splitlines() or [""]:
        line_count += max(1, (len(line) + chars_per_line - 1) // chars_per_line)
    return max(min_height, line_count * line_height + padding)


def target_channel_row(items: Iterable[object] | None, target_post_id: object) -> int:
    target = str(target_post_id or "")
    if not target:
        return -1
    for index, item in enumerate(list(items or [])):
        if str(getattr(item, "post_id", "") or "") == target:
            return index
    return -1


def oldest_telegram_post_id(items: Iterable[object] | None) -> str:
    post_ids = []
    for item in list(items or []):
        post_id = str(getattr(item, "post_id", "") or "")
        if post_id.isdigit():
            post_ids.append(int(post_id))
    return str(min(post_ids)) if post_ids else ""


def last_channel_url_for_settings(pending_url: object, configured_url: object) -> str:
    return str(pending_url or configured_url or "")


def last_channel_post_id_for_settings(
    pending_url: object,
    *,
    current_post_id: object = "",
    pending_post_id: object = "",
    configured_post_id: object = "",
) -> str:
    if not pending_url:
        return str(configured_post_id or "")
    return str(current_post_id or pending_post_id or configured_post_id or "")


def last_channel_search_for_settings(
    pending_url: object,
    *,
    current_search: object = "",
    configured_search: object = "",
) -> str:
    if not pending_url:
        return str(configured_search or "")
    return str(current_search or "")


def last_channel_filter_for_settings(
    pending_url: object,
    *,
    current_filter: object = "",
    configured_filter: object = "all",
) -> str:
    if not pending_url:
        return str(configured_filter or "all")
    return normalize_channel_filter(current_filter)


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
