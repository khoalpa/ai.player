from __future__ import annotations

import html
import importlib
import json
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from ai_player.core.i18n import ui_text
from ai_player.services.video_source import _url_host


@dataclass(frozen=True)
class YouTubeChannelItem:
    title: str
    url: str
    post_id: str
    duration: str = ""
    authenticated: bool = False
    text: str = ""
    has_video: bool = True
    thumbnail_url: str = ""
    date: str = ""
    media_kind: str = "video"
    file_name: str = ""
    file_size: int = 0
    media_count: int = 1
    media_url: str = ""
    provider: str = "youtube"
    view_count_text: str = ""
    playlist_id: str = ""


@dataclass(frozen=True)
class YouTubeChannelPage:
    items: list[YouTubeChannelItem]
    continuation: str = ""


class YouTubeChannelError(RuntimeError):
    pass


YOUTUBE_HOSTS = {
    "youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


def youtube_channel_item_translation_text(item: object) -> str:
    text = str(getattr(item, "text", "") or "").strip()
    if text:
        return " ".join(text.split())
    title = str(getattr(item, "title", "") or "").strip()
    return " ".join(title.split())


def is_youtube_channel_url(value: str) -> bool:
    parsed = urlparse(str(value or "").strip())
    host = _url_host(parsed)
    if host not in YOUTUBE_HOSTS or host == "youtu.be":
        return False
    parts = _path_parts(parsed.path)
    if not parts:
        return False
    if parts[0].startswith("@") and len(parts[0]) > 1:
        return True
    if len(parts) >= 2 and parts[0] in {"channel", "c", "user"} and bool(parts[1]):
        return True
    return False


def is_youtube_playlist_url(value: str) -> bool:
    parsed = urlparse(str(value or "").strip())
    host = _url_host(parsed)
    if host not in YOUTUBE_HOSTS or host == "youtu.be":
        return False
    parts = _path_parts(parsed.path)
    query = parse_qs(parsed.query)
    return parts[:1] == ["playlist"] and bool(query.get("list", [""])[0])


def is_youtube_browse_url(value: str) -> bool:
    return is_youtube_channel_url(value) or is_youtube_playlist_url(value)


def youtube_client_available() -> bool:
    return _youtube_client_adapter() is not None


def list_youtube_channel_items(
    value: str,
    *,
    limit: int = 50,
    continuation: str = "",
    search: str = "",
    language_id: str | None = None,
) -> YouTubeChannelPage:
    adapter = _youtube_client_adapter()
    if adapter is not None:
        return _adapter_channel_page(
            adapter.list_youtube_channel_items(
                value,
                limit=limit,
                continuation=continuation,
                search=search,
                language_id=language_id,
            )
        )
    if is_youtube_playlist_url(value):
        return list_youtube_playlist_items(
            value,
            limit=limit,
            continuation=continuation,
            search=search,
            language_id=language_id,
        )
    if not is_youtube_channel_url(value):
        raise YouTubeChannelError(ui_text("youtube_channel_bad_url", language_id))
    return _list_youtube_public_items(
        _channel_videos_url(value),
        limit=limit,
        continuation=continuation,
        search=search,
        language_id=language_id,
    )


def list_youtube_playlist_items(
    value: str,
    *,
    limit: int = 50,
    continuation: str = "",
    search: str = "",
    language_id: str | None = None,
) -> YouTubeChannelPage:
    adapter = _youtube_client_adapter()
    if adapter is not None and hasattr(adapter, "list_youtube_playlist_items"):
        return _adapter_channel_page(
            adapter.list_youtube_playlist_items(
                value,
                limit=limit,
                continuation=continuation,
                search=search,
                language_id=language_id,
            )
        )
    if not is_youtube_playlist_url(value):
        raise YouTubeChannelError(ui_text("youtube_playlist_bad_url", language_id))
    return _list_youtube_public_items(
        value,
        limit=limit,
        continuation=continuation,
        search=search,
        language_id=language_id,
    )


def get_youtube_transcript(
    video_url: str,
    *,
    languages: tuple[str, ...] = ("vi", "en"),
    language_id: str | None = None,
) -> str:
    adapter = _youtube_client_adapter()
    if adapter is not None and hasattr(adapter, "get_youtube_transcript"):
        return str(adapter.get_youtube_transcript(video_url, languages=languages, language_id=language_id) or "")

    html_text, _api_key, _client_version = _load_youtube_page(video_url, language_id=language_id)
    player = _extract_json_assignment(html_text, "ytInitialPlayerResponse")
    tracks = (
        player.get("captions", {})
        .get("playerCaptionsTracklistRenderer", {})
        .get("captionTracks", [])
    )
    tracks = [track for track in tracks if isinstance(track, dict)]
    if not tracks:
        return ""
    language_order = {language: index for index, language in enumerate(languages)}
    tracks.sort(key=lambda track: language_order.get(str(track.get("languageCode") or ""), len(language_order)))
    base_url = str(tracks[0].get("baseUrl") or "")
    if not base_url:
        return ""
    try:
        import requests
    except ImportError as exc:
        raise YouTubeChannelError(ui_text("youtube_channel_missing_requests", language_id)) from exc
    separator = "&" if "?" in base_url else "?"
    response = requests.get(f"{base_url}{separator}fmt=json3", headers=_youtube_headers(), timeout=20)
    response.raise_for_status()
    if not response.text.strip():
        return ""
    data = response.json()
    lines = []
    for event in data.get("events", []):
        if not isinstance(event, dict):
            continue
        segments = event.get("segs") or []
        text = "".join(str(segment.get("utf8") or "") for segment in segments if isinstance(segment, dict)).strip()
        if text:
            lines.append(" ".join(text.split()))
    return "\n".join(lines)


def parse_youtube_initial_items(
    data: dict,
    *,
    limit: int = 50,
    search: str = "",
) -> YouTubeChannelPage:
    items: list[YouTubeChannelItem] = []
    seen: set[str] = set()
    continuation = ""

    def add(item: YouTubeChannelItem) -> None:
        if not item.post_id or item.post_id in seen:
            return
        if search and not _matches_query(search, item.title, item.text, item.date, item.view_count_text):
            return
        seen.add(item.post_id)
        items.append(item)

    def walk(value: object) -> None:
        nonlocal continuation
        if len(items) >= limit and continuation:
            return
        if isinstance(value, dict):
            if "lockupViewModel" in value:
                item = _lockup_item(value.get("lockupViewModel"))
                if item is not None and len(items) < limit:
                    add(item)
            if "videoRenderer" in value:
                item = _video_renderer_item(value.get("videoRenderer"))
                if item is not None and len(items) < limit:
                    add(item)
            if "playlistVideoRenderer" in value:
                item = _playlist_video_renderer_item(value.get("playlistVideoRenderer"))
                if item is not None and len(items) < limit:
                    add(item)
            if not continuation and "continuationItemRenderer" in value:
                continuation = _continuation_token(value.get("continuationItemRenderer"))
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(data)
    return YouTubeChannelPage(items=items[:limit], continuation=continuation)


def _list_youtube_public_items(
    url: str,
    *,
    limit: int,
    continuation: str,
    search: str,
    language_id: str | None,
) -> YouTubeChannelPage:
    html_text, api_key, client_version = _load_youtube_page(url, language_id=language_id)
    if continuation:
        data = _load_youtube_continuation(
            api_key,
            client_version,
            continuation,
            language_id=language_id,
        )
    else:
        data = _extract_json_assignment(html_text, "ytInitialData")
    page = parse_youtube_initial_items(data, limit=limit, search=search)
    if not page.items:
        raise YouTubeChannelError(ui_text("youtube_channel_no_items", language_id))
    return page


def _load_youtube_page(url: str, *, language_id: str | None = None) -> tuple[str, str, str]:
    try:
        import requests
    except ImportError as exc:
        raise YouTubeChannelError(ui_text("youtube_channel_missing_requests", language_id)) from exc
    try:
        response = requests.get(url, headers=_youtube_headers(), timeout=20)
        response.raise_for_status()
    except Exception as exc:
        message = ui_text("youtube_channel_load_failed", language_id, detail=_clean_error(exc))
        raise YouTubeChannelError(message) from exc
    html_text = response.text
    api_key = _regex_text(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"', html_text)
    client_version = _regex_text(r'"INNERTUBE_CLIENT_VERSION"\s*:\s*"([^"]+)"', html_text)
    return html_text, api_key, client_version


def _load_youtube_continuation(
    api_key: str,
    client_version: str,
    continuation: str,
    *,
    language_id: str | None = None,
) -> dict:
    if not api_key or not client_version:
        raise YouTubeChannelError(ui_text("youtube_channel_continuation_failed", language_id, detail="missing context"))
    try:
        import requests
    except ImportError as exc:
        raise YouTubeChannelError(ui_text("youtube_channel_missing_requests", language_id)) from exc
    payload = {
        "context": {
            "client": {
                "clientName": "WEB",
                "clientVersion": client_version,
                "hl": "en",
                "gl": "US",
            }
        },
        "continuation": continuation,
    }
    try:
        response = requests.post(
            f"https://www.youtube.com/youtubei/v1/browse?{urlencode({'key': api_key})}",
            headers=_youtube_headers(),
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise YouTubeChannelError(
            ui_text("youtube_channel_continuation_failed", language_id, detail=_clean_error(exc))
        ) from exc
    return data if isinstance(data, dict) else {}


def _lockup_item(value: object) -> YouTubeChannelItem | None:
    if not isinstance(value, dict) or value.get("contentType") != "LOCKUP_CONTENT_TYPE_VIDEO":
        return None
    video_id = str(value.get("contentId") or "")
    if not video_id:
        return None
    metadata = value.get("metadata", {}).get("lockupMetadataViewModel", {})
    title = str(metadata.get("title", {}).get("content") or video_id)
    parts = _metadata_parts(metadata)
    label = str(value.get("rendererContext", {}).get("accessibilityContext", {}).get("label") or "")
    duration = _duration_from_lockup(value) or _duration_from_label(label)
    thumbnail = _thumbnail_from_lockup(value)
    description = _description_from_metadata(metadata)
    return YouTubeChannelItem(
        title=title,
        text=description or title,
        url=f"https://www.youtube.com/watch?v={video_id}",
        post_id=video_id,
        duration=duration,
        date=parts[1] if len(parts) > 1 else "",
        thumbnail_url=thumbnail,
        view_count_text=parts[0] if parts else "",
        file_name=parts[0] if parts else "",
    )


def _video_renderer_item(value: object) -> YouTubeChannelItem | None:
    if not isinstance(value, dict):
        return None
    video_id = str(value.get("videoId") or "")
    if not video_id:
        return None
    title = _runs_text(value.get("title")) or video_id
    duration = _simple_text(value.get("lengthText"))
    view_count = _simple_text(value.get("viewCountText"))
    date = _simple_text(value.get("publishedTimeText"))
    description = _runs_text(value.get("descriptionSnippet")) or title
    return YouTubeChannelItem(
        title=title,
        text=description,
        url=f"https://www.youtube.com/watch?v={video_id}",
        post_id=video_id,
        duration=duration,
        date=date,
        thumbnail_url=_thumbnail_from_renderer(value),
        view_count_text=view_count,
        file_name=view_count,
    )


def _playlist_video_renderer_item(value: object) -> YouTubeChannelItem | None:
    if not isinstance(value, dict):
        return None
    video_id = str(value.get("videoId") or "")
    if not video_id:
        return None
    title = _runs_text(value.get("title")) or video_id
    duration = _simple_text(value.get("lengthText"))
    return YouTubeChannelItem(
        title=title,
        text=title,
        url=f"https://www.youtube.com/watch?v={video_id}",
        post_id=video_id,
        duration=duration,
        thumbnail_url=_thumbnail_from_renderer(value),
    )


def _metadata_parts(metadata: dict) -> list[str]:
    parts = []
    rows = metadata.get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", [])
    for row in rows if isinstance(rows, list) else []:
        for part in row.get("metadataParts", []) if isinstance(row, dict) else []:
            text = part.get("text", {}).get("content") if isinstance(part, dict) else ""
            if text:
                parts.append(str(text))
    return parts


def _description_from_metadata(metadata: dict) -> str:
    for key in ("description", "subtitle"):
        text = str(metadata.get(key, {}).get("content") or "")
        if text:
            return text
    return ""


def _duration_from_lockup(value: dict) -> str:
    badges = (
        value.get("contentImage", {})
        .get("thumbnailViewModel", {})
        .get("overlays", [])
    )
    for overlay in badges if isinstance(badges, list) else []:
        badge_items = (
            overlay.get("thumbnailBottomOverlayViewModel", {}).get("badges", [])
            if isinstance(overlay, dict)
            else []
        )
        for badge in badge_items:
            text = badge.get("thumbnailBadgeViewModel", {}).get("text") if isinstance(badge, dict) else ""
            if text and re.fullmatch(r"\d+(?::\d{2}){1,2}", str(text)):
                return str(text)
    return ""


def _duration_from_label(value: str) -> str:
    patterns = (
        r"(\d+)\s+hours?,\s+(\d+)\s+minutes?,\s+(\d+)\s+seconds?",
        r"(\d+)\s+hours?,\s+(\d+)\s+minutes?",
        r"(\d+)\s+minutes?,\s+(\d+)\s+seconds?",
        r"(\d+)\s+seconds?",
    )
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            groups = [int(part) for part in match.groups()]
            if len(groups) == 3:
                hours, minutes, seconds = groups
            elif "hour" in pattern:
                hours, minutes, seconds = groups[0], groups[1], 0
            elif "minute" in pattern:
                hours, minutes, seconds = 0, groups[0], groups[1]
            else:
                hours, minutes, seconds = 0, 0, groups[0]
            return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"
    return ""


def _thumbnail_from_lockup(value: dict) -> str:
    sources = (
        value.get("contentImage", {})
        .get("thumbnailViewModel", {})
        .get("image", {})
        .get("sources", [])
    )
    return _best_thumbnail(sources)


def _thumbnail_from_renderer(value: dict) -> str:
    return _best_thumbnail(value.get("thumbnail", {}).get("thumbnails", []))


def _best_thumbnail(sources: object) -> str:
    if not isinstance(sources, list):
        return ""
    best = ""
    best_width = -1
    for source in sources:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url") or "")
        width = _safe_int(source.get("width"))
        if url and width >= best_width:
            best = html.unescape(url)
            best_width = width
    return best


def _continuation_token(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    return str(
        value.get("continuationEndpoint", {})
        .get("continuationCommand", {})
        .get("token")
        or ""
    )


def _extract_json_assignment(html_text: str, name: str) -> dict:
    marker = re.search(rf"{re.escape(name)}\s*=\s*", html_text)
    if not marker:
        marker = re.search(rf"var\s+{re.escape(name)}\s*=\s*", html_text)
    if not marker:
        raise ValueError(f"{name} was not found.")
    start = html_text.find("{", marker.end())
    if start < 0:
        raise ValueError(f"{name} JSON object was not found.")
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(html_text)):
        char = html_text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                data = json.loads(html_text[start : index + 1])
                return data if isinstance(data, dict) else {}
    raise ValueError(f"{name} JSON object was not closed.")


def _adapter_channel_page(value: object) -> YouTubeChannelPage:
    if isinstance(value, YouTubeChannelPage):
        return value
    if isinstance(value, tuple) and len(value) == 2:
        return YouTubeChannelPage(items=list(value[0] or []), continuation=str(value[1] or ""))
    if isinstance(value, dict):
        return YouTubeChannelPage(
            items=list(value.get("items") or []),
            continuation=str(value.get("continuation") or ""),
        )
    return YouTubeChannelPage(items=list(value or []), continuation="")


def _youtube_client_adapter():
    try:
        return importlib.import_module("ai_player_youtube_client.adapter")
    except ImportError:
        return None


def _channel_videos_url(value: str) -> str:
    parsed = urlparse(str(value or "").strip())
    parts = _path_parts(parsed.path)
    if len(parts) >= 2 and parts[-1] in {"about", "community", "featured", "playlists", "shorts", "streams", "videos"}:
        path = "/" + "/".join(parts[:-1] + ["videos"])
    else:
        path = "/" + "/".join(parts + ["videos"])
    return urlunparse(("https", "www.youtube.com", path, "", "", ""))


def _path_parts(path: str) -> list[str]:
    return [part for part in path.strip("/").split("/") if part]


def _runs_text(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    simple = value.get("simpleText")
    if simple:
        return str(simple)
    runs = value.get("runs") or []
    return "".join(str(run.get("text") or "") for run in runs if isinstance(run, dict)).strip()


def _simple_text(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("simpleText") or _runs_text(value) or "")


def _matches_query(query: str, *values: object) -> bool:
    needle = " ".join(str(query or "").lower().split())
    if not needle:
        return True
    haystack = " ".join(str(value or "") for value in values).lower()
    return needle in haystack


def _youtube_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }


def _regex_text(pattern: str, value: str) -> str:
    match = re.search(pattern, value)
    return match.group(1) if match else ""


def _safe_int(value: object) -> int:
    try:
        return int(float(str(value or "0")))
    except (TypeError, ValueError, OverflowError):
        return 0


def _clean_error(value: object) -> str:
    text = " ".join(str(value or "").split())
    return text or value.__class__.__name__
