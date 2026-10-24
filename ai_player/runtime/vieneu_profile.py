"""Version and verify the local modifications applied to the pinned SDK."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ai_player.adapters.storage.atomic import write_text_atomic
from ai_player.runtime.vieneu_v3 import SDK_VERSION

PATCH_REVISION = 1
PROFILE_FILENAME = "ai_player_v3_runtime.json"
PATCHED_FILES = ("factory.py", "base.py", "v3turbo.py")


def _package_in_runtime(prefix: Path, package: Path) -> tuple[Path, Path]:
    prefix, package = Path(prefix).resolve(), Path(package).resolve()
    if not package.is_relative_to(prefix):
        raise ValueError("VieNeu SDK must be inside its dedicated runtime")
    return prefix, package


def record_runtime_profile(prefix: Path, package: Path) -> dict:
    prefix, package = _package_in_runtime(prefix, package)
    payload = {
        "sdk_version": SDK_VERSION,
        "profile": "v3turbo-only",
        "patch_revision": PATCH_REVISION,
        "local_codec": True,
        "sha256": {name: hashlib.sha256((package / name).read_bytes()).hexdigest() for name in PATCHED_FILES},
    }
    write_text_atomic(prefix / PROFILE_FILENAME, json.dumps(payload, indent=2, sort_keys=True))
    return payload


def validate_runtime_profile(prefix: Path, package: Path) -> None:
    prefix, package = _package_in_runtime(prefix, package)
    marker = prefix / PROFILE_FILENAME
    try:
        profile = json.loads(marker.read_text(encoding="utf-8"))
        valid = (
            profile["sdk_version"] == SDK_VERSION
            and profile["profile"] == "v3turbo-only"
            and profile["patch_revision"] == PATCH_REVISION
            and profile["local_codec"] is True
            and all(
                profile["sha256"][name] == hashlib.sha256((package / name).read_bytes()).hexdigest()
                for name in PATCHED_FILES
            )
        )
    except (OSError, ValueError, KeyError, TypeError):
        valid = False
    if not valid:
        raise RuntimeError("VieNeu runtime profile is missing or modified. Run scripts/setup_vieneu_runtime.ps1.")
