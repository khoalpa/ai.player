from __future__ import annotations

import json
import os
import re
from importlib import resources
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.networking import HEADRequest
from yt_dlp.utils import ExtractorError, determine_ext, int_or_none, js_to_json, unescapeHTML, url_or_none, urljoin


def _load_site_registry() -> dict[str, dict[str, object]]:
    registry = _read_bundled_site_registry()
    for path in _local_registry_paths():
        local_registry = _read_json_registry(path)
        if local_registry:
            registry = _merge_site_registry(registry, local_registry)
    return registry


def _read_bundled_site_registry() -> dict[str, dict[str, object]]:
    try:
        text = resources.files(__package__).joinpath("adult_sites_registry.json").read_text(encoding="utf-8")
    except Exception:
        try:
            text = Path(__file__).with_name("adult_sites_registry.json").read_text(encoding="utf-8")
        except OSError:
            return {}
    return _registry_from_text(text)


def _read_json_registry(path: Path) -> dict[str, dict[str, object]]:
    try:
        return _registry_from_text(path.read_text(encoding="utf-8"))
    except OSError:
        return {}


def _registry_from_text(text: str) -> dict[str, dict[str, object]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def _local_registry_paths() -> tuple[Path, ...]:
    paths = []
    for raw_path in str(os.getenv("AI_PLAYER_ADULT_SITES_REGISTRY") or "").split(os.pathsep):
        if raw_path.strip():
            paths.append(Path(raw_path.strip()))
    project_root = Path(os.getenv("AI_PLAYER_PROJECT_ROOT") or Path.cwd())
    paths.append(project_root / "data" / "config" / "private" / "adult_sites.local.json")
    return tuple(dict.fromkeys(paths))


def _merge_site_registry(
    base: dict[str, dict[str, object]],
    override: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    merged = {key: dict(value) for key, value in base.items()}
    for key, value in override.items():
        current = dict(merged.get(key, {}))
        current.update(value)
        merged[key] = current
    return merged


SITE_REGISTRY = _load_site_registry()


def _registry_hosts() -> tuple[str, ...]:
    hosts = []
    for value in SITE_REGISTRY.values():
        domains = value.get("domains")
        if isinstance(domains, list):
            hosts.extend(str(domain) for domain in domains if str(domain).strip())
    return tuple(dict.fromkeys(hosts))


ADULT_SITE_HOSTS = _registry_hosts()


def _profile_delegates_to_ytdlp(profile: dict[str, object]) -> bool:
    return bool(profile.get("delegate_to_ytdlp"))


class _AdultSiteBaseIE(InfoExtractor):
    _DOMAINS: tuple[str, ...] = ()
    _IFRAME_DEPTH = 1
    _SITE_KEY = ""

    def _extract_adult_site(self, url: str, video_id: str | None = None) -> dict:
        video_id = video_id or self._generic_id(url)
        webpage = self._download_webpage(url, video_id, headers=self._adult_site_headers(url))
        return self._extract_from_webpage(url, video_id, webpage, self._iframe_depth_for_url(url))

    def _extract_from_webpage(self, url: str, video_id: str, webpage: str, iframe_depth: int) -> dict:
        title = self._adult_site_title(url, webpage)
        thumbnail = self._html_search_meta(
            ("og:image", "twitter:image", "thumbnail"),
            webpage,
            "thumbnail",
            default=None,
        )
        duration = int_or_none(
            self._search_regex(
                (
                    r'"duration"\s*:\s*"?(\d+)"?',
                    r"duration\s*[:=]\s*['\"]?(\d+)['\"]?",
                    r"<meta[^>]+(?:itemprop|property|name)=['\"]duration['\"][^>]+content=['\"](\d+)['\"]",
                ),
                webpage,
                "duration",
                default=None,
            )
        )

        formats = self._extract_media_formats(url, video_id, webpage)
        if formats:
            return {
                "id": video_id,
                "title": title,
                "thumbnail": urljoin(url, thumbnail) if thumbnail else None,
                "duration": duration,
                "age_limit": 18,
                "formats": formats,
            }

        iframe_url = self._find_iframe_url(url, webpage)
        if iframe_url:
            if iframe_depth <= 0:
                return self.url_result(iframe_url)
            try:
                iframe_webpage = self._download_webpage(
                    iframe_url,
                    video_id,
                    note="Downloading embedded player webpage",
                    fatal=False,
                    headers=self._adult_site_headers(iframe_url, referer=url),
                )
            except ExtractorError:
                iframe_webpage = None
            if iframe_webpage:
                iframe_result = self._extract_from_webpage(iframe_url, video_id, iframe_webpage, iframe_depth - 1)
                iframe_result.setdefault("title", title)
                iframe_result.setdefault("thumbnail", urljoin(url, thumbnail) if thumbnail else None)
                return iframe_result
            return self.url_result(iframe_url, video_id=video_id, video_title=title)

        raise ExtractorError("Unable to find embedded media URL", expected=True)

    def _extract_media_formats(self, page_url: str, video_id: str, webpage: str) -> list[dict]:
        formats = []
        seen_urls = set()
        for media_url in self._find_media_urls(page_url, webpage):
            if media_url in seen_urls:
                continue
            seen_urls.add(media_url)
            ext = determine_ext(media_url)
            if ext in {"m3u8", "vl"}:
                if ext == "vl" and self._hls_playlist_looks_like_image_sequence(page_url, video_id, media_url):
                    continue
                headers = self._adult_site_headers(page_url)
                formats.extend(
                    self._formats_with_headers(
                        self._extract_m3u8_formats(
                            media_url,
                            video_id,
                            "mp4",
                            m3u8_id="hls",
                            fatal=False,
                            headers=headers,
                        ),
                        headers,
                    )
                )
            elif ext == "mpd":
                headers = self._adult_site_headers(page_url)
                formats.extend(
                    self._formats_with_headers(
                        self._extract_mpd_formats(media_url, video_id, mpd_id="dash", fatal=False),
                        headers,
                    )
                )
            elif ext in {"mp4", "m4v", "webm", "mov"}:
                formats.append({"url": media_url, "ext": ext, "http_headers": self._adult_site_headers(page_url)})
        return formats

    @staticmethod
    def _formats_with_headers(formats: list[dict], headers: dict) -> list[dict]:
        updated = []
        for item in formats or []:
            if not isinstance(item, dict):
                continue
            cloned = dict(item)
            current_headers = cloned.get("http_headers")
            if isinstance(current_headers, dict):
                cloned["http_headers"] = {**headers, **current_headers}
            else:
                cloned["http_headers"] = dict(headers)
            updated.append(cloned)
        return updated

    def _hls_playlist_looks_like_image_sequence(self, page_url: str, video_id: str, media_url: str) -> bool:
        playlist = self._download_webpage(
            media_url,
            video_id,
            note="Checking .vl playlist",
            fatal=False,
            headers=self._adult_site_headers(page_url),
        )
        if not isinstance(playlist, str):
            return False
        segment_url = self._first_hls_segment_url(media_url, playlist)
        if not segment_url:
            return False
        response = None
        try:
            response = self._request_webpage(
                HEADRequest(segment_url, headers=self._adult_site_headers(page_url)),
                video_id,
                note="Checking .vl segment type",
                fatal=False,
            )
            if response is False:
                return False
            content_type = str(response.headers.get("Content-Type") or response.headers.get("content-type") or "")
        except ExtractorError:
            return False
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
        return content_type.lower().split(";", 1)[0].strip().startswith("image/")

    def _first_hls_segment_url(self, playlist_url: str, playlist: str) -> str | None:
        for line in playlist.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            return url_or_none(urljoin(playlist_url, line))
        return None

    def _find_media_urls(self, page_url: str, webpage: str) -> list[str]:
        candidates = []
        meta_video_url = self._html_search_meta(
            ("og:video", "og:video:url", "og:video:secure_url", "twitter:player:stream"),
            webpage,
            "video url",
            default=None,
        )
        if meta_video_url:
            candidates.append(meta_video_url)
        candidates.extend(self._html_content_url_meta_urls(webpage))
        candidates.extend(self._html_media_attribute_urls(webpage))
        for match in re.finditer(
            r"""(?ix)
            ["'](?P<quoted>https?:\\/\\/[^"']+\.(?:m3u8|mpd|mp4|m4v|webm|vl)(?:\?[^"']*)?)["']
            |
            (?P<bare>https?://[^\s"'<>\\]+\.(?:m3u8|mpd|mp4|m4v|webm|vl)(?:\?[^\s"'<>\\]+)?)
            |
            (?:contentUrl|content_url|dashUrl|dash_url|downloadUrl|download_url|file|fileUrl|file_url|hls|hlsUrl|hls_url|manifest|master|masterUrl|master_url|media|mp4Url|mp4_url|playUrl|play_url|src|source|sourceUrl|source_url|stream|streamUrl|stream_url|url|video|videoSrc|video_src|videoUrl|video_url)\s*[:=]\s*["'](?P<named>[^"']+\.(?:m3u8|mpd|mp4|m4v|webm|vl)(?:\?[^"']*)?)["']
            |
            (?:file|quality|src|source|video)[_-]?(?:\d{3,4}p?|hd|sd)\s*[:=]\s*["'](?P<quality>[^"']+\.(?:m3u8|mpd|mp4|m4v|webm|vl)(?:\?[^"']*)?)["']
            |
            \.src\(\s*["'](?P<src_call>[^"']+\.(?:m3u8|mpd|mp4|m4v|webm|vl)(?:\?[^"']*)?)["']\s*\)
            """,
            webpage,
        ):
            candidates.append(
                match.group("quoted")
                or match.group("bare")
                or match.group("named")
                or match.group("quality")
                or match.group("src_call")
            )

        for payload in self._json_payloads_from_webpage(webpage):
            candidates.extend(self._media_candidates_from_json(page_url, payload))
        candidates.extend(self._configured_pattern_urls(page_url, webpage, "media_patterns"))

        return [url for url in (self._clean_media_url(page_url, candidate) for candidate in candidates) if url]

    def _html_content_url_meta_urls(self, webpage: str) -> list[str]:
        urls = []
        for match in re.finditer(
            r"""(?is)<meta[^>]+(?:itemprop|property|name)=["'](?:contentUrl|video|video:url)["'][^>]+content=["'](?P<url>[^"']+)["']""",
            webpage,
        ):
            urls.append(match.group("url"))
        return urls

    def _html_media_attribute_urls(self, webpage: str) -> list[str]:
        urls = []
        for match in re.finditer(
            r"""(?is)<(?:video|source|a|div|span)[^>]+(?:src|href|data-file|data-hls|data-mp4|data-source|data-stream|data-video|data-video-src)=["'](?P<url>[^"']+\.(?:m3u8|mpd|mp4|m4v|webm|vl)(?:\?[^"']*)?)["']""",
            webpage,
        ):
            urls.append(match.group("url"))
        return urls

    def _json_payloads_from_webpage(self, webpage: str) -> list[object]:
        payloads = []
        for match in re.finditer(
            r"""(?is)<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>""",
            webpage,
        ):
            attrs = match.group("attrs") or ""
            body = unescapeHTML(match.group("body") or "").strip()
            if not body:
                continue
            if re.search(r"""(?i)\btype=["']application/(?:ld\+)?json["']""", attrs) or re.search(
                r"""(?i)\bid=["']__NEXT_DATA__["']""", attrs
            ):
                data = self._parse_json(body, "json payload", fatal=False)
                if data is not None:
                    payloads.append(data)
                continue
            for state_match in re.finditer(
                r"""(?is)(?:window\.)?(?:__INITIAL_STATE__|__NUXT__|flashvars|jwplayerConfig|JWPLAYER_CONFIG|mediaData|MEDIA_DATA|playerConfig|PLAYER_CONFIG|playerData|PLAYER_DATA|playerSettings|PLAYER_SETTINGS|sources|videoConfig|videoData|VIDEO_DATA|videoSources)\s*=\s*(?P<json>\{.*?\}|\[.*?\])\s*;""",
                body,
            ):
                data = self._parse_json(
                    state_match.group("json"),
                    "state payload",
                    transform_source=js_to_json,
                    fatal=False,
                )
                if data is not None:
                    payloads.append(data)
            for player_match in re.finditer(
                r"""(?is)(?:jwplayer\s*\([^)]*\)\s*\.\s*setup|videojs\s*\([^)]*\)\s*\.\s*src)\s*\(\s*(?P<json>\{.*?\}|\[.*?\])\s*\)""",
                body,
            ):
                data = self._parse_json(
                    player_match.group("json"),
                    "player payload",
                    transform_source=js_to_json,
                    fatal=False,
                )
                if data is not None:
                    payloads.append(data)
        return payloads

    def _media_candidates_from_json(self, page_url: str, value: object) -> list[str]:
        candidates = []
        stack = [value]
        seen_ids = set()
        while stack:
            item = stack.pop()
            item_id = id(item)
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            if isinstance(item, dict):
                for key, child in item.items():
                    key_text = str(key).lower()
                    if isinstance(child, str):
                        candidates.extend(self._media_candidates_from_string(page_url, child, key_text))
                    else:
                        stack.append(child)
            elif isinstance(item, list | tuple):
                stack.extend(item)
            elif isinstance(item, str):
                candidates.extend(self._media_candidates_from_string(page_url, item, ""))
        return candidates

    def _media_candidates_from_string(self, page_url: str, value: str, key: str) -> list[str]:
        text = unescapeHTML(str(value or "")).replace("\\/", "/").strip()
        if not text:
            return []
        looks_like_media_key = key in {
            "contenturl",
            "content_url",
            "dashurl",
            "dash_url",
            "downloadurl",
            "download_url",
            "embedurl",
            "file",
            "files",
            "fileurl",
            "file_url",
            "hls",
            "hlsurl",
            "hls_url",
            "manifest",
            "master",
            "masterurl",
            "master_url",
            "media",
            "mp4",
            "mp4url",
            "mp4_url",
            "playurl",
            "play_url",
            "src",
            "source",
            "sources",
            "sourceurl",
            "source_url",
            "stream",
            "streams",
            "streamurl",
            "stream_url",
            "url",
            "video",
            "videosrc",
            "video_src",
            "videourl",
            "video_url",
            "videosources",
            "video_sources",
        } or bool(re.match(r"(?:file|quality|src|source|video)_?(?:\d{3,4}p?|hd|sd)$", key))
        if looks_like_media_key and re.search(r"\.(?:m3u8|mpd|mp4|m4v|webm|mov|vl)(?:[?#]|$)", text, flags=re.I):
            return [text]
        return [
            match.group(0)
            for match in re.finditer(
                r"""https?://[^\s"'<>\\]+\.(?:m3u8|mpd|mp4|m4v|webm|mov|vl)(?:\?[^\s"'<>\\]+)?""",
                text,
                flags=re.I,
            )
        ]

    def _find_iframe_url(self, page_url: str, webpage: str) -> str | None:
        for iframe_url in self._configured_pattern_urls(page_url, webpage, "iframe_patterns"):
            cleaned = self._clean_media_url(page_url, iframe_url)
            if cleaned:
                return cleaned
        for pattern in (
            r"""(?is)<iframe[^>]+(?:src|data-src|data-embed|data-embed-url|data-iframe|data-player|data-player-src|data-player-url)=["'](?P<url>[^"']+)["']""",
            r"""(?is)<embed[^>]+(?:src|data-src)=["'](?P<url>[^"']+)["']""",
            r"""(?is)(?:embedUrl|embed_url|iframeUrl|iframe_url|playerSrc|player_src|playerUrl|player_url)\s*[:=]\s*["'](?P<url>[^"']+)["']""",
        ):
            for match in re.finditer(pattern, webpage):
                iframe_url = self._clean_media_url(page_url, match.group("url"))
                if iframe_url:
                    return iframe_url
        return None

    def _configured_pattern_urls(self, page_url: str, webpage: str, key: str) -> list[str]:
        urls = []
        patterns = self._site_profile(page_url).get(key)
        if not isinstance(patterns, list):
            return urls
        for pattern_spec in patterns:
            pattern = ""
            group: str | int = "url"
            if isinstance(pattern_spec, str):
                pattern = pattern_spec
            elif isinstance(pattern_spec, dict):
                pattern = str(pattern_spec.get("pattern") or "")
                raw_group = pattern_spec.get("group", "url")
                group = int(raw_group) if isinstance(raw_group, int) else str(raw_group or "url")
            if not pattern:
                continue
            try:
                matches = re.finditer(pattern, webpage)
            except re.error:
                continue
            for match in matches:
                value = self._match_group_value(match, group)
                if value:
                    urls.append(value)
        return urls

    @staticmethod
    def _match_group_value(match: re.Match, group: str | int) -> str:
        try:
            value = match.group(group)
        except (IndexError, KeyError):
            try:
                value = match.group(1)
            except IndexError:
                value = ""
        return str(value or "")

    def _clean_media_url(self, page_url: str, media_url: str | None) -> str | None:
        if not media_url:
            return None
        cleaned = unescapeHTML(str(media_url)).replace("\\/", "/").strip()
        if not cleaned or cleaned.startswith(("data:", "javascript:", "#")):
            return None
        try:
            cleaned = self._parse_json(f'"{cleaned}"', self._generic_id(page_url), transform_source=js_to_json)
        except ExtractorError:
            pass
        absolute_url = urljoin(page_url, cleaned)
        return url_or_none(absolute_url)

    def _adult_site_title(self, url: str, webpage: str) -> str:
        return (
            self._og_search_title(webpage, default=None)
            or self._html_extract_title(webpage, default=None)
            or self._generic_id(url)
        )

    @classmethod
    def _adult_site_headers(cls, url: str, *, referer: str | None = None) -> dict:
        profile = cls._site_profile(url)
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Referer": referer or url,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125 Safari/537.36"
            ),
        }
        accept_language = str(profile.get("accept_language") or "").strip()
        if accept_language:
            headers["Accept-Language"] = accept_language
        return headers

    @classmethod
    def _iframe_depth_for_url(cls, url: str) -> int:
        profile = cls._site_profile(url)
        value = profile.get("iframe_depth")
        return int(value) if isinstance(value, int) and value >= 0 else cls._IFRAME_DEPTH

    @classmethod
    def _site_profile(cls, url: str) -> dict[str, object]:
        if cls._SITE_KEY and cls._SITE_KEY in SITE_REGISTRY:
            return SITE_REGISTRY[cls._SITE_KEY]
        host = str(urlparse(url).hostname or "").lower().removeprefix("www.")
        for profile in SITE_REGISTRY.values():
            domains = profile.get("domains")
            if not isinstance(domains, list):
                continue
            for domain in domains:
                if cls._host_matches(host, str(domain)):
                    return profile
        return {}

    @staticmethod
    def _host_matches(host: str, pattern: str) -> bool:
        pattern = pattern.lower().strip()
        if not host or not pattern:
            return False
        if pattern.startswith("*."):
            suffix = pattern[2:]
            return host == suffix or host.endswith(f".{suffix}")
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return host == prefix or host.startswith(f"{prefix}.")
        return host == pattern or host.endswith(f".{pattern}")


class MissAVIE(_AdultSiteBaseIE):
    IE_NAME = "missav"
    _SITE_KEY = "missav"
    _VALID_URL = r"https?://(?:[^/]+\.)?missav\.(?:ai|com|ws)/(?:[a-z]{2}/)?(?P<id>[^/?#&]+)"

    def _real_extract(self, url: str) -> dict:
        return self._extract_adult_site(url, self._match_id(url))


class SupJavIE(_AdultSiteBaseIE):
    IE_NAME = "supjav"
    _SITE_KEY = "supjav"
    _VALID_URL = r"https?://(?:[^/]+\.)?supjav\.com/(?:[^/?#]+/)*(?P<id>[^/?#&]+)"

    def _real_extract(self, url: str) -> dict:
        return self._extract_adult_site(url, self._match_id(url))


class JAVMostIE(_AdultSiteBaseIE):
    IE_NAME = "javmost"
    _SITE_KEY = "javmost"
    _VALID_URL = r"https?://(?:[^/]+\.)?javmost\.(?:com|cx)/(?:[^/?#]+/)*(?P<id>[^/?#&]+)"

    def _real_extract(self, url: str) -> dict:
        return self._extract_adult_site(url, self._match_id(url))


class JAVGGIE(_AdultSiteBaseIE):
    IE_NAME = "javgg"
    _SITE_KEY = "javgg"
    _VALID_URL = r"https?://(?:[^/]+\.)?javgg\.(?:net|to)/(?:[^/?#]+/)*(?P<id>[^/?#&]+)"

    def _real_extract(self, url: str) -> dict:
        return self._extract_adult_site(url, self._match_id(url))


class R18IE(_AdultSiteBaseIE):
    IE_NAME = "r18"
    _SITE_KEY = "r18"
    _VALID_URL = r"https?://(?:[^/]+\.)?r18\.com/(?:.*?id=(?P<id>[^/?#&]+)|(?P<slug>[^?#]+))"

    def _real_extract(self, url: str) -> dict:
        return self._extract_adult_site(url, self._match_id(url) or self._generic_id(url))


class JAVLibraryIE(_AdultSiteBaseIE):
    IE_NAME = "javlibrary"
    _SITE_KEY = "javlibrary"
    _VALID_URL = r"https?://(?:[^/]+\.)?javlibrary\.com/(?:[a-z]{2}/)?(?:\?(?:[^#]*&)?v=(?P<id>[^&#]+)|(?P<slug>[^?#]+))"

    def _real_extract(self, url: str) -> dict:
        return self._extract_adult_site(url, self._match_id(url) or self._generic_id(url))


class JAVHDIE(_AdultSiteBaseIE):
    IE_NAME = "javhd"
    _SITE_KEY = "javhd"
    _VALID_URL = r"https?://(?:[^/]+\.)?javhd\.com/(?:[^/?#]+/)*(?P<id>[^/?#&]+)"

    def _real_extract(self, url: str) -> dict:
        return self._extract_adult_site(url, self._match_id(url))


class NJAVIE(_AdultSiteBaseIE):
    IE_NAME = "njav"
    _SITE_KEY = "njav"
    _VALID_URL = r"https?://(?:[^/]+\.)?njav\.com/(?:[a-z]{2}/)?(?:xvideos|video|videos)/(?P<id>[^/?#&]+)"
    _IFRAME_DEPTH = 2

    def _real_extract(self, url: str) -> dict:
        video_id = self._match_id(url)
        webpage = self._download_webpage(url, video_id, headers=self._adult_site_headers(url))
        title = self._adult_site_title(url, webpage)
        thumbnail = self._html_search_meta(
            ("og:image", "twitter:image", "thumbnail"),
            webpage,
            "thumbnail",
            default=None,
        )
        embed_url = self._njav_embed_url(url, webpage)
        if not embed_url:
            raise ExtractorError("Unable to find embedded player URL", expected=True)

        embed_webpage = self._download_webpage(
            embed_url,
            video_id,
            note="Downloading embedded player webpage",
            headers=self._adult_site_headers(url),
        )
        player_url = self._njav_player_url(embed_url, embed_webpage)
        if not player_url:
            raise ExtractorError("Unable to find player frame URL", expected=True)

        player_webpage, urlh = self._download_webpage_handle(
            player_url,
            video_id,
            note="Downloading player frame webpage",
            headers=self._adult_site_headers(embed_url),
        )
        final_player_url = getattr(urlh, "geturl", lambda: player_url)()
        m3u8_url = self._njav_m3u8_url(final_player_url, player_webpage)
        if not m3u8_url:
            raise ExtractorError("Unable to find HLS media URL", expected=True)

        headers = self._adult_site_headers(final_player_url)
        formats = self._formats_with_headers(
            self._extract_m3u8_formats(
                m3u8_url,
                video_id,
                "mp4",
                m3u8_id="hls",
                fatal=False,
                headers=headers,
            ),
            headers,
        )
        if not formats:
            formats = [
                {
                    "url": m3u8_url,
                    "format_id": "hls",
                    "ext": "mp4",
                    "protocol": "m3u8_native",
                    "vcodec": "h264",
                    "acodec": "aac",
                    "http_headers": headers,
                }
            ]
        return {
            "id": video_id,
            "title": title,
            "thumbnail": urljoin(url, thumbnail) if thumbnail else None,
            "age_limit": 18,
            "formats": formats,
        }

    def _njav_embed_url(self, page_url: str, webpage: str) -> str | None:
        embed_url = self._html_search_meta(("embedUrl",), webpage, "embed url", default=None)
        if not embed_url:
            embed_url = self._search_regex(
                r'"embedUrl"\s*:\s*"([^"]+)"',
                webpage,
                "embed url",
                default=None,
            )
        if not embed_url:
            return None
        return self._clean_media_url(page_url, embed_url)

    def _njav_player_url(self, embed_url: str, embed_webpage: str) -> str | None:
        player_url = self._search_regex(
            r"""(?x)
            videoFrame\.src\s*=\s*["'](?P<url>[^"']+)["']
            |
            <iframe[^>]+(?:src|data-src)=["'](?P<iframe>[^"']+)["']
            """,
            embed_webpage,
            "player frame url",
            default=None,
            group=("url", "iframe"),
        )
        player_url = self._first_nonempty_match(player_url)
        if not player_url:
            return None
        return self._clean_media_url(embed_url, player_url)

    def _njav_m3u8_url(self, player_url: str, player_webpage: str) -> str | None:
        m3u8_url = self._search_regex(
            r"""(?x)
            \bm3u8\s*:\s*["'](?P<m3u8>[^"']+)["']
            |
            \bfile\s*:\s*["'](?P<file>[^"']+\.m3u8(?:\?[^"']*)?)["']
            """,
            player_webpage,
            "HLS media url",
            default=None,
            group=("m3u8", "file"),
        )
        m3u8_url = self._first_nonempty_match(m3u8_url)
        if not m3u8_url:
            return None
        return self._clean_media_url(player_url, unescapeHTML(m3u8_url))

    @staticmethod
    def _first_nonempty_match(value: object) -> str:
        if isinstance(value, tuple):
            return next((str(item) for item in value if item), "")
        return str(value or "")


class LiveJasminIE(_AdultSiteBaseIE):
    IE_NAME = "livejasmin"
    _SITE_KEY = "livejasmin"
    _VALID_URL = r"https?://(?:[^/]+\.)?livejasmin\.com/(?:[a-z]{2}/)?(?P<id>[^?#]+)"

    def _real_extract(self, url: str) -> dict:
        return self._extract_adult_site(url, self._match_id(url).strip("/") or self._generic_id(url))


class VLXXIE(_AdultSiteBaseIE):
    IE_NAME = "vlxx"
    _SITE_KEY = "vlxx"
    _VALID_URL = r"https?://(?:[^/]+\.)?vlxx\.[^/]+/(?:video/)?(?P<id>[^/?#&]+)(?:/(?P<numeric_id>\d+))?/?"
    _IFRAME_DEPTH = 2

    def _real_extract(self, url: str) -> dict:
        matched = self._match_valid_url(url)
        video_id = str(matched.group("numeric_id") or matched.group("id") or self._generic_id(url))
        webpage = self._download_webpage(url, video_id, headers=self._adult_site_headers(url))
        ajax_url = urljoin(url, "/ajax.php")
        escaped_video_id = re.escape(video_id)
        server_ids = dict.fromkeys(
            re.findall(rf"""(?i)\bserver\s*\(\s*(\d+)\s*,\s*{escaped_video_id}\s*\)""", webpage)
            + re.findall(r"""(?i)\bdata-sv=["'](\d+)["']""", webpage)
            + ["1", "2"]
        )
        player_webpages = []
        for server_id in server_ids:
            payload = urlencode({"vlxx_server": "1", "id": video_id, "server": server_id}).encode()
            ajax_data = self._download_json(
                ajax_url,
                video_id,
                note=f"Downloading server {server_id} player",
                data=payload,
                headers={**self._adult_site_headers(url), "X-Requested-With": "XMLHttpRequest"},
                fatal=False,
            )
            if isinstance(ajax_data, dict) and ajax_data.get("player"):
                player_webpages.append(str(ajax_data.get("player") or ""))
        return self._extract_from_webpage(url, video_id, "\n".join([webpage, *player_webpages]), self._IFRAME_DEPTH)


class BuomTVIE(_AdultSiteBaseIE):
    IE_NAME = "buomtv"
    _SITE_KEY = "buomtv"
    _VALID_URL = (
        r"https?://(?:[^/]+\.)?buomtv\.[^/]+/(?:[a-z]{2}/)?"
        r"(?:(?P<long_type>movie)/[^/]+/(?P<long_id>[^/?#&]+)|(?P<short_type>video|anime)/(?P<short_id>[^/?#&]+))"
    )

    def _real_extract(self, url: str) -> dict:
        matched = self._match_valid_url(url)
        video_type = "long" if matched.group("long_type") else str(matched.group("short_type") or "short")
        video_id = str(matched.group("long_id") or matched.group("short_id") or self._generic_id(url))
        api_base = self._api_base(url)
        headers = self._api_headers(url)

        token_payload = self._download_json(
            f"{api_base}/pwa/register/pwatoken?version=old-web&lang=vi",
            video_id,
            note="Downloading token",
            data=urlencode({"lang": "vi"}).encode(),
            headers=headers,
        )
        token = str(self._dict_value(token_payload.get("response")).get("token") or "")
        if not token:
            raise ExtractorError("Unable to get token", expected=True)

        info_payload = self._download_json(
            f"{api_base}/pwa/video/info/{quote(video_id)}"
            f"?token={quote(token)}&video_type={video_type}&platform=web&lang=vi",
            video_id,
            note="Downloading video info",
            headers=headers,
        )
        status = self._dict_value(info_payload.get("status"))
        if status.get("code") != 200:
            raise ExtractorError(str(status.get("message") or "Video API returned an error"), expected=True)

        info = self._dict_value(info_payload.get("response"))
        title = str(info.get("video_title") or video_id)
        stream_url = self._absolute_url(url, self._select_stream_url(self._dict_value(info.get("video_urls"))))
        if not stream_url:
            raise ExtractorError("Unable to find playback URL", expected=True)

        ext = determine_ext(stream_url)
        if ext == "m3u8":
            formats = self._formats_with_headers(
                self._extract_m3u8_formats(stream_url, video_id, "mp4", fatal=False, headers=headers),
                headers,
            )
        else:
            formats = [{"url": stream_url, "ext": ext, "http_headers": headers}]

        return {
            "id": video_id,
            "title": title,
            "age_limit": 18,
            "formats": formats,
        }

    @staticmethod
    def _dict_value(value: object) -> dict:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _select_stream_url(video_urls: dict) -> str:
        numeric_streams = sorted(
            (int(height), str(stream_url))
            for height, stream_url in video_urls.items()
            if str(height).isdigit() and stream_url
        )
        if numeric_streams:
            return numeric_streams[-1][1]
        return str(video_urls.get("intro") or "")

    @staticmethod
    def _absolute_url(page_url: str, stream_path: str) -> str:
        stream_path = str(stream_path or "").strip()
        if stream_path.lower().startswith(("http://", "https://")):
            return stream_path
        return f"{BuomTVIE._api_base(page_url)}/{stream_path.lstrip('/')}"

    @staticmethod
    def _api_base(page_url: str) -> str:
        parsed = urlparse(page_url)
        return f"{parsed.scheme or 'https'}://api.{str(parsed.hostname or '').lower().removeprefix('www.')}"

    @staticmethod
    def _api_headers(page_url: str) -> dict:
        parsed = urlparse(page_url)
        headers = _AdultSiteBaseIE._adult_site_headers(page_url)
        headers["Origin"] = f"{parsed.scheme or 'https'}://{parsed.netloc}"
        return headers


class GenericAdultIE(_AdultSiteBaseIE):
    IE_NAME = "ai_player_adult_generic"
    _VALID_URL = r"https?://(?P<host>[^/?#]+)/(?P<id>[^?#]+)"
    _IFRAME_DEPTH = 2

    @classmethod
    def suitable(cls, url: str) -> bool:
        profile = cls._site_profile(url)
        return bool(profile) and not _profile_delegates_to_ytdlp(profile) and super().suitable(url)

    def _real_extract(self, url: str) -> dict:
        return self._extract_adult_site(url, self._generic_id(url))


__all__ = [
    "BuomTVIE",
    "GenericAdultIE",
    "JAVGGIE",
    "JAVHDIE",
    "JAVLibraryIE",
    "JAVMostIE",
    "LiveJasminIE",
    "MissAVIE",
    "NJAVIE",
    "R18IE",
    "SupJavIE",
    "VLXXIE",
]
