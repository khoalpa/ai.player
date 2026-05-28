from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse

from ai_player.core.i18n import ui_text


class VideoSourceError(RuntimeError):
    pass


class VideoSourceCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoSource:
    input_url: str
    playback_url: str
    title: str
    provider: str = "direct"
    is_resolved: bool = False


YTDLP_PAGE_HOSTS = {
    "youtube.com",
    "m.youtube.com",
    "youtu.be",
    "music.youtube.com",
    "tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
    "facebook.com",
    "fb.watch",
    "m.facebook.com",
    "web.facebook.com",
    "instagram.com",
    "threads.net",
    "x.com",
    "twitter.com",
    "vimeo.com",
    "dailymotion.com",
    "dai.ly",
    "t.me",
    "telegram.me",
}

ADULT_VIDEO_PAGE_HOSTS = {
    "cam4.com": "cam4",
    "camsoda.com": "camsoda",
    "javgg.net": "javgg",
    "javgg.to": "javgg",
    "javhd.com": "javhd",
    "javlibrary.com": "javlibrary",
    "javmost.com": "javmost",
    "javmost.cx": "javmost",
    "livejasmin.com": "livejasmin",
    "missav.ai": "missav",
    "missav.com": "missav",
    "missav.ws": "missav",
    "r18.com": "r18",
    "stripchat.com": "stripchat",
    "supjav.com": "supjav",
}

DIRECT_MEDIA_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".mov",
    ".webm",
    ".avi",
    ".m4v",
    ".m3u8",
    ".mpd",
}
CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
CACHE_MAX_BYTES = 20 * 1024 * 1024 * 1024
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
BARE_ANSI_COLOR_RE = re.compile(r"(?:\[\])?\[[0-9;]{1,12}m")


def resolve_video_source(
    value: str,
    playback_quality: str = "720p",
    progress_callback=None,
    cancel_callback=None,
    *,
    full_cache: bool = True,
    language_id: str | None = None,
) -> VideoSource:
    url = value.strip()
    if not url:
        raise VideoSourceError(ui_text("video_error_empty_url", language_id))

    if is_telegram_web_progressive_url(url):
        raise VideoSourceError(ui_text("video_error_telegram_web_progressive", language_id))

    if _should_resolve_with_ytdlp(url):
        return _resolve_page_url(url, playback_quality, full_cache, progress_callback, cancel_callback, language_id)

    return VideoSource(input_url=url, playback_url=url, title=url, is_resolved=False)


def is_supported_video_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme.lower() in {"http", "https", "rtsp", "rtmp", "mms"} and bool(parsed.hostname)


def is_telegram_web_progressive_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    host = _url_host(parsed)
    path = parsed.path.lower()
    return parsed.scheme.lower() in {"http", "https"} and host == "web.telegram.org" and "/progressive/" in path


def _should_resolve_with_ytdlp(value: str) -> bool:
    parsed = urlparse(value.strip())
    host = _url_host(parsed)
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    if _looks_like_direct_media_url(parsed.path):
        return False
    return host in YTDLP_PAGE_HOSTS or _is_adult_video_page_host(host)


def _looks_like_direct_media_url(path: str) -> bool:
    return Path(path.lower()).suffix in DIRECT_MEDIA_EXTENSIONS


def _resolve_page_url(
    url: str,
    playback_quality: str,
    full_cache: bool,
    progress_callback=None,
    cancel_callback=None,
    language_id: str | None = None,
) -> VideoSource:
    provider = _provider_name(url)
    if provider == "buomtv":
        return _resolve_buomtv_url(url, playback_quality, full_cache, progress_callback, cancel_callback, language_id)

    try:
        import yt_dlp
    except ImportError as exc:
        raise VideoSourceError(ui_text("video_error_missing_ytdlp_page", language_id)) from exc

    provider = _provider_name(url)
    quality = _normalize_playback_quality(playback_quality)
    cache_dir = _source_cache_dir(provider, quality) if full_cache else None

    def check_cancelled() -> None:
        if cancel_callback is not None and cancel_callback():
            raise VideoSourceCancelled(ui_text("video_error_open_cancelled", language_id))

    check_cancelled()
    if full_cache and progress_callback is not None:
        progress_callback(
            {
                "status": "starting",
                "provider": provider,
                "quality": quality,
                "cache_dir": str(cache_dir or ""),
                "url": url,
            }
        )

    def progress_hook(data: dict) -> None:
        check_cancelled()
        if progress_callback is None:
            return
        progress_callback(
            {
                "status": str(data.get("status") or ""),
                "downloaded_bytes": data.get("downloaded_bytes"),
                "total_bytes": data.get("total_bytes") or data.get("total_bytes_estimate"),
                "speed": data.get("speed"),
                "eta": data.get("eta"),
                "filename": data.get("filename") or data.get("tmpfilename") or "",
                "provider": provider,
                "quality": quality,
                "cache_dir": str(cache_dir or ""),
                "url": url,
            }
        )

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": not full_cache,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "format": _format_selector(quality) if full_cache else _stream_format_selector(quality),
        "windowsfilenames": True,
    }
    if full_cache and cache_dir is not None:
        options.update(
            {
                "merge_output_format": "mp4",
                "outtmpl": str(cache_dir / "%(extractor_key)s-%(id)s-%(format_id)s-%(height)sp.%(ext)s"),
                "continuedl": True,
                "overwrites": False,
                "progress_hooks": [progress_hook],
            }
        )
    try:
        check_cancelled()
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=full_cache)
        check_cancelled()
    except VideoSourceCancelled:
        raise
    except Exception as exc:
        raise VideoSourceError(
            ui_text("video_error_download_failed", language_id, provider=provider, detail=_clean_download_error(exc))
        ) from exc

    if not full_cache:
        playback_url = _stream_playback_url(info)
        if not playback_url:
            raise VideoSourceError(ui_text("video_error_stream_url_missing", language_id, provider=provider))
        return VideoSource(
            input_url=url,
            playback_url=playback_url,
            title=str(info.get("title") or url),
            provider=provider,
            is_resolved=True,
        )

    if cache_dir is None:
        cache_dir = _source_cache_dir(provider, quality)
    local_path = _downloaded_file_path(info, cache_dir)
    if not local_path:
        raise VideoSourceError(ui_text("video_error_downloaded_file_missing", language_id, provider=provider))

    if progress_callback is not None:
        progress_callback(
            {
                "status": "cached",
                "provider": provider,
                "quality": quality,
                "cache_dir": str(cache_dir or ""),
                "filename": local_path,
                "url": url,
            }
        )

    return VideoSource(
        input_url=url,
        playback_url=local_path,
        title=str(info.get("title") or url),
        provider=provider,
        is_resolved=True,
    )


def _normalize_playback_quality(playback_quality: str) -> str:
    quality = str(playback_quality or "720p").strip().lower()
    return quality if quality in {"360p", "480p", "720p", "1080p", "best"} else "720p"


def _format_selector(playback_quality: str) -> str:
    max_height_by_quality = {
        "360p": 360,
        "480p": 480,
        "720p": 720,
        "1080p": 1080,
    }
    quality = _normalize_playback_quality(playback_quality)
    max_height = max_height_by_quality.get(quality)
    if max_height is None:
        return (
            "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/"
            "best[ext=mp4][vcodec^=avc1][acodec!=none]/"
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo+bestaudio/"
            "best[ext=mp4][vcodec!=none][acodec!=none]/"
            "best[vcodec!=none][acodec!=none]/best"
        )
    return (
        f"bestvideo[ext=mp4][vcodec^=avc1][height<={max_height}]+bestaudio[ext=m4a]/"
        f"best[ext=mp4][vcodec^=avc1][acodec!=none][height<={max_height}]/"
        f"bestvideo[ext=mp4][height<={max_height}]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={max_height}]+bestaudio/"
        f"best[ext=mp4][vcodec!=none][acodec!=none][height<={max_height}]/"
        f"best[vcodec!=none][acodec!=none][height<={max_height}]/"
        "best[ext=mp4][vcodec!=none][acodec!=none]/"
        "best[vcodec!=none][acodec!=none]/best"
    )


def _stream_format_selector(playback_quality: str) -> str:
    max_height_by_quality = {
        "360p": 360,
        "480p": 480,
        "720p": 720,
        "1080p": 1080,
    }
    quality = _normalize_playback_quality(playback_quality)
    max_height = max_height_by_quality.get(quality)
    height_filter = f"[height<={max_height}]" if max_height is not None else ""
    return (
        f"best[ext=mp4][vcodec^=avc1][acodec!=none]{height_filter}/"
        f"best[ext=mp4][vcodec!=none][acodec!=none]{height_filter}/"
        f"best[vcodec!=none][acodec!=none]{height_filter}/"
        "best[ext=mp4][vcodec^=avc1][acodec!=none]/"
        "best[ext=mp4][vcodec!=none][acodec!=none]/"
        "best[vcodec!=none][acodec!=none]/best"
    )


def _provider_name(value: str) -> str:
    host = _url_host(urlparse(value.strip()))
    host = host.removeprefix("m.").removeprefix("web.")
    if host in {"youtube.com", "youtu.be", "music.youtube.com"}:
        return "youtube"
    if host in {"tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}:
        return "tiktok"
    if host in {"facebook.com", "fb.watch"}:
        return "facebook"
    if host == "instagram.com":
        return "instagram"
    if host in {"x.com", "twitter.com"}:
        return "x-twitter"
    if host == "vimeo.com":
        return "vimeo"
    if host in {"dailymotion.com", "dai.ly"}:
        return "dailymotion"
    if host in {"t.me", "telegram.me"}:
        return "telegram"
    adult_provider = _adult_video_provider_name(host)
    if adult_provider:
        return adult_provider
    if _is_buomtv_host(host):
        return "buomtv"
    return re.sub(r"[^a-z0-9]+", "-", host.split(":")[0]).strip("-") or "url"


def _url_host(parsed) -> str:
    return str(parsed.hostname or "").lower().removeprefix("www.")


def _is_buomtv_host(host: str) -> bool:
    return host.startswith("buomtv.") or ".buomtv." in host


def _is_adult_video_page_host(host: str) -> bool:
    return _is_buomtv_host(host) or bool(_adult_video_provider_name(host))


def _adult_video_provider_name(host: str) -> str:
    if _is_chaturbate_host(host):
        return "chaturbate"
    if _is_bongacams_host(host):
        return "bongacams"
    for domain, provider in ADULT_VIDEO_PAGE_HOSTS.items():
        if _host_matches(host, domain):
            return provider
    return ""


def _is_chaturbate_host(host: str) -> bool:
    return any(_host_matches(host, domain) for domain in {"chaturbate.com", "chaturbate.eu", "chaturbate.global"})


def _is_bongacams_host(host: str) -> bool:
    return bool(re.fullmatch(r"(?:.+\.)?bongacams\d*\.(?:com|net)", host))


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def _resolve_buomtv_url(
    url: str,
    playback_quality: str,
    full_cache: bool,
    progress_callback=None,
    cancel_callback=None,
    language_id: str | None = None,
) -> VideoSource:
    provider = "buomtv"
    quality = _normalize_playback_quality(playback_quality)

    def check_cancelled() -> None:
        if cancel_callback is not None and cancel_callback():
            raise VideoSourceCancelled(ui_text("video_error_open_cancelled", language_id))

    check_cancelled()
    video_info = _fetch_buomtv_video_info(url, language_id)
    title = str(video_info.get("video_title") or url)
    stream_path = _select_buomtv_stream_url(
        video_info.get("video_urls") or {},
        quality,
        str(video_info.get("video_main_tag") or ""),
    )
    if not stream_path:
        raise VideoSourceError(ui_text("video_error_buomtv_stream_missing", language_id))
    stream_url = _absolute_buomtv_url(url, stream_path)

    if not full_cache:
        return VideoSource(input_url=url, playback_url=stream_url, title=title, provider=provider, is_resolved=True)

    try:
        import yt_dlp
    except ImportError as exc:
        raise VideoSourceError(ui_text("video_error_missing_ytdlp_buomtv", language_id)) from exc

    cache_dir = _source_cache_dir(provider, quality)
    if progress_callback is not None:
        progress_callback(
            {
                "status": "starting",
                "provider": provider,
                "quality": quality,
                "cache_dir": str(cache_dir),
                "url": url,
            }
        )

    def progress_hook(data: dict) -> None:
        check_cancelled()
        if progress_callback is None:
            return
        progress_callback(
            {
                "status": str(data.get("status") or ""),
                "downloaded_bytes": data.get("downloaded_bytes"),
                "total_bytes": data.get("total_bytes") or data.get("total_bytes_estimate"),
                "speed": data.get("speed"),
                "eta": data.get("eta"),
                "filename": data.get("filename") or data.get("tmpfilename") or "",
                "provider": provider,
                "quality": quality,
                "cache_dir": str(cache_dir),
                "url": url,
            }
        )

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": False,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "format": _format_selector(quality),
        "windowsfilenames": True,
        "merge_output_format": "mp4",
        "outtmpl": str(cache_dir / "%(extractor_key)s-%(id)s-%(format_id)s-%(height)sp.%(ext)s"),
        "continuedl": True,
        "overwrites": False,
        "progress_hooks": [progress_hook],
        "http_headers": _buomtv_headers(url),
    }

    try:
        check_cancelled()
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(stream_url, download=True)
        check_cancelled()
    except VideoSourceCancelled:
        raise
    except Exception as exc:
        raise VideoSourceError(
            ui_text("video_error_buomtv_download_failed", language_id, detail=_clean_download_error(exc))
        ) from exc

    local_path = _downloaded_file_path(info, cache_dir)
    if not local_path:
        raise VideoSourceError(ui_text("video_error_buomtv_downloaded_file_missing", language_id))

    if progress_callback is not None:
        progress_callback(
            {
                "status": "cached",
                "provider": provider,
                "quality": quality,
                "cache_dir": str(cache_dir),
                "filename": local_path,
                "url": url,
            }
        )

    return VideoSource(input_url=url, playback_url=local_path, title=title, provider=provider, is_resolved=True)


def _fetch_buomtv_video_info(url: str, language_id: str | None = None) -> dict:
    try:
        import requests
    except ImportError as exc:
        raise VideoSourceError(ui_text("video_error_missing_requests_buomtv", language_id)) from exc

    parsed = urlparse(url.strip())
    video_type, video_id = _parse_buomtv_video_path(parsed.path, language_id)
    api_base = _buomtv_api_base(parsed)
    headers = _buomtv_headers(url)
    session = requests.Session()

    try:
        token_response = session.post(
            f"{api_base}/pwa/register/pwatoken?version=old-web&lang=vi",
            data={"lang": "vi"},
            headers=headers,
            timeout=30,
        )
    except Exception as exc:
        raise VideoSourceError(ui_text("video_error_buomtv_token_api_failed", language_id, detail=exc)) from exc
    token_payload = _buomtv_response_json(token_response, "token", language_id)
    token = str(_dict_value(token_payload.get("response")).get("token") or "")
    if not token:
        raise VideoSourceError(ui_text("video_error_buomtv_token_missing", language_id))

    info_url = (
        f"{api_base}/pwa/video/info/{quote(video_id)}"
        f"?token={quote(token)}&video_type={video_type}&platform=web&lang=vi"
    )
    try:
        info_response = session.get(info_url, headers=headers, timeout=30)
    except Exception as exc:
        raise VideoSourceError(ui_text("video_error_buomtv_video_api_failed", language_id, detail=exc)) from exc
    payload = _buomtv_response_json(info_response, "video", language_id)
    status = _dict_value(payload.get("status"))
    if status.get("code") != 200:
        message = str(status.get("message") or ui_text("video_error_unknown", language_id))
        raise VideoSourceError(ui_text("video_error_buomtv_status", language_id, detail=message))
    return _dict_value(payload.get("response"))


def _buomtv_response_json(response, context: str, language_id: str | None = None) -> dict:
    try:
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
    except Exception as exc:
        raise VideoSourceError(ui_text("video_error_buomtv_http", language_id, context=context, detail=exc)) from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise VideoSourceError(ui_text("video_error_buomtv_invalid_json", language_id, context=context)) from exc
    if not isinstance(payload, dict):
        raise VideoSourceError(ui_text("video_error_buomtv_invalid_data", language_id, context=context))
    return payload


def _dict_value(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _parse_buomtv_video_path(path: str, language_id: str | None = None) -> tuple[str, str]:
    parts = [part for part in path.split("/") if part]
    if parts and parts[0] in {"th", "en", "cn"}:
        parts = parts[1:]
    if len(parts) >= 3 and parts[0] == "movie":
        return "long", parts[2]
    if len(parts) >= 2 and parts[0] == "video":
        return "short", parts[1]
    if len(parts) >= 2 and parts[0] == "anime":
        return "anime", parts[1]
    raise VideoSourceError(ui_text("video_error_buomtv_bad_url", language_id))


def _select_buomtv_stream_url(video_urls: dict, playback_quality: str, video_main_tag: str = "") -> str:
    if video_main_tag.strip().lower() == "vip" and video_urls.get("intro"):
        return str(video_urls.get("intro") or "")

    numeric_streams = sorted(
        (int(height), str(stream_url))
        for height, stream_url in video_urls.items()
        if str(height).isdigit() and stream_url
    )
    if not numeric_streams:
        return str(video_urls.get("intro") or "")

    quality = _normalize_playback_quality(playback_quality)
    max_height_by_quality = {
        "360p": 360,
        "480p": 480,
        "720p": 720,
        "1080p": 1080,
    }
    max_height = max_height_by_quality.get(quality)
    if max_height is None:
        return numeric_streams[-1][1]

    matching_streams = [(height, stream_url) for height, stream_url in numeric_streams if height <= max_height]
    if matching_streams:
        return matching_streams[-1][1]
    return numeric_streams[0][1]


def _absolute_buomtv_url(page_url: str, stream_path: str) -> str:
    stream_path = str(stream_path or "").strip()
    if stream_path.lower().startswith(("http://", "https://")):
        return stream_path
    return f"{_buomtv_api_base(urlparse(page_url.strip()))}/{stream_path.lstrip('/')}"


def _buomtv_api_base(parsed) -> str:
    scheme = parsed.scheme or "https"
    host = _url_host(parsed)
    return f"{scheme}://api.{host}"


def _buomtv_headers(page_url: str) -> dict[str, str]:
    parsed = urlparse(page_url.strip())
    origin = f"{parsed.scheme or 'https'}://{parsed.netloc}"
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125 Safari/537.36",
        "Origin": origin,
        "Referer": page_url,
    }


def _source_cache_dir(provider: str, playback_quality: str = "720p") -> Path:
    safe_provider = re.sub(r"[^a-z0-9_-]+", "-", provider.lower()).strip("-") or "url"
    safe_quality = re.sub(r"[^a-z0-9_-]+", "-", _normalize_playback_quality(playback_quality)).strip("-") or "720p"
    root = Path(tempfile.gettempdir()) / "ai-player-sources"
    _cleanup_cache_root(root)
    path = root / safe_provider / safe_quality
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cleanup_cache_root(
    root: Path,
    *,
    max_age_seconds: int = CACHE_MAX_AGE_SECONDS,
    max_bytes: int = CACHE_MAX_BYTES,
) -> None:
    try:
        if not root.exists():
            return
        now = time.time()
        files = [path for path in root.rglob("*") if path.is_file()]
        for path in files:
            try:
                if now - path.stat().st_mtime > max_age_seconds:
                    path.unlink()
            except OSError:
                pass
        files = [path for path in root.rglob("*") if path.is_file()]
        files_with_stats = []
        for path in files:
            try:
                stat = path.stat()
            except OSError:
                continue
            files_with_stats.append((path, stat.st_size, stat.st_mtime))
        total = sum(size for _path, size, _mtime in files_with_stats)
        for path, size, _mtime in sorted(files_with_stats, key=lambda item: item[2]):
            if total <= max_bytes:
                break
            try:
                path.unlink()
                total -= size
            except OSError:
                pass
        _remove_empty_dirs(root)
    except Exception:
        pass


def _remove_empty_dirs(root: Path) -> None:
    empty_dirs = (item for item in root.rglob("*") if item.is_dir())
    for path in sorted(empty_dirs, key=lambda item: len(item.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass


def _downloaded_file_path(info: dict, cache_dir: Path) -> str:
    candidates = []
    requested_downloads = info.get("requested_downloads") or []
    if isinstance(requested_downloads, list):
        candidates.extend(
            download.get("filepath") for download in requested_downloads if isinstance(download, dict)
        )
    candidates.extend([info.get("_filename"), info.get("filepath")])

    for candidate in candidates:
        path = Path(str(candidate or ""))
        if path.exists() and path.is_file():
            return str(path)

    video_id = str(info.get("id") or "")
    if video_id:
        for path in sorted(cache_dir.glob(f"*{video_id}.*")):
            if path.is_file() and path.suffix.lower() not in {".part", ".ytdl"}:
                return str(path)
    return ""


def _clean_download_error(value: object) -> str:
    text = str(value or "").replace("\r", "\n")
    text = ANSI_ESCAPE_RE.sub("", text)
    text = BARE_ANSI_COLOR_RE.sub("", text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    text = " ".join(line for line in lines if line)
    text = re.sub(r"\bERROR:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text or value.__class__.__name__


def _stream_playback_url(info: dict) -> str:
    direct_url = str(info.get("url") or "").strip()
    if direct_url:
        return direct_url

    requested_formats = info.get("requested_formats") or []
    requested_formats = (
        [item for item in requested_formats if isinstance(item, dict)]
        if isinstance(requested_formats, list)
        else []
    )
    if len(requested_formats) == 1:
        return str(requested_formats[0].get("url") or "").strip()

    formats = info.get("formats") or []
    formats = [item for item in formats if isinstance(item, dict)] if isinstance(formats, list) else []
    playable_formats = [
        video_format
        for video_format in formats
        if str(video_format.get("url") or "").strip()
        and str(video_format.get("vcodec") or "none") != "none"
        and str(video_format.get("acodec") or "none") != "none"
    ]
    if playable_formats:
        return str(playable_formats[-1].get("url") or "").strip()
    return ""
