from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


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


def resolve_video_source(
    value: str,
    playback_quality: str = "720p",
    progress_callback=None,
    cancel_callback=None,
    *,
    full_cache: bool = True,
) -> VideoSource:
    url = value.strip()
    if not url:
        raise VideoSourceError("URL rỗng.")

    if _should_resolve_with_ytdlp(url):
        return _resolve_page_url(url, playback_quality, full_cache, progress_callback, cancel_callback)

    return VideoSource(input_url=url, playback_url=url, title=url, is_resolved=False)


def is_supported_video_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme.lower() in {"http", "https", "rtsp", "rtmp", "mms"} and bool(parsed.hostname)


def _should_resolve_with_ytdlp(value: str) -> bool:
    parsed = urlparse(value.strip())
    host = _url_host(parsed)
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    if _looks_like_direct_media_url(parsed.path):
        return False
    return host in YTDLP_PAGE_HOSTS


def _looks_like_direct_media_url(path: str) -> bool:
    return Path(path.lower()).suffix in DIRECT_MEDIA_EXTENSIONS


def _resolve_page_url(
    url: str,
    playback_quality: str,
    full_cache: bool,
    progress_callback=None,
    cancel_callback=None,
) -> VideoSource:
    try:
        import yt_dlp
    except ImportError as exc:
        raise VideoSourceError(
            "Thiếu yt-dlp để mở link trang video. Chạy: "
            ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
        ) from exc

    provider = _provider_name(url)
    quality = _normalize_playback_quality(playback_quality)
    cache_dir = _source_cache_dir(provider, quality) if full_cache else None

    def check_cancelled() -> None:
        if cancel_callback is not None and cancel_callback():
            raise VideoSourceCancelled("Da huy mo URL.")

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
        raise VideoSourceError(f"Không tải được video từ {provider}: {exc}") from exc

    if not full_cache:
        playback_url = _stream_playback_url(info)
        if not playback_url:
            raise VideoSourceError(f"Khong tim thay URL phat truc tiep tu {provider}.")
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
        raise VideoSourceError(f"Không tìm thấy file video {provider} đã tải.")

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
    return re.sub(r"[^a-z0-9]+", "-", host.split(":")[0]).strip("-") or "url"


def _url_host(parsed) -> str:
    return str(parsed.hostname or "").lower().removeprefix("www.")


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
    candidates.extend(download.get("filepath") for download in requested_downloads)
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


def _stream_playback_url(info: dict) -> str:
    direct_url = str(info.get("url") or "").strip()
    if direct_url:
        return direct_url

    requested_formats = info.get("requested_formats") or []
    if len(requested_formats) == 1:
        return str(requested_formats[0].get("url") or "").strip()

    formats = info.get("formats") or []
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
