from __future__ import annotations

import asyncio
import contextlib
import json
import platform
from pathlib import Path
from typing import Any

from ai_player.core.config import CONFIG_DIR, RUNTIME_DIR
from ai_player.core.i18n import ui_text
from ai_player.core.secret_store import SecretStoreError, protect_text, reveal_text
from ai_player.services.telegram_channel import (
    TelegramChannelError,
    TelegramChannelVideo,
    TelegramLoginConfig,
    TelegramLoginRequest,
    TelegramPasswordRequired,
    _channel_name,
    _clean_error,
    _format_duration,
    _safe_filename,
    _truncate,
)

PRIVATE_TELEGRAM_CONFIG_DIR = CONFIG_DIR / "private" / "telegram"
TELEGRAM_LOGIN_CONFIG_PATH = PRIVATE_TELEGRAM_CONFIG_DIR / "telegram_login.json"
TELEGRAM_SESSION_PATH = PRIVATE_TELEGRAM_CONFIG_DIR / "telegram_user.session"
TELEGRAM_CACHE_DIR = RUNTIME_DIR / "private" / "telegram"

LEGACY_TELEGRAM_LOGIN_CONFIG_PATH = CONFIG_DIR / "telegram_login.json"
LEGACY_TELEGRAM_SESSION_PATH = CONFIG_DIR / "telegram_user.session"


def load_telegram_login_config() -> TelegramLoginConfig | None:
    return _load_login_config_from(TELEGRAM_LOGIN_CONFIG_PATH) or _load_login_config_from(
        LEGACY_TELEGRAM_LOGIN_CONFIG_PATH
    )


def save_telegram_login_config(config: TelegramLoginConfig) -> None:
    PRIVATE_TELEGRAM_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data: dict[str, object] = {"api_id": int(config.api_id)}
    try:
        data.update(
            {
                "api_hash_secret": protect_text(config.api_hash),
                "phone_secret": protect_text(config.phone),
            }
        )
    except SecretStoreError:
        pass
    TELEGRAM_LOGIN_CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def delete_telegram_login_data() -> None:
    for path in (TELEGRAM_LOGIN_CONFIG_PATH, LEGACY_TELEGRAM_LOGIN_CONFIG_PATH):
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)
    for session_path in (TELEGRAM_SESSION_PATH, LEGACY_TELEGRAM_SESSION_PATH):
        for path in session_path.parent.glob(f"{session_path.name}*"):
            if path.is_file() or path.is_symlink():
                with contextlib.suppress(OSError):
                    path.unlink()


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
    before_post_id: str = "",
    search: str = "",
    language_id: str | None = None,
) -> list[TelegramChannelVideo]:
    videos = [
        item
        for item in list_telegram_channel_items_authenticated(
            value,
            config,
            limit=limit,
            before_post_id=before_post_id,
            search=search,
            language_id=language_id,
        )
        if item.has_video
    ]
    if not videos:
        raise TelegramChannelError(ui_text("telegram_channel_auth_no_videos", language_id))
    return videos


def list_telegram_channel_items_authenticated(
    value: str,
    config: TelegramLoginConfig,
    *,
    limit: int = 50,
    before_post_id: str = "",
    search: str = "",
    language_id: str | None = None,
) -> list[TelegramChannelVideo]:
    try:
        videos = _run_async(_list_authenticated_items(value, config, limit, before_post_id, search))
    except TelegramChannelError:
        raise
    except Exception as exc:
        raise TelegramChannelError(
            ui_text("telegram_channel_auth_load_failed", language_id, detail=_clean_error(exc))
        ) from exc
    if not videos:
        raise TelegramChannelError(ui_text("telegram_channel_auth_no_items", language_id))
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


def _load_login_config_from(path: Path) -> TelegramLoginConfig | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    try:
        api_hash = _load_saved_secret(payload, "api_hash")
        phone = _load_saved_secret(payload, "phone")
        if not api_hash or not phone:
            return None
        return TelegramLoginConfig(
            api_id=int(payload.get("api_id") or 0),
            api_hash=api_hash,
            phone=phone,
        )
    except (SecretStoreError, TypeError, ValueError):
        return None


def _load_saved_secret(payload: dict[str, Any], name: str) -> str:
    protected = reveal_text(payload.get(f"{name}_secret"))
    if protected:
        return protected.strip()
    return str(payload.get(name) or "").strip()


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


async def _list_authenticated_items(
    value: str,
    config: TelegramLoginConfig,
    limit: int,
    before_post_id: str,
    search: str,
) -> list[TelegramChannelVideo]:
    channel = _channel_name(value)
    offset_id = _post_id_value(before_post_id)
    client = _telegram_client(config)
    await client.connect()
    try:
        await _ensure_authorized(client)
        entity = await client.get_entity(channel)
        username = str(getattr(entity, "username", "") or channel).strip() or channel
        videos: list[TelegramChannelVideo] = []
        async for message in client.iter_messages(entity, limit=limit, offset_id=offset_id, search=str(search or "")):
            duration = _message_media_duration(message)
            title = _authenticated_message_title(message, duration)
            media_kind = _message_media_kind(message)
            videos.append(
                TelegramChannelVideo(
                    title=title,
                    url=f"https://t.me/{username}/{message.id}",
                    post_id=str(message.id),
                    duration=duration,
                    authenticated=True,
                    text=_authenticated_message_text(message),
                    has_video=media_kind == "video",
                    thumbnail_url=await _download_message_thumbnail(client, message, channel, message.id),
                    date=_message_date(message),
                    media_kind=media_kind,
                    file_name=_message_file_name(message),
                    file_size=_message_file_size(message),
                    media_count=1,
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
    PRIVATE_TELEGRAM_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return TelegramClient(
        str(TELEGRAM_SESSION_PATH),
        int(config.api_id),
        config.api_hash,
        device_model="AI Player",
        system_version=platform.platform(),
        app_version="AI Player internal",
        lang_code="vi",
        system_lang_code="vi",
    )


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


def _message_media_kind(message) -> str:
    if _message_has_video(message):
        return "video"
    if bool(getattr(message, "photo", None)):
        return "photo"
    document = getattr(message, "document", None)
    if document is not None:
        mime_type = str(getattr(document, "mime_type", "") or "").lower()
        if mime_type.startswith("audio/"):
            return "audio"
        return "document"
    return "text"


def _message_media_duration(message) -> str:
    document = getattr(message, "document", None)
    for attr in getattr(document, "attributes", []) or []:
        duration = getattr(attr, "duration", None)
        if duration:
            return _format_duration(duration)
    return ""


def _authenticated_message_title(message, duration: str) -> str:
    text = _truncate(_authenticated_message_text(message), 90)
    if not text:
        date = getattr(message, "date", None)
        date_text = date.strftime("%Y-%m-%d %H:%M") if date is not None and hasattr(date, "strftime") else ""
        text = f"#{getattr(message, 'id', '')} {date_text}".strip()
    return f"{text} [{duration}]" if duration else text


def _authenticated_message_text(message) -> str:
    return " ".join(str(getattr(message, "message", "") or "").strip().split())


def _message_date(message) -> str:
    date = getattr(message, "date", None)
    return date.strftime("%Y-%m-%d %H:%M") if date is not None and hasattr(date, "strftime") else ""


def _message_file_name(message) -> str:
    document = getattr(message, "document", None)
    for attr in getattr(document, "attributes", []) or []:
        file_name = str(getattr(attr, "file_name", "") or "").strip()
        if file_name:
            return file_name
    return ""


def _message_file_size(message) -> int:
    document = getattr(message, "document", None)
    try:
        return max(0, int(getattr(document, "size", 0) or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


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


async def _download_message_thumbnail(client, message, channel: str, message_id: object) -> str:
    if _message_media_kind(message) not in {"video", "photo", "document", "audio"}:
        return ""
    thumbnail_dir = TELEGRAM_CACHE_DIR / "thumbnails"
    thumbnail_dir.mkdir(parents=True, exist_ok=True)
    output_path = thumbnail_dir / f"{_safe_filename(channel)}-{message_id}.jpg"
    if output_path.exists() and output_path.stat().st_size > 0:
        return str(output_path)
    for thumb in (-1, 0):
        temp_path = output_path.with_suffix(f".{thumb}.tmp")
        with contextlib.suppress(OSError):
            temp_path.unlink(missing_ok=True)
        try:
            downloaded = await client.download_media(message, file=str(temp_path), thumb=thumb)
        except Exception:
            continue
        downloaded_path = Path(str(downloaded or temp_path))
        if downloaded_path.exists() and downloaded_path.stat().st_size > 0:
            downloaded_path.replace(output_path)
            return str(output_path)
    return ""


def _post_id_value(value: object) -> int:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else 0
