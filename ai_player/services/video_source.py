from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urljoin, urlparse

from ai_player.core.i18n import ui_text
from ai_player.core.redaction import compact_redacted_text
from ai_player.services.ffmpeg import ffmpeg_executable, run_ffmpeg, run_ffprobe


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
    width: int = 0
    height: int = 0


@dataclass(frozen=True)
class VideoUrlPreflight:
    url: str
    supported: bool
    provider: str = ""
    source_kind: str = "unsupported"
    requires_ytdlp: bool = False
    direct_media: bool = False


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
    "njav.com",
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
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
BARE_ANSI_COLOR_RE = re.compile(r"(?:\[\])?\[[0-9;]{1,12}m")


def resolve_video_source(
    value: str,
    playback_quality: str = "720p",
    progress_callback=None,
    cancel_callback=None,
    *,
    full_cache: bool = True,
    cache_dir: str | Path | None = None,
    language_id: str | None = None,
) -> VideoSource:
    url = value.strip()
    if not url:
        raise VideoSourceError(ui_text("video_error_empty_url", language_id))

    if is_telegram_web_progressive_url(url):
        raise VideoSourceError(ui_text("video_error_telegram_web_progressive", language_id))
    if _is_private_telegram_url(url):
        raise VideoSourceError(ui_text("video_error_telegram_private_url", language_id))

    if _should_resolve_with_ytdlp(url):
        return _resolve_page_url(
            url,
            playback_quality,
            full_cache,
            progress_callback,
            cancel_callback,
            language_id,
            cache_dir=cache_dir,
        )

    return VideoSource(input_url=url, playback_url=url, title=url, is_resolved=False)


def is_supported_video_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme.lower() in {"http", "https", "rtsp", "rtmp", "mms"} and bool(parsed.hostname)


def is_supported_browser_video_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    scheme = parsed.scheme.lower()
    if scheme in {"rtsp", "rtmp", "mms"}:
        return bool(parsed.hostname)
    if scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if _looks_like_direct_media_url(parsed.path):
        return True
    host = _url_host(parsed)
    return host in YTDLP_PAGE_HOSTS or _is_extra_ytdlp_host(host) or _has_plugin_ytdlp_extractor(value)


def inspect_video_url(value: str) -> VideoUrlPreflight:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if not is_supported_video_url(url):
        return VideoUrlPreflight(url=url, supported=False)
    scheme = parsed.scheme.lower()
    if is_telegram_web_progressive_url(url):
        return VideoUrlPreflight(url=url, supported=True, provider="telegram", source_kind="telegram_web")
    if _is_private_telegram_url(url):
        return VideoUrlPreflight(url=url, supported=True, provider="telegram", source_kind="private_telegram")
    if scheme not in {"http", "https"}:
        return VideoUrlPreflight(url=url, supported=True, provider=scheme, source_kind="network_stream")
    provider = _provider_name(url)
    if _looks_like_direct_media_url(parsed.path):
        return VideoUrlPreflight(
            url=url,
            supported=True,
            provider=provider,
            source_kind="direct_media",
            direct_media=True,
        )
    if _should_resolve_with_ytdlp(url):
        return VideoUrlPreflight(
            url=url,
            supported=True,
            provider=provider,
            source_kind="page",
            requires_ytdlp=True,
        )
    return VideoUrlPreflight(url=url, supported=True, provider=provider, source_kind="network_stream")


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
    if _is_private_telegram_url(value):
        return False
    return host in YTDLP_PAGE_HOSTS or _is_extra_ytdlp_host(host) or _has_plugin_ytdlp_extractor(value)


def _looks_like_direct_media_url(path: str) -> bool:
    return Path(path.lower()).suffix in DIRECT_MEDIA_EXTENSIONS


def _resolve_page_url(
    url: str,
    playback_quality: str,
    full_cache: bool,
    progress_callback=None,
    cancel_callback=None,
    language_id: str | None = None,
    *,
    cache_dir: str | Path | None = None,
) -> VideoSource:
    try:
        import yt_dlp
    except ImportError as exc:
        raise VideoSourceError(ui_text("video_error_missing_ytdlp_page", language_id)) from exc

    provider = _provider_name(url)
    quality = _normalize_playback_quality(playback_quality)
    source_cache_dir = _source_cache_dir(provider, quality, cache_root=cache_dir) if full_cache else None

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
                "cache_dir": str(source_cache_dir or ""),
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
                "cache_dir": str(source_cache_dir or ""),
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
    allowed_extractors = _allowed_extractors(provider)
    if allowed_extractors:
        options["allowed_extractors"] = allowed_extractors
    if full_cache and source_cache_dir is not None:
        options.update(
            {
                "merge_output_format": "mp4",
                "ffmpeg_location": str(Path(ffmpeg_executable()).parent),
                "outtmpl": str(source_cache_dir / "%(extractor_key)s-%(id)s-%(format_id)s-%(height)sp.%(ext)s"),
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
        if not isinstance(info, dict):
            raise VideoSourceError(ui_text("video_error_info_missing", language_id, provider=provider))
    except VideoSourceCancelled:
        raise
    except VideoSourceError:
        raise
    except Exception as exc:
        detail = _clean_download_error(exc)
        if "Unable to find embedded media URL" in detail:
            fallback_source = _resolve_vlxx_wrapped_hls(
                url,
                provider,
                quality,
                cache_dir=cache_dir,
                progress_callback=progress_callback,
                cancel_callback=cancel_callback,
                language_id=language_id,
            )
            if fallback_source is not None:
                return fallback_source
            raise VideoSourceError(ui_text("video_error_usable_media_missing", language_id, provider=provider)) from exc
        raise VideoSourceError(
            ui_text("video_error_download_failed", language_id, provider=provider, detail=detail)
        ) from exc

    if not full_cache:
        playback_url = _stream_playback_url(info)
        if not playback_url:
            raise VideoSourceError(ui_text("video_error_stream_url_missing", language_id, provider=provider))
        width, height = _video_dimensions_from_info(info)
        return VideoSource(
            input_url=url,
            playback_url=playback_url,
            title=str(info.get("title") or url),
            provider=provider,
            is_resolved=True,
            width=width,
            height=height,
        )

    if source_cache_dir is None:
        source_cache_dir = _source_cache_dir(provider, quality, cache_root=cache_dir)
    local_path = _downloaded_file_path(info, source_cache_dir)
    if not local_path:
        raise VideoSourceError(ui_text("video_error_downloaded_file_missing", language_id, provider=provider))
    if not _video_file_has_audio(local_path):
        _remove_cached_file(local_path)
        raise VideoSourceError(ui_text("video_error_no_audio_stream", language_id, provider=provider))

    if progress_callback is not None:
        progress_callback(
            {
                "status": "cached",
                "provider": provider,
                "quality": quality,
                "cache_dir": str(source_cache_dir or ""),
                "filename": local_path,
                "url": url,
            }
        )

    width, height = _video_dimensions_from_info(info)
    return VideoSource(
        input_url=url,
        playback_url=local_path,
        title=str(info.get("title") or url),
        provider=provider,
        is_resolved=True,
        width=width,
        height=height,
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
            "best[vcodec!=none][acodec!=none]"
        )
    return (
        f"bestvideo[ext=mp4][vcodec^=avc1][height<={max_height}]+bestaudio[ext=m4a]/"
        f"best[ext=mp4][vcodec^=avc1][acodec!=none][height<={max_height}]/"
        f"bestvideo[ext=mp4][height<={max_height}]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={max_height}]+bestaudio/"
        f"best[ext=mp4][vcodec!=none][acodec!=none][height<={max_height}]/"
        f"best[vcodec!=none][acodec!=none][height<={max_height}]/"
        "best[ext=mp4][vcodec!=none][acodec!=none]/"
        "best[vcodec!=none][acodec!=none]"
    )


def _allowed_extractors(provider: str) -> list[str]:
    if provider == "telegram":
        return ["telegram:embed"]
    if provider == "tiktok":
        return [r"tiktok(:.*)?", r"vm\.tiktok"]
    return []


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
        "best[vcodec!=none][acodec!=none]"
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


def _is_private_telegram_url(value: str) -> bool:
    parsed = urlparse(str(value or "").strip())
    host = _url_host(parsed)
    if host not in {"t.me", "telegram.me"}:
        return False
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) == 1 and parts[0].startswith("+") and len(parts[0]) > 1:
        return True
    if len(parts) == 2 and parts[0] == "joinchat" and bool(parts[1]):
        return True
    return len(parts) == 3 and parts[0] == "c" and parts[1].isdigit() and parts[2].isdigit()


def _host_matches(host: str, domain: str) -> bool:
    if "*" in domain:
        pattern = re.escape(domain).replace(r"\*", r"[^.]+")
        return bool(re.fullmatch(pattern, host))
    return host == domain or host.endswith(f".{domain}")


def _is_extra_ytdlp_host(host: str) -> bool:
    return any(_host_matches(host, extra_host) for extra_host in _extra_ytdlp_hosts())


def _has_plugin_ytdlp_extractor(value: str) -> bool:
    return any(_extractor_suitable(extractor, value) for extractor in _plugin_ytdlp_extractors())


@lru_cache(maxsize=1)
def _plugin_ytdlp_extractors() -> tuple[object, ...]:
    try:
        import yt_dlp
    except ImportError:
        return ()
    try:
        extractors = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True})._ies.values()
    except Exception:
        return ()
    return tuple(
        extractor
        for extractor in extractors
        if getattr(extractor, "IE_NAME", "") != "generic"
        and str(getattr(extractor, "__module__", "")).startswith("yt_dlp_plugins.")
    )


def _extractor_suitable(extractor: object, value: str) -> bool:
    suitable = getattr(extractor, "suitable", None)
    if not callable(suitable):
        return False
    try:
        return bool(suitable(value))
    except Exception:
        return False


def _extra_ytdlp_hosts() -> tuple[str, ...]:
    hosts = []
    for raw_host in os.getenv("AI_PLAYER_EXTRA_YTDLP_HOSTS", "").replace(";", ",").split(","):
        host = _normalize_extra_ytdlp_host(raw_host)
        if host:
            hosts.append(host)
    return tuple(dict.fromkeys(hosts))


def _normalize_extra_ytdlp_host(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "://" in text:
        text = _url_host(urlparse(text))
    else:
        text = text.split("/", 1)[0].split(":", 1)[0]
        if not text.startswith("*."):
            text = text.removeprefix("www.")
    return text.strip(".")


def default_video_cache_root() -> Path:
    return Path(tempfile.gettempdir()) / "ai-player-sources"


def _source_cache_dir(provider: str, playback_quality: str = "720p", *, cache_root: str | Path | None = None) -> Path:
    safe_provider = re.sub(r"[^a-z0-9_-]+", "-", provider.lower()).strip("-") or "url"
    safe_quality = re.sub(r"[^a-z0-9_-]+", "-", _normalize_playback_quality(playback_quality)).strip("-") or "720p"
    root = _video_cache_root(cache_root)
    _cleanup_cache_root(root)
    path = root / safe_provider / safe_quality
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_vlxx_wrapped_hls(
    url: str,
    provider: str,
    quality: str,
    *,
    cache_dir: str | Path | None = None,
    progress_callback=None,
    cancel_callback=None,
    language_id: str | None = None,
) -> VideoSource | None:
    if not _is_vlxx_url(url):
        return None
    try:
        import requests
    except ImportError:
        return None

    def check_cancelled() -> None:
        if cancel_callback is not None and cancel_callback():
            raise VideoSourceCancelled(ui_text("video_error_open_cancelled", language_id))

    video_id = _vlxx_video_id(url)
    source_cache_dir = _source_cache_dir(provider, quality, cache_root=cache_dir)
    output_path = source_cache_dir / f"VLXX-{video_id}-wrapped-hls.mp4"
    if output_path.exists() and _video_file_has_audio(output_path):
        return VideoSource(
            input_url=url,
            playback_url=str(output_path),
            title=video_id,
            provider=provider,
            is_resolved=True,
        )
    _remove_cached_file(output_path)

    session = requests.Session()
    headers = _browser_headers(url)
    try:
        check_cancelled()
        webpage = session.get(url, headers=headers, timeout=30).text
        player_urls = _vlxx_player_urls(url, video_id, webpage, session, headers)
        for player_url in player_urls:
            check_cancelled()
            player_headers = _browser_headers(player_url, referer=url)
            player_page = session.get(player_url, headers=player_headers, timeout=30).text
            manifest_urls = _vlxx_manifest_urls(player_url, player_page)
            title = _html_title(player_page) or _html_title(webpage) or video_id
            for manifest_url in manifest_urls:
                check_cancelled()
                if progress_callback is not None:
                    progress_callback(
                        {
                            "status": "downloading",
                            "provider": provider,
                            "quality": quality,
                            "cache_dir": str(source_cache_dir),
                            "filename": str(output_path),
                            "url": url,
                        }
                    )
                if _download_wrapped_hls(
                    manifest_url,
                    output_path,
                    session,
                    _browser_headers(manifest_url, referer=player_url),
                    progress_callback=progress_callback,
                    cancel_callback=cancel_callback,
                    provider=provider,
                    quality=quality,
                    cache_dir=source_cache_dir,
                    source_url=url,
                ):
                    if _video_file_has_audio(output_path):
                        width, height = _video_dimensions_from_file(output_path)
                        return VideoSource(
                            input_url=url,
                            playback_url=str(output_path),
                            title=title,
                            provider=provider,
                            is_resolved=True,
                            width=width,
                            height=height,
                        )
                    _remove_cached_file(output_path)
    except VideoSourceCancelled:
        raise
    except Exception:
        _remove_cached_file(output_path)
        return None
    return None


def _download_wrapped_hls(
    manifest_url: str,
    output_path: Path,
    session,
    headers: dict,
    *,
    progress_callback=None,
    cancel_callback=None,
    provider: str = "",
    quality: str = "",
    cache_dir: Path | None = None,
    source_url: str = "",
) -> bool:
    playlist = session.get(manifest_url, headers=headers, timeout=30).text
    segment_urls = _hls_segment_urls(manifest_url, playlist)
    if not segment_urls:
        return False

    temp_ts = output_path.with_suffix(".part.ts")
    temp_mp4 = output_path.with_suffix(".part.mp4")
    _remove_cached_file(temp_ts)
    _remove_cached_file(temp_mp4)
    downloaded_bytes = 0
    try:
        with temp_ts.open("wb") as output:
            for index, segment_url in enumerate(segment_urls, start=1):
                if cancel_callback is not None and cancel_callback():
                    raise VideoSourceCancelled()
                response = session.get(segment_url, headers=headers, timeout=60)
                response.raise_for_status()
                payload = response.content
                offset = _mpeg_ts_payload_offset(payload)
                if offset < 0:
                    return False
                output.write(payload[offset:])
                downloaded_bytes += len(payload)
                if progress_callback is not None:
                    progress_callback(
                        {
                            "status": "downloading",
                            "downloaded_bytes": downloaded_bytes,
                            "total_bytes": max(downloaded_bytes, len(segment_urls)),
                            "eta": max(0, len(segment_urls) - index),
                            "provider": provider,
                            "quality": quality,
                            "cache_dir": str(cache_dir or ""),
                            "filename": str(output_path),
                            "url": source_url,
                        }
                    )
        run_ffmpeg(
            [
                "-y",
                "-i",
                temp_ts,
                "-map",
                "0:v:0?",
                "-map",
                "0:a:0?",
                "-c",
                "copy",
                "-bsf:a",
                "aac_adtstoasc",
                temp_mp4,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        shutil.move(str(temp_mp4), output_path)
        return output_path.exists()
    finally:
        _remove_cached_file(temp_ts)
        _remove_cached_file(temp_mp4)


def _is_vlxx_url(url: str) -> bool:
    return _url_host(urlparse(url)).startswith("vlxx.")


def _vlxx_video_id(url: str) -> str:
    matched = re.search(r"/(\d+)/?(?:[?#].*)?$", url)
    if matched:
        return matched.group(1)
    path = urlparse(url).path.rstrip("/")
    return Path(path).name or "vlxx"


def _vlxx_player_urls(page_url: str, video_id: str, webpage: str, session, headers: dict) -> list[str]:
    escaped_video_id = re.escape(video_id)
    server_ids = dict.fromkeys(
        re.findall(rf"""(?i)\bserver\s*\(\s*(\d+)\s*,\s*{escaped_video_id}\s*\)""", webpage)
        + re.findall(r"""(?i)\bdata-sv=["'](\d+)["']""", webpage)
        + ["1", "2"]
    )
    urls = []
    for server_id in server_ids:
        response = session.post(
            urljoin(page_url, "/ajax.php"),
            data={"vlxx_server": "1", "id": video_id, "server": server_id},
            headers={**headers, "X-Requested-With": "XMLHttpRequest"},
            timeout=30,
        )
        response.raise_for_status()
        try:
            ajax_data = response.json()
        except ValueError:
            ajax_data = {}
        player_html = str(ajax_data.get("player") or response.text) if isinstance(ajax_data, dict) else response.text
        urls.extend(_iframe_urls(page_url, player_html))
    return list(dict.fromkeys(urls))


def _vlxx_manifest_urls(player_url: str, player_page: str) -> list[str]:
    urls = re.findall(r"""https?:\\/\\/[^"']+?\.vl(?:[?#][^"']*)?(?=["'])""", player_page)
    urls.extend(re.findall(r"""https?://[^\s"'<>\\]+?\.vl(?:[?#][^\s"'<>\\]+)?(?=[\s"'<>]|$)""", player_page))
    return list(dict.fromkeys(_clean_url(player_url, url) for url in urls if _clean_url(player_url, url)))


def _iframe_urls(page_url: str, html: str) -> list[str]:
    urls = []
    for match in re.finditer(r"""(?is)<iframe[^>]+(?:src|data-src)=["'](?P<url>[^"']+)["']""", html):
        cleaned = _clean_url(page_url, match.group("url"))
        if cleaned:
            urls.append(cleaned)
    return urls


def _hls_segment_urls(playlist_url: str, playlist: str) -> list[str]:
    urls = []
    for line in playlist.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cleaned = _clean_url(playlist_url, line)
        if cleaned:
            urls.append(cleaned)
    return urls


def _mpeg_ts_payload_offset(payload: bytes) -> int:
    for offset in range(min(512, len(payload))):
        if payload[offset] != 0x47 or offset + 188 * 5 >= len(payload):
            continue
        if all(payload[offset + 188 * index] == 0x47 for index in range(6)):
            return offset
    return -1


def _clean_url(page_url: str, value: str | None) -> str | None:
    if not value:
        return None
    cleaned = str(value).replace("\\/", "/").strip()
    absolute_url = urljoin(page_url, cleaned)
    return absolute_url if is_supported_video_url(absolute_url) else None


def _browser_headers(url: str, *, referer: str | None = None) -> dict:
    return {
        "Referer": referer or url,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125 Safari/537.36"
        ),
    }


def _html_title(html: str) -> str:
    matched = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    if not matched:
        return ""
    return re.sub(r"\s+", " ", matched.group(1)).strip()


def _video_cache_root(cache_root: str | Path | None = None) -> Path:
    text = str(cache_root or "").strip()
    return Path(text).expanduser() / "ai-player-sources" if text else default_video_cache_root()


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


def _video_file_has_audio(path: str | Path) -> bool:
    try:
        completed = run_ffprobe(
            [
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=index",
                "-of",
                "csv=p=0",
                path,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return True
    return completed.returncode == 0 and bool(str(completed.stdout or "").strip())


def _video_dimensions_from_file(path: str | Path) -> tuple[int, int]:
    try:
        completed = run_ffprobe(
            [
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0:s=x",
                path,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return 0, 0
    match = re.search(r"(\d+)x(\d+)", str(completed.stdout or ""))
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


def _remove_cached_file(path: str | Path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _clean_download_error(value: object) -> str:
    text = str(value or "").replace("\r", "\n")
    text = ANSI_ESCAPE_RE.sub("", text)
    text = BARE_ANSI_COLOR_RE.sub("", text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    text = " ".join(line for line in lines if line)
    text = re.sub(r"\bERROR:\s*", "", text, flags=re.IGNORECASE)
    text = compact_redacted_text(re.sub(r"\s+", " ", text).strip())
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


def _video_dimensions_from_info(info: dict) -> tuple[int, int]:
    for candidate in _video_dimension_candidates(info):
        if not isinstance(candidate, dict):
            continue
        width = _positive_dimension(candidate.get("width"))
        height = _positive_dimension(candidate.get("height"))
        if width and height:
            return width, height
    return 0, 0


def _video_dimension_candidates(info: dict):
    yield info
    requested_downloads = info.get("requested_downloads") if isinstance(info, dict) else None
    if isinstance(requested_downloads, list):
        yield from requested_downloads
    requested_formats = info.get("requested_formats") if isinstance(info, dict) else None
    if isinstance(requested_formats, list):
        yield from requested_formats
    formats = info.get("formats") if isinstance(info, dict) else None
    if isinstance(formats, list):
        yield from formats


def _positive_dimension(value: object) -> int:
    try:
        parsed = int(float(str(value or "").strip()))
    except (OverflowError, TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0
