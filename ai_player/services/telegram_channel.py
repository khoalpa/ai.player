from __future__ import annotations

import html
import importlib
import inspect
import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from ai_player.core.i18n import ui_text
from ai_player.services.video_source import _url_host


@dataclass(frozen=True)
class TelegramChannelVideo:
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


@dataclass(frozen=True)
class TelegramLoginConfig:
    api_id: int
    api_hash: str
    phone: str


@dataclass(frozen=True)
class TelegramLoginRequest:
    config: TelegramLoginConfig
    phone_code_hash: str


class TelegramChannelError(RuntimeError):
    pass


class TelegramPasswordRequired(TelegramChannelError):
    pass


def telegram_channel_item_translation_text(item: object) -> str:
    text = str(getattr(item, "text", "") or "").strip()
    if text:
        return " ".join(text.split())
    title = str(getattr(item, "title", "") or "").strip()
    return " ".join(title.split())


TELEGRAM_SESSION_LOCK_RETRIES = 5
TELEGRAM_SESSION_LOCK_RETRY_DELAY_SECONDS = 0.35


def is_telegram_channel_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    host = _url_host(parsed)
    if host not in {"t.me", "telegram.me"}:
        return False
    parts = _path_parts(parsed.path)
    if _is_private_telegram_path(parts):
        return True
    if len(parts) == 1:
        return _valid_public_channel_name(parts[0])
    if len(parts) == 2 and parts[0] == "s":
        return _valid_public_channel_name(parts[1])
    return len(parts) == 2 and _valid_public_channel_name(parts[0]) and parts[1].isdigit()


def is_private_telegram_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    host = _url_host(parsed)
    return host in {"t.me", "telegram.me"} and _is_private_telegram_path(_path_parts(parsed.path))


def list_telegram_channel_videos(
    value: str,
    *,
    limit: int = 50,
    before_post_id: str = "",
    search: str = "",
    language_id: str | None = None,
) -> list[TelegramChannelVideo]:
    try:
        items = list_telegram_channel_items(
            value,
            limit=limit,
            before_post_id=before_post_id,
            search=search,
            language_id=language_id,
        )
    except TelegramChannelError as exc:
        if str(exc) == ui_text("telegram_channel_no_items", language_id):
            raise TelegramChannelError(ui_text("telegram_channel_no_videos", language_id)) from exc
        raise
    videos = [item for item in items if item.has_video]
    if not videos:
        raise TelegramChannelError(ui_text("telegram_channel_no_videos", language_id))
    return videos


def list_telegram_channel_items(
    value: str,
    *,
    limit: int = 50,
    before_post_id: str = "",
    search: str = "",
    language_id: str | None = None,
) -> list[TelegramChannelVideo]:
    channel = _channel_name(value, language_id)
    preview_url = f"https://t.me/s/{channel}"
    before_post_id = _post_id_text(before_post_id)
    if before_post_id:
        preview_url = f"{preview_url}?before={before_post_id}"
    try:
        import requests
    except ImportError as exc:
        raise TelegramChannelError(ui_text("telegram_channel_missing_requests", language_id)) from exc

    try:
        response = requests.get(preview_url, headers=_telegram_headers(), timeout=20)
        response.raise_for_status()
    except Exception as exc:
        raise TelegramChannelError(
            ui_text("telegram_channel_load_failed", language_id, detail=_clean_error(exc))
        ) from exc

    items = parse_telegram_channel_items(response.text, channel, limit=limit, search=search)
    if not items:
        raise TelegramChannelError(ui_text("telegram_channel_no_items", language_id))
    return items


def telegram_private_available() -> bool:
    return _telegram_private_adapter() is not None


def load_telegram_login_config() -> TelegramLoginConfig | None:
    adapter = _require_telegram_private_adapter(required=False)
    if adapter is None:
        return None
    return adapter.load_telegram_login_config()


def delete_telegram_login_data() -> None:
    adapter = _require_telegram_private_adapter(required=False)
    if adapter is not None:
        adapter.delete_telegram_login_data()


def validate_telegram_login_config(
    api_id: object,
    api_hash: object,
    phone: object,
    language_id: str | None = None,
) -> TelegramLoginConfig:
    try:
        parsed_api_id = int(str(api_id or "").strip())
    except (TypeError, ValueError) as exc:
        raise TelegramChannelError(ui_text("telegram_login_bad_api_id", language_id)) from exc
    parsed_api_hash = str(api_hash or "").strip()
    parsed_phone = str(phone or "").strip()
    if parsed_api_id <= 0:
        raise TelegramChannelError(ui_text("telegram_login_bad_api_id", language_id))
    if not parsed_api_hash:
        raise TelegramChannelError(ui_text("telegram_login_missing_api_hash", language_id))
    if not parsed_phone:
        raise TelegramChannelError(ui_text("telegram_login_missing_phone", language_id))
    return TelegramLoginConfig(parsed_api_id, parsed_api_hash, parsed_phone)


def start_telegram_login(config: TelegramLoginConfig, language_id: str | None = None) -> TelegramLoginRequest | None:
    adapter = _require_telegram_private_adapter(language_id=language_id)
    return _retry_telegram_session_lock(lambda: adapter.start_telegram_login(config, language_id=language_id))


def complete_telegram_login(
    request: TelegramLoginRequest,
    code: str,
    *,
    password: str = "",
    language_id: str | None = None,
) -> None:
    code = str(code or "").strip()
    if not code:
        raise TelegramChannelError(ui_text("telegram_login_missing_code", language_id))
    adapter = _require_telegram_private_adapter(language_id=language_id)
    _retry_telegram_session_lock(
        lambda: adapter.complete_telegram_login(request, code, password=password, language_id=language_id)
    )


def list_telegram_channel_videos_authenticated(
    value: str,
    config: TelegramLoginConfig,
    *,
    limit: int = 50,
    before_post_id: str = "",
    search: str = "",
    language_id: str | None = None,
) -> list[TelegramChannelVideo]:
    adapter = _require_telegram_private_adapter(language_id=language_id)
    return _retry_telegram_session_lock(
        lambda: adapter.list_telegram_channel_videos_authenticated(
            value,
            config,
            limit=limit,
            before_post_id=before_post_id,
            search=search,
            language_id=language_id,
        )
    )


def list_telegram_channel_items_authenticated(
    value: str,
    config: TelegramLoginConfig,
    *,
    limit: int = 50,
    before_post_id: str = "",
    search: str = "",
    language_id: str | None = None,
) -> list[TelegramChannelVideo]:
    adapter = _require_telegram_private_adapter(language_id=language_id)
    return _retry_telegram_session_lock(
        lambda: adapter.list_telegram_channel_items_authenticated(
            value,
            config,
            limit=limit,
            before_post_id=before_post_id,
            search=search,
            language_id=language_id,
        )
    )


def download_telegram_channel_video(
    value: str,
    post_id: str,
    config: TelegramLoginConfig,
    *,
    progress_callback=None,
    cancel_callback=None,
    language_id: str | None = None,
) -> str:
    adapter = _require_telegram_private_adapter(language_id=language_id)
    callback = adapter.download_telegram_channel_video
    kwargs = _supported_adapter_kwargs(
        callback,
        {
            "language_id": language_id,
            "progress_callback": progress_callback,
            "cancel_callback": cancel_callback,
        },
    )
    return _retry_telegram_session_lock(
        lambda: callback(value, post_id, config, **kwargs)
    )


def parse_telegram_channel_videos(
    html_text: str,
    channel: str,
    *,
    limit: int = 50,
    search: str = "",
) -> list[TelegramChannelVideo]:
    return [
        item
        for item in parse_telegram_channel_items(html_text, channel, limit=limit, search=search)
        if item.has_video
    ]


def parse_telegram_channel_items(
    html_text: str,
    channel: str,
    *,
    limit: int = 50,
    search: str = "",
) -> list[TelegramChannelVideo]:
    videos: list[TelegramChannelVideo] = []
    seen: set[str] = set()
    for post, block in _iter_message_blocks(html_text):
        post_channel, post_id = _split_post(post)
        if not post_id:
            continue
        url = f"https://t.me/{post_channel or channel}/{post_id}"
        if url in seen:
            continue
        seen.add(url)
        text = _message_text(block)
        duration = _message_duration(block)
        media_kind = _message_media_kind(block)
        has_video = media_kind == "video"
        thumbnail_url = _message_thumbnail_url(url, block)
        media_url = _message_media_url(url, block)
        date = _message_date(block)
        file_name = _message_file_name(block)
        file_size = _message_file_size(block)
        media_count = _message_media_count(block)
        title = _truncate(text, 90) if text else _message_title(block, post_id)
        if duration:
            title = f"{title} [{duration}]"
        if search and not _matches_query(search, title, text, file_name, post_id):
            continue
        videos.append(
            TelegramChannelVideo(
                title=title,
                url=url,
                post_id=post_id,
                duration=duration,
                text=text,
                has_video=has_video,
                thumbnail_url=thumbnail_url,
                date=date,
                media_kind=media_kind,
                file_name=file_name,
                file_size=file_size,
                media_count=media_count,
                media_url=media_url,
            )
        )
        if len(videos) >= limit:
            break
    return videos


def _telegram_private_adapter():
    try:
        return importlib.import_module("ai_player_telegram_client.adapter")
    except ImportError:
        return None


def _require_telegram_private_adapter(*, language_id: str | None = None, required: bool = True):
    adapter = _telegram_private_adapter()
    if adapter is not None or not required:
        return adapter
    raise TelegramChannelError(ui_text("telegram_login_missing_private_plugin", language_id))


def _supported_adapter_kwargs(callback, values: dict[str, object]) -> dict[str, object]:
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return {name: value for name, value in values.items() if value is not None}
    parameters = signature.parameters
    accepts_kwargs = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
    return {
        name: value
        for name, value in values.items()
        if value is not None and (accepts_kwargs or name in parameters)
    }


def _retry_telegram_session_lock(callback):
    for attempt in range(TELEGRAM_SESSION_LOCK_RETRIES + 1):
        try:
            return callback()
        except Exception as exc:
            if not _is_telegram_session_locked(exc) or attempt >= TELEGRAM_SESSION_LOCK_RETRIES:
                raise
            time.sleep(TELEGRAM_SESSION_LOCK_RETRY_DELAY_SECONDS * (attempt + 1))
    return callback()


def _is_telegram_session_locked(value: object) -> bool:
    text = str(value or "").lower()
    return "database is locked" in text or "database table is locked" in text


def _format_duration(value: object) -> str:
    try:
        seconds = max(0, int(float(value)))
    except (TypeError, ValueError, OverflowError):
        return ""
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:d}:{seconds:02d}"


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "telegram"


def _channel_name(value: str, language_id: str | None = None) -> str:
    parsed = urlparse(value.strip())
    parts = _path_parts(parsed.path)
    if len(parts) == 1 and _valid_public_channel_name(parts[0]):
        return parts[0]
    if len(parts) == 2 and parts[0] == "s" and _valid_public_channel_name(parts[1]):
        return parts[1]
    if len(parts) == 2 and _valid_public_channel_name(parts[0]) and parts[1].isdigit():
        return parts[0]
    raise TelegramChannelError(ui_text("telegram_channel_bad_url", language_id))


def _path_parts(path: str) -> list[str]:
    return [part for part in path.strip("/").split("/") if part]


def _is_private_telegram_path(parts: list[str]) -> bool:
    if len(parts) == 1 and parts[0].startswith("+") and len(parts[0]) > 1:
        return True
    if len(parts) == 2 and parts[0] == "joinchat" and bool(parts[1]):
        return True
    return len(parts) == 3 and parts[0] == "c" and parts[1].isdigit() and parts[2].isdigit()


def _valid_public_channel_name(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_]{5,64}", value or ""))


def _telegram_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125 Safari/537.36"
        )
    }


def _iter_message_blocks(html_text: str):
    matches = list(re.finditer(r'data-post="([^"]+)"', html_text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(html_text)
        yield html.unescape(match.group(1)), html_text[match.start() : end]


def _split_post(value: str) -> tuple[str, str]:
    parts = _path_parts(value)
    if len(parts) < 2:
        return "", ""
    post_id = parts[-1]
    if not post_id.isdigit():
        return "", ""
    return parts[-2], post_id


def _block_has_video(block: str) -> bool:
    lowered = block.lower()
    markers = (
        "tgme_widget_message_video",
        "tgme_widget_message_video_player",
        "message_video_duration",
        "<video",
    )
    return any(marker in lowered for marker in markers)


def _message_media_kind(block: str) -> str:
    lowered = block.lower()
    if _block_has_video(block):
        return "video"
    if "tgme_widget_message_photo" in lowered or "<img" in lowered:
        return "photo"
    if "tgme_widget_message_document" in lowered or "tgme_widget_message_document_title" in lowered:
        return "document"
    if "tgme_widget_message_voice" in lowered or "tgme_widget_message_audio" in lowered:
        return "audio"
    return "text"


def _message_title(block: str, post_id: str) -> str:
    text = _message_text(block)
    if text:
        return _truncate(text, 90)

    date_match = re.search(
        r'<time[^>]*datetime="([^"]+)"',
        block,
        flags=re.IGNORECASE,
    )
    date_text = date_match.group(1).replace("T", " ")[:16] if date_match else ""
    return f"#{post_id} {date_text}".strip()


def _message_text(block: str) -> str:
    text_match = re.search(
        r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
        block,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return _html_to_text(text_match.group(1)) if text_match else ""


def _message_date(block: str) -> str:
    date_match = re.search(
        r'<time[^>]*datetime="([^"]+)"',
        block,
        flags=re.IGNORECASE,
    )
    return date_match.group(1).replace("T", " ")[:16] if date_match else ""


def _message_duration(block: str) -> str:
    match = re.search(
        r'<[^>]*class="[^"]*message_video_duration[^"]*"[^>]*>(.*?)</[^>]+>',
        block,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return _html_to_text(match.group(1)) if match else ""


def _message_file_name(block: str) -> str:
    for pattern in (
        r'<div class="[^"]*tgme_widget_message_document_title[^"]*"[^>]*>(.*?)</div>',
        r'<div class="[^"]*tgme_widget_message_document_extra[^"]*"[^>]*>(.*?)</div>',
    ):
        match = re.search(pattern, block, flags=re.IGNORECASE | re.DOTALL)
        if match:
            text = _html_to_text(match.group(1))
            if text:
                return _truncate(text, 120)
    return ""


def _message_file_size(block: str) -> int:
    match = re.search(
        r'([0-9]+(?:[.,][0-9]+)?)\s*(KB|MB|GB)',
        _html_to_text(block),
        flags=re.IGNORECASE,
    )
    if not match:
        return 0
    try:
        value = float(match.group(1).replace(",", "."))
    except ValueError:
        return 0
    unit = match.group(2).upper()
    multiplier = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}.get(unit, 1)
    return int(value * multiplier)


def _message_media_count(block: str) -> int:
    lowered = block.lower()
    marker_count = 0
    for marker in (
        "tgme_widget_message_video_player",
        "tgme_widget_message_photo",
        "tgme_widget_message_document",
        "tgme_widget_message_voice",
        "tgme_widget_message_audio",
        "<video",
    ):
        marker_count += lowered.count(marker)
    urls: set[str] = set()
    for pattern in (
        r"""background-image\s*:\s*url\((?P<quote>['"]?)(?P<url>.*?)(?P=quote)\)""",
        r"""<img[^>]+src=["'](?P<url>[^"']+)["']""",
        r"""(?:poster|data-thumb|data-src|src)=["'](?P<url>[^"']+)["']""",
    ):
        for match in re.finditer(pattern, block, flags=re.IGNORECASE | re.DOTALL):
            url = html.unescape(str(match.group("url") or "")).strip()
            if url:
                urls.add(url)
    return max(1, marker_count, len(urls))


def _message_thumbnail_url(page_url: str, block: str) -> str:
    for pattern in (
        r"""background-image\s*:\s*url\((?P<quote>['"]?)(?P<url>.*?)(?P=quote)\)""",
        r"""<img[^>]+src=["'](?P<url>[^"']+)["']""",
        r"""(?:poster|data-thumb|data-src)=["'](?P<url>[^"']+)["']""",
    ):
        match = re.search(pattern, block, flags=re.IGNORECASE | re.DOTALL)
        if match:
            url = html.unescape(str(match.group("url") or "")).strip()
            if url:
                return urljoin(page_url, url)
    return ""


def _message_media_url(page_url: str, block: str) -> str:
    for pattern in (
        r"""<video[^>]+src=["'](?P<url>[^"']+)["']""",
        r"""<source[^>]+src=["'](?P<url>[^"']+)["']""",
    ):
        match = re.search(pattern, block, flags=re.IGNORECASE | re.DOTALL)
        if match:
            url = html.unescape(str(match.group("url") or "")).strip()
            if url:
                return urljoin(page_url, url)
    return ""


def _html_to_text(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return " ".join(text.split())


def _matches_query(query: str, *values: object) -> bool:
    needle = " ".join(str(query or "").lower().split())
    if not needle:
        return True
    haystack = " ".join(str(value or "") for value in values).lower()
    return needle in haystack


def _post_id_text(value: object) -> str:
    text = str(value or "").strip()
    return text if text.isdigit() else ""


def _truncate(value: str, max_length: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3].rstrip()}..."


def _clean_error(value: object) -> str:
    text = " ".join(str(value or "").split())
    return text or value.__class__.__name__
