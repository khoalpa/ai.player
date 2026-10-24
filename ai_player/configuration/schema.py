"""Version the persisted configuration independently of provider migrations."""

from __future__ import annotations

CURRENT_SCHEMA_VERSION = 1


class UnsupportedSettingsVersion(ValueError):
    pass


def migrate_settings(payload: dict[str, object]) -> dict[str, object]:
    version = payload.get("schema_version", 0)
    if not isinstance(version, int) or version < 0 or version > CURRENT_SCHEMA_VERSION:
        raise UnsupportedSettingsVersion(f"Unsupported settings schema: {version!r}")
    # Version 0 used the same flat field names without a schema marker.
    return {**payload, "schema_version": CURRENT_SCHEMA_VERSION}
