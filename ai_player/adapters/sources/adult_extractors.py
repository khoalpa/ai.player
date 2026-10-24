from __future__ import annotations

import json
import sys
from dataclasses import dataclass

from ai_player.configuration import PROJECT_ROOT

LOCAL_ADULT_EXTRACTOR_PLUGIN = PROJECT_ROOT / "plugins" / "ai-player-adult-extractors"
REGISTRY_PATH = LOCAL_ADULT_EXTRACTOR_PLUGIN / "yt_dlp_plugins" / "extractor" / "adult_sites_registry.json"


@dataclass(frozen=True)
class AdultHostSupport:
    site_key: str
    domains: tuple[str, ...]
    description: str
    open_url: str
    mode: str
    iframe_depth: int | None = None
    accept_language: str = ""


def supported_adult_hosts() -> tuple[AdultHostSupport, ...]:
    registry = _adult_site_registry()
    rows = []
    for site_key, profile in sorted(registry.items()):
        domains = profile.get("domains")
        if not isinstance(domains, list):
            continue
        clean_domains = tuple(str(domain).strip() for domain in domains if str(domain).strip())
        if not clean_domains:
            continue
        rows.append(
            AdultHostSupport(
                site_key=str(site_key),
                domains=clean_domains,
                description=_host_description(str(site_key), profile),
                open_url=_profile_open_url(profile, clean_domains),
                mode=_support_mode(profile),
                iframe_depth=profile.get("iframe_depth") if isinstance(profile.get("iframe_depth"), int) else None,
                accept_language=str(profile.get("accept_language") or ""),
            )
        )
    return tuple(rows)


def supported_adult_host_summary() -> dict[str, int]:
    rows = supported_adult_hosts()
    return {
        "sites": len(rows),
        "hosts": sum(len(row.domains) for row in rows),
        "delegate": sum(1 for row in rows if row.mode == "yt-dlp native"),
        "generic": sum(1 for row in rows if row.mode == "generic"),
        "site_specific": sum(1 for row in rows if row.mode == "site-specific"),
    }


def _support_mode(profile: dict[str, object]) -> str:
    if profile.get("delegate_to_ytdlp"):
        return "yt-dlp native"
    has_patterns = any(
        isinstance(profile.get(key), list) and profile.get(key) for key in ("media_patterns", "iframe_patterns")
    )
    if has_patterns or "iframe_depth" in profile:
        return "generic"
    return "site-specific"


def _host_description(site_key: str, profile: dict[str, object]) -> str:
    description = _HOST_DESCRIPTIONS.get(site_key.lower())
    if description:
        return description
    mode = _support_mode(profile)
    if mode == "yt-dlp native":
        return "Public adult video host handled by the native yt-dlp extractor."
    if mode == "generic":
        return "Public adult video host handled by the generic registry parser."
    return "Public adult video host handled by a site-specific extractor."


def _primary_host_url(domains: tuple[str, ...]) -> str:
    for domain in domains:
        clean = str(domain or "").strip().lower().removeprefix("www.")
        if clean and "*" not in clean:
            return f"https://{clean}"
    return ""


def _profile_open_url(profile: dict[str, object], domains: tuple[str, ...]) -> str:
    open_url = str(profile.get("open_url") or "").strip()
    if open_url.startswith(("http://", "https://")):
        return open_url
    return _primary_host_url(domains)


def _adult_site_registry() -> dict[str, dict[str, object]]:
    module_registry = _module_site_registry()
    if module_registry:
        return module_registry
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def _module_site_registry() -> dict[str, dict[str, object]]:
    plugin_root = str(LOCAL_ADULT_EXTRACTOR_PLUGIN)
    if LOCAL_ADULT_EXTRACTOR_PLUGIN.exists() and plugin_root not in sys.path:
        sys.path.insert(0, plugin_root)
    try:
        from yt_dlp_plugins.extractor import adult_sites
    except Exception:
        return {}
    registry = getattr(adult_sites, "SITE_REGISTRY", {})
    if not isinstance(registry, dict):
        return {}
    return {str(key): value for key, value in registry.items() if isinstance(value, dict)}


_HOST_DESCRIPTIONS = {
    "4tube": "Mainstream adult tube site with public video pages delegated to yt-dlp.",
    "alphaporno": "Adult tube site with public video pages delegated to yt-dlp.",
    "avgle": "JAV/Asia-oriented public video host handled by the generic parser.",
    "beeg": "Large adult tube site with public video pages delegated to yt-dlp.",
    "bongacams": "Live adult cam host delegated to yt-dlp for public room URLs.",
    "buomtv": "Vietnamese adult video host handled by the generic/API extractor path.",
    "cam4": "Live adult cam host delegated to yt-dlp for public room URLs.",
    "camsoda": "Live adult cam host delegated to yt-dlp for public room URLs.",
    "chaturbate": "Live adult cam host delegated to yt-dlp for public room URLs.",
    "drtuber": "Adult tube site with public video pages delegated to yt-dlp.",
    "empflix": "Adult tube site with public video pages delegated to yt-dlp.",
    "eporner": "Adult tube site with public HD video pages delegated to yt-dlp.",
    "fc2": "FC2 public video pages delegated to yt-dlp.",
    "hellporno": "Adult tube site with public video pages delegated to yt-dlp.",
    "javgg": "JAV/Asia-oriented public video host handled by the registry extractor.",
    "javhd": "JAV/Asia-oriented public video host handled by the registry extractor.",
    "jable": "JAV/Asia-oriented public video host handled by the generic parser.",
    "javlibrary": "JAV catalog/video pages handled by the registry extractor.",
    "javmost": "JAV/Asia-oriented public video host handled by the registry extractor.",
    "livejasmin": "Live adult cam host included for public yt-dlp-compatible URLs.",
    "lovehomeporn": "Adult tube site with public video pages delegated to yt-dlp.",
    "manyvids": "Creator/direct-upload adult video host delegated to yt-dlp.",
    "missav": "JAV/Asia-oriented public video host handled by the registry extractor.",
    "murrtube": "Social/bookmark adult video host delegated to yt-dlp.",
    "myvidster": "Social video bookmarking host delegated to yt-dlp for public pages.",
    "netflav": "JAV/Asia-oriented public video host handled by the generic parser.",
    "njav": "JAV/Asia-oriented public video host with a site-specific extractor flow.",
    "nubilesporn": "Nubiles member video URLs delegated to yt-dlp when accessible.",
    "nuvid": "Adult tube site with public video pages delegated to yt-dlp.",
    "peekvids": "Adult tube/embed host delegated to yt-dlp for public pages.",
    "playvids": "Adult tube/embed host delegated to yt-dlp for public pages.",
    "pornbox": "Adult video host delegated to yt-dlp for public watch pages.",
    "pornflip": "Adult tube site with public video pages delegated to yt-dlp.",
    "pornhub": "Major adult tube site delegated to yt-dlp for public video pages.",
    "pornotube": "Adult tube site with public video pages delegated to yt-dlp.",
    "pornoxo": "Adult tube site with public video pages delegated to yt-dlp.",
    "porntop": "Adult tube site with public video pages delegated to yt-dlp.",
    "porntube": "Adult tube site with public video pages delegated to yt-dlp.",
    "pornerbros": "Adult tube site with public video pages delegated to yt-dlp.",
    "r18": "Adult/JAV video pages handled by the registry extractor.",
    "redtube": "Major adult tube site delegated to yt-dlp for public video pages.",
    "rule34video": "Rule34-oriented public video host delegated to yt-dlp.",
    "spankbang": "Major adult tube site delegated to yt-dlp for public video pages.",
    "stripchat": "Live adult cam host delegated to yt-dlp for public room URLs.",
    "sunporno": "Adult tube site with public video pages delegated to yt-dlp.",
    "supjav": "JAV/Asia-oriented public video host handled by the registry extractor.",
    "thisvid": "Community adult video host delegated to yt-dlp for public pages.",
    "tnaflix": "Adult tube site with public video pages delegated to yt-dlp.",
    "toypics": "Social/adult video host delegated to yt-dlp for public pages.",
    "tube8": "Adult tube site with public video pages delegated to yt-dlp.",
    "txxx": "Txxx-family adult tube hosts delegated to yt-dlp.",
    "vlxx": "Vietnamese adult video host handled by the registry extractor.",
    "xhamster": "Major adult tube site delegated to yt-dlp for public video pages.",
    "xnxx": "Major adult tube site delegated to yt-dlp for public video pages.",
    "xvideos": "Major adult tube site delegated to yt-dlp for public video pages.",
    "xxxymovies": "Adult movie/tube site delegated to yt-dlp for public pages.",
    "youporn": "Major adult tube site delegated to yt-dlp for public video pages.",
    "youjizz": "Adult tube site with public video pages delegated to yt-dlp.",
    "zenporn": "Adult tube site with public video pages delegated to yt-dlp.",
}
