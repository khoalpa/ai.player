from __future__ import annotations

import json
from pathlib import Path

PLAYBACK_COMPAT_CACHE_VERSION = "qt-playback-main-h264-720p-v2"


def playback_compat_cached_output_valid(output_path: Path, source_path: str, cache_key: str) -> bool:
    if not output_path.exists() or output_path.stat().st_size <= 0:
        return False
    metadata = _read_playback_compat_metadata(output_path)
    return (
        metadata.get("version") == PLAYBACK_COMPAT_CACHE_VERSION
        and metadata.get("source_path") == str(source_path)
        and metadata.get("cache_key") == str(cache_key)
        and metadata.get("status") == "complete"
    )


def write_playback_compat_metadata(output_path: Path, source_path: str, cache_key: str) -> None:
    _playback_compat_metadata_path(output_path).write_text(
        json.dumps(
            {
                "version": PLAYBACK_COMPAT_CACHE_VERSION,
                "source_path": str(source_path),
                "cache_key": str(cache_key),
                "status": "complete",
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def remove_playback_compat_output(output_path: Path) -> None:
    for path in (output_path, _playback_compat_metadata_path(output_path)):
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass


def _read_playback_compat_metadata(output_path: Path) -> dict[str, object]:
    try:
        data = json.loads(_playback_compat_metadata_path(output_path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _playback_compat_metadata_path(output_path: Path) -> Path:
    return output_path.with_suffix(f"{output_path.suffix}.json")
