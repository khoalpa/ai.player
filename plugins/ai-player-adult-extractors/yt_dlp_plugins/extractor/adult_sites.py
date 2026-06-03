from __future__ import annotations

import re
from urllib.parse import quote, urlencode, urlparse

from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import ExtractorError, determine_ext, int_or_none, js_to_json, unescapeHTML, url_or_none, urljoin


class _AdultSiteBaseIE(InfoExtractor):
    _DOMAINS: tuple[str, ...] = ()
    _IFRAME_DEPTH = 1

    def _extract_adult_site(self, url: str, video_id: str | None = None) -> dict:
        video_id = video_id or self._generic_id(url)
        webpage = self._download_webpage(url, video_id, headers=self._adult_site_headers(url))
        return self._extract_from_webpage(url, video_id, webpage, self._IFRAME_DEPTH)

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
                    headers=self._adult_site_headers(url),
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
            if ext == "m3u8":
                formats.extend(
                    self._extract_m3u8_formats(
                        media_url,
                        video_id,
                        "mp4",
                        m3u8_id="hls",
                        fatal=False,
                        headers=self._adult_site_headers(page_url),
                    )
                )
            elif ext == "mpd":
                formats.extend(self._extract_mpd_formats(media_url, video_id, mpd_id="dash", fatal=False))
            elif ext in {"mp4", "m4v", "webm", "mov"}:
                formats.append({"url": media_url, "ext": ext, "http_headers": self._adult_site_headers(page_url)})
        return formats

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
        for match in re.finditer(
            r"""(?ix)
            ["'](?P<quoted>https?:\\/\\/[^"']+\.(?:m3u8|mpd|mp4|m4v|webm)(?:\?[^"']*)?)["']
            |
            (?P<bare>https?://[^\s"'<>\\]+\.(?:m3u8|mpd|mp4|m4v|webm)(?:\?[^\s"'<>\\]+)?)
            |
            (?:file|src|source|videoUrl|video_url|hls|url)\s*[:=]\s*["'](?P<named>[^"']+\.(?:m3u8|mpd|mp4|m4v|webm)(?:\?[^"']*)?)["']
            """,
            webpage,
        ):
            candidates.append(match.group("quoted") or match.group("bare") or match.group("named"))

        for json_ld in re.finditer(
            r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(?P<json>.*?)</script>',
            webpage,
        ):
            data = self._parse_json(json_ld.group("json"), self._generic_id(page_url), fatal=False)
            if isinstance(data, dict):
                candidates.extend(str(data.get(key) or "") for key in ("contentUrl", "embedUrl", "url"))

        return [url for url in (self._clean_media_url(page_url, candidate) for candidate in candidates) if url]

    def _find_iframe_url(self, page_url: str, webpage: str) -> str | None:
        for pattern in (
            r"""(?is)<iframe[^>]+(?:src|data-src)=["'](?P<url>[^"']+)["']""",
            r"""(?is)<embed[^>]+src=["'](?P<url>[^"']+)["']""",
            r"""(?is)(?:embedUrl|embed_url|player_url)\s*[:=]\s*["'](?P<url>[^"']+)["']""",
        ):
            for match in re.finditer(pattern, webpage):
                iframe_url = self._clean_media_url(page_url, match.group("url"))
                if iframe_url:
                    return iframe_url
        return None

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

    @staticmethod
    def _adult_site_headers(url: str) -> dict:
        return {
            "Referer": url,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125 Safari/537.36"
            ),
        }


class MissAVIE(_AdultSiteBaseIE):
    IE_NAME = "missav"
    _VALID_URL = r"https?://(?:[^/]+\.)?missav\.(?:ai|com|ws)/(?:[a-z]{2}/)?(?P<id>[^/?#&]+)"

    def _real_extract(self, url: str) -> dict:
        return self._extract_adult_site(url, self._match_id(url))


class SupJavIE(_AdultSiteBaseIE):
    IE_NAME = "supjav"
    _VALID_URL = r"https?://(?:[^/]+\.)?supjav\.com/(?:[^/?#]+/)*(?P<id>[^/?#&]+)"

    def _real_extract(self, url: str) -> dict:
        return self._extract_adult_site(url, self._match_id(url))


class JAVMostIE(_AdultSiteBaseIE):
    IE_NAME = "javmost"
    _VALID_URL = r"https?://(?:[^/]+\.)?javmost\.(?:com|cx)/(?:[^/?#]+/)*(?P<id>[^/?#&]+)"

    def _real_extract(self, url: str) -> dict:
        return self._extract_adult_site(url, self._match_id(url))


class JAVGGIE(_AdultSiteBaseIE):
    IE_NAME = "javgg"
    _VALID_URL = r"https?://(?:[^/]+\.)?javgg\.(?:net|to)/(?:[^/?#]+/)*(?P<id>[^/?#&]+)"

    def _real_extract(self, url: str) -> dict:
        return self._extract_adult_site(url, self._match_id(url))


class R18IE(_AdultSiteBaseIE):
    IE_NAME = "r18"
    _VALID_URL = r"https?://(?:[^/]+\.)?r18\.com/(?:.*?id=(?P<id>[^/?#&]+)|(?P<slug>[^?#]+))"

    def _real_extract(self, url: str) -> dict:
        return self._extract_adult_site(url, self._match_id(url) or self._generic_id(url))


class JAVLibraryIE(_AdultSiteBaseIE):
    IE_NAME = "javlibrary"
    _VALID_URL = r"https?://(?:[^/]+\.)?javlibrary\.com/(?:[a-z]{2}/)?(?:\?(?:[^#]*&)?v=(?P<id>[^&#]+)|(?P<slug>[^?#]+))"

    def _real_extract(self, url: str) -> dict:
        return self._extract_adult_site(url, self._match_id(url) or self._generic_id(url))


class JAVHDIE(_AdultSiteBaseIE):
    IE_NAME = "javhd"
    _VALID_URL = r"https?://(?:[^/]+\.)?javhd\.com/(?:[^/?#]+/)*(?P<id>[^/?#&]+)"

    def _real_extract(self, url: str) -> dict:
        return self._extract_adult_site(url, self._match_id(url))


class LiveJasminIE(_AdultSiteBaseIE):
    IE_NAME = "livejasmin"
    _VALID_URL = r"https?://(?:[^/]+\.)?livejasmin\.com/(?:[a-z]{2}/)?(?P<id>[^?#]+)"

    def _real_extract(self, url: str) -> dict:
        return self._extract_adult_site(url, self._match_id(url).strip("/") or self._generic_id(url))


class BuomTVIE(_AdultSiteBaseIE):
    IE_NAME = "buomtv"
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
            formats = self._extract_m3u8_formats(stream_url, video_id, "mp4", fatal=False, headers=headers)
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


__all__ = [
    "BuomTVIE",
    "JAVGGIE",
    "JAVHDIE",
    "JAVLibraryIE",
    "JAVMostIE",
    "LiveJasminIE",
    "MissAVIE",
    "R18IE",
    "SupJavIE",
]
