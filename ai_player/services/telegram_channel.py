from __future__ import annotations

import asyncio
import contextlib
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from ai_player.core.config import CONFIG_DIR, RUNTIME_DIR
from ai_player.core.i18n import ui_text
from ai_player.services.video_source import _url_host


@dataclass(frozen=True)
class TelegramChannelVideo:
    title: str
    url: str
    post_id: str
    duration: str = ""
    authenticated: bool = False


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


TELEGRAM_LOGIN_CONFIG_PATH = CONFIG_DIR / "telegram_login.json"
TELEGRAM_SESSION_PATH = CONFIG_DIR / "telegram_user.session"
TELEGRAM_CACHE_DIR = RUNTIME_DIR / "telegram"


def is_telegram_channel_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    host = _url_host(parsed)
    if host not in {"t.me", "telegram.me"}:
        return False
    parts = _path_parts(parsed.path)
    if len(parts) == 1:
        return _valid_public_channel_name(parts[0])
    return len(parts) == 2 and parts[0] == "s" and _valid_public_channel_name(parts[1])


def list_telegram_channel_videos(
    value: str,
    *,
    limit: int = 50,
    language_id: str | None = None,
) -> list[TelegramChannelVideo]:
    channel = _channel_name(value, language_id)
    preview_url = f"https://t.me/s/{channel}"
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

    videos = parse_telegram_channel_videos(response.text, channel, limit=limit)
    if not videos:
        raise TelegramChannelError(ui_text("telegram_channel_no_videos", language_id))
    return videos


def load_telegram_login_config() -> TelegramLoginConfig | None:
    try:
        payload = json.loads(TELEGRAM_LOGIN_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    try:
        return TelegramLoginConfig(
            api_id=int(payload.get("api_id") or 0),
            api_hash=str(payload.get("api_hash") or "").strip(),
            phone=str(payload.get("phone") or "").strip(),
        )
    except (TypeError, ValueError):
        return None


def save_telegram_login_config(config: TelegramLoginConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TELEGRAM_LOGIN_CONFIG_PATH.write_text(
        json.dumps(
            {"api_id": int(config.api_id), "api_hash": config.api_hash, "phone": config.phone},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def delete_telegram_login_data() -> None:
    with contextlib.suppress(OSError):
        TELEGRAM_LOGIN_CONFIG_PATH.unlink(missing_ok=True)
    for path in TELEGRAM_SESSION_PATH.parent.glob(f"{TELEGRAM_SESSION_PATH.name}*"):
        if path.is_file() or path.is_symlink():
            with contextlib.suppress(OSError):
                path.unlink()


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
    save_telegram_login_config(config)
    try:
        phone_code_hash = _run_async(_start_telegram_login(config))
    except TelegramChannelError:
        raise
    except Exception as exc:
        raise TelegramChannelError(ui_text("telegram_login_failed", language_id, detail=_clean_error(exc))) from exc
    if not phone_code_hash:
        return None
    return TelegramLoginRequest(config=config, phone_code_hash=str(phone_code_hash))


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
    try:
        _run_async(_complete_telegram_login(request, code, password))
    except TelegramPasswordRequired:
        raise
    except TelegramChannelError:
        raise
    except Exception as exc:
        raise TelegramChannelError(ui_text("telegram_login_failed", language_id, detail=_clean_error(exc))) from exc


def list_telegram_channel_videos_authenticated(
    value: str,
    config: TelegramLoginConfig,
    *,
    limit: int = 50,
    language_id: str | None = None,
) -> list[TelegramChannelVideo]:
    try:
        videos = _run_async(_list_authenticated_videos(value, config, limit))
    except TelegramChannelError:
        raise
    except Exception as exc:
        raise TelegramChannelError(
            ui_text("telegram_channel_auth_load_failed", language_id, detail=_clean_error(exc))
        ) from exc
    if not videos:
        raise TelegramChannelError(ui_text("telegram_channel_auth_no_videos", language_id))
    return videos


def download_telegram_channel_video(
    value: str,
    post_id: str,
    config: TelegramLoginConfig,
    *,
    language_id: str | None = None,
) -> str:
    try:
        return _run_async(_download_authenticated_video(value, post_id, config))
    except TelegramChannelError:
        raise
    except Exception as exc:
        raise TelegramChannelError(
            ui_text("telegram_channel_download_failed", language_id, detail=_clean_error(exc))
        ) from exc


def parse_telegram_channel_videos(html_text: str, channel: str, *, limit: int = 50) -> list[TelegramChannelVideo]:
    videos: list[TelegramChannelVideo] = []
    seen: set[str] = set()
    for post, block in _iter_message_blocks(html_text):
        post_channel, post_id = _split_post(post)
        if not post_id:
            continue
        if not _block_has_video(block):
            continue
        url = f"https://t.me/{post_channel or channel}/{post_id}"
        if url in seen:
            continue
        seen.add(url)
        title = _message_title(block, post_id)
        duration = _message_duration(block)
        if duration:
            title = f"{title} [{duration}]"
        videos.append(TelegramChannelVideo(title=title, url=url, post_id=post_id, duration=duration))
        if len(videos) >= limit:
            break
    return videos


async def _start_telegram_login(config: TelegramLoginConfig) -> str:
    client = _telegram_client(config)
    await client.connect()
    try:
        if await client.is_user_authorized():
            return ""
        sent = await client.send_code_request(config.phone)
        return str(sent.phone_code_hash or "")
    finally:
        await client.disconnect()


async def _complete_telegram_login(request: TelegramLoginRequest, code: str, password: str) -> None:
    errors = _telethon_errors()
    client = _telegram_client(request.config)
    await client.connect()
    try:
        try:
            await client.sign_in(
                phone=request.config.phone,
                code=code,
                phone_code_hash=request.phone_code_hash,
            )
        except errors.SessionPasswordNeededError as exc:
            password = str(password or "").strip()
            if not password:
                raise TelegramPasswordRequired("telegram password required") from exc
            await client.sign_in(password=password)
    finally:
        await client.disconnect()


async def _list_authenticated_videos(
    value: str,
    config: TelegramLoginConfig,
    limit: int,
) -> list[TelegramChannelVideo]:
    channel = _channel_name(value)
    client = _telegram_client(config)
    await client.connect()
    try:
        await _ensure_authorized(client)
        entity = await client.get_entity(channel)
        username = str(getattr(entity, "username", "") or channel).strip() or channel
        videos: list[TelegramChannelVideo] = []
        async for message in client.iter_messages(entity, limit=max(limit * 8, 100)):
            if not _message_has_video(message):
                continue
            duration = _message_media_duration(message)
            title = _authenticated_message_title(message, duration)
            videos.append(
                TelegramChannelVideo(
                    title=title,
                    url=f"https://t.me/{username}/{message.id}",
                    post_id=str(message.id),
                    duration=duration,
                    authenticated=True,
                )
            )
            if len(videos) >= limit:
                break
        return videos
    finally:
        await client.disconnect()


async def _download_authenticated_video(value: str, post_id: str, config: TelegramLoginConfig) -> str:
    channel = _channel_name(value)
    message_id = int(str(post_id).strip())
    client = _telegram_client(config)
    await client.connect()
    try:
        await _ensure_authorized(client)
        entity = await client.get_entity(channel)
        message = await client.get_messages(entity, ids=message_id)
        if message is None or not _message_has_video(message):
            raise TelegramChannelError("Telegram message does not contain a video.")
        TELEGRAM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        output_path = TELEGRAM_CACHE_DIR / f"{_safe_filename(channel)}-{message_id}{_message_video_suffix(message)}"
        if output_path.exists() and output_path.stat().st_size > 0:
            return str(output_path)
        partial_path = output_path.with_suffix(f"{output_path.suffix}.part")
        if partial_path.exists():
            partial_path.unlink()
        downloaded = await client.download_media(message, file=str(partial_path))
        downloaded_path = Path(str(downloaded or partial_path))
        if not downloaded_path.exists() or downloaded_path.stat().st_size <= 0:
            raise TelegramChannelError("Telegram download did not create a video file.")
        downloaded_path.replace(output_path)
        return str(output_path)
    finally:
        await client.disconnect()


def _telegram_client(config: TelegramLoginConfig):
    try:
        from telethon import TelegramClient
    except ImportError as exc:
        raise TelegramChannelError(ui_text("telegram_login_missing_telethon")) from exc
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return TelegramClient(str(TELEGRAM_SESSION_PATH), int(config.api_id), config.api_hash)


def _telethon_errors():
    try:
        from telethon import errors
    except ImportError as exc:
        raise TelegramChannelError(ui_text("telegram_login_missing_telethon")) from exc
    return errors


async def _ensure_authorized(client) -> None:
    if not await client.is_user_authorized():
        raise TelegramChannelError(ui_text("telegram_login_required"))


def _run_async(coro):
    return asyncio.run(coro)


def _message_has_video(message) -> bool:
    if bool(getattr(message, "video", None)):
        return True
    document = getattr(message, "document", None)
    mime_type = str(getattr(document, "mime_type", "") or "")
    return mime_type.lower().startswith("video/")


def _message_media_duration(message) -> str:
    document = getattr(message, "document", None)
    for attr in getattr(document, "attributes", []) or []:
        duration = getattr(attr, "duration", None)
        if duration:
            return _format_duration(duration)
    return ""


def _authenticated_message_title(message, duration: str) -> str:
    text = _truncate(str(getattr(message, "message", "") or "").strip(), 90)
    if not text:
        date = getattr(message, "date", None)
        date_text = date.strftime("%Y-%m-%d %H:%M") if date is not None and hasattr(date, "strftime") else ""
        text = f"#{getattr(message, 'id', '')} {date_text}".strip()
    return f"{text} [{duration}]" if duration else text


def _message_video_suffix(message) -> str:
    document = getattr(message, "document", None)
    mime_type = str(getattr(document, "mime_type", "") or "").lower()
    suffix_by_mime = {
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "video/x-matroska": ".mkv",
        "video/quicktime": ".mov",
    }
    return suffix_by_mime.get(mime_type, ".mp4")


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
    raise TelegramChannelError(ui_text("telegram_channel_bad_url", language_id))


def _path_parts(path: str) -> list[str]:
    return [part for part in path.strip("/").split("/") if part]


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


def _message_title(block: str, post_id: str) -> str:
    text_match = re.search(
        r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
        block,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = _html_to_text(text_match.group(1)) if text_match else ""
    if text:
        return _truncate(text, 90)

    date_match = re.search(
        r'<time[^>]*datetime="([^"]+)"',
        block,
        flags=re.IGNORECASE,
    )
    date_text = date_match.group(1).replace("T", " ")[:16] if date_match else ""
    return f"#{post_id} {date_text}".strip()


def _message_duration(block: str) -> str:
    match = re.search(
        r'<[^>]*class="[^"]*message_video_duration[^"]*"[^>]*>(.*?)</[^>]+>',
        block,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return _html_to_text(match.group(1)) if match else ""


def _html_to_text(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return " ".join(text.split())


def _truncate(value: str, max_length: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3].rstrip()}..."


def _clean_error(value: object) -> str:
    text = " ".join(str(value or "").split())
    return text or value.__class__.__name__
