from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from yt_dlp import YoutubeDL

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_PLUGIN = PROJECT_ROOT / "plugins" / "ai-player-adult-extractors"
if LOCAL_PLUGIN.exists() and str(LOCAL_PLUGIN) not in sys.path:
    sys.path.insert(0, str(LOCAL_PLUGIN))

from yt_dlp_plugins.extractor import adult_sites as ADULT_SITES  # noqa: E402,I001
from yt_dlp_plugins.extractor.adult_sites import GenericAdultIE  # noqa: E402,I001


SENSITIVE_QUERY_KEYS = {
    "auth",
    "expires",
    "hash",
    "key",
    "signature",
    "sig",
    "token",
}


def main() -> int:
    args = _parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    html = _download_html(args.url, timeout=args.timeout)
    redacted_html = _redact_sensitive_values(html)
    extractor = GenericAdultIE(YoutubeDL({"quiet": True, "no_warnings": True}))
    media_urls = extractor._find_media_urls(args.url, redacted_html)
    iframe_url = extractor._find_iframe_url(args.url, redacted_html)
    json_payload_count = len(extractor._json_payloads_from_webpage(redacted_html))
    plugin_candidates = _matching_extractors(args.url)
    native_candidates = _matching_native_ytdlp_extractors(args.url)

    host = _normalized_host(args.url)
    site_key = args.site_key or re.sub(r"[^a-z0-9]+", "_", host).strip("_") or "adult_site"
    html_path = output_dir / f"{site_key}.html"
    draft_path = output_dir / f"{site_key}.registry.json"
    report_path = output_dir / f"{site_key}.probe.json"

    html_path.write_text(redacted_html, encoding="utf-8")
    draft = _registry_draft(
        site_key,
        host,
        accept_language=args.accept_language,
        iframe_url=iframe_url,
        native_ytdlp_extractors=native_candidates,
    )
    draft_path.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
    report = {
        "url": _redact_sensitive_values(args.url),
        "host": host,
        "html_fixture": str(html_path),
        "registry_draft": str(draft_path),
        "suggested_registry_mode": _suggested_registry_mode(native_candidates),
        "json_payload_count": json_payload_count,
        "extractor_candidates": plugin_candidates,
        "native_ytdlp_extractors": native_candidates,
        "iframe_candidate": iframe_url,
        "media_candidates": media_urls,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if media_urls or iframe_url else 2


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe a new adult video host and create a registry draft.")
    parser.add_argument("url", help="Adult site URL to inspect.")
    parser.add_argument("--site-key", default="", help="Registry key to use for the draft.")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "data" / "tmp" / "adult-site-probe"))
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--accept-language", default="en-US,en;q=0.9")
    return parser.parse_args()


def _download_html(url: str, *, timeout: float) -> str:
    response = requests.get(
        url,
        headers=GenericAdultIE._adult_site_headers(url),
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text


def _normalized_host(url: str) -> str:
    return str(urlparse(url).hostname or "").lower().removeprefix("www.")


def _matching_extractors(url: str) -> list[str]:
    names = []
    for name in getattr(ADULT_SITES, "__all__", ()):
        extractor = getattr(ADULT_SITES, name, None)
        if _extractor_suitable(extractor, url):
            names.append(str(name))
    return sorted(dict.fromkeys(names))


def _matching_native_ytdlp_extractors(url: str) -> list[str]:
    try:
        extractors = YoutubeDL({"quiet": True, "no_warnings": True})._ies.values()
    except Exception:
        return []
    names = []
    for extractor in extractors:
        module_name = str(getattr(extractor, "__module__", ""))
        ie_name = str(getattr(extractor, "IE_NAME", "") or "")
        if not ie_name or ie_name == "generic" or module_name.startswith("yt_dlp_plugins."):
            continue
        if _extractor_suitable(extractor, url):
            names.append(ie_name)
    return sorted(dict.fromkeys(names))


def _extractor_suitable(extractor: object, url: str) -> bool:
    suitable = getattr(extractor, "suitable", None)
    if not callable(suitable):
        return False
    try:
        return bool(suitable(url))
    except Exception:
        return False


def _registry_draft(
    site_key: str,
    host: str,
    *,
    accept_language: str,
    iframe_url: str | None,
    native_ytdlp_extractors: list[str],
) -> dict[str, dict[str, object]]:
    if native_ytdlp_extractors:
        return {
            site_key: {
                "domains": [host],
                "delegate_to_ytdlp": True,
            }
        }
    return {
        site_key: {
            "domains": [host],
            "iframe_depth": 2 if iframe_url else 1,
            "accept_language": accept_language,
            "media_patterns": [],
            "iframe_patterns": [],
        }
    }


def _suggested_registry_mode(native_ytdlp_extractors: list[str]) -> str:
    return "delegate_to_ytdlp" if native_ytdlp_extractors else "generic"


def _redact_sensitive_values(value: str) -> str:
    text = str(value)
    for key in SENSITIVE_QUERY_KEYS:
        text = re.sub(
            rf"(?i)([?&;]{re.escape(key)}=)[^&;\"'<>\s]+",
            r"\1<redacted>",
            text,
        )
        text = re.sub(
            rf"(?i)([\"']{re.escape(key)}[\"']\s*:\s*[\"'])[^\"']+",
            r"\1<redacted>",
            text,
        )
    return text


if __name__ == "__main__":
    raise SystemExit(main())
