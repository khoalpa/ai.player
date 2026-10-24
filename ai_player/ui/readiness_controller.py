from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from typing import Any

from ai_player.configuration import AppConfig
from ai_player.runtime.runtime_health import RuntimeHealthItem, build_runtime_health, format_runtime_health
from ai_player.ui.player_window_utils import PERFORMANCE_PRESETS


@dataclass(frozen=True)
class ReadinessProfile:
    key: str
    preset: str
    title_key: str
    detail_key: str
    overrides: dict[str, object] | None = None


@dataclass(frozen=True)
class ReadinessStatus:
    config: AppConfig
    items: tuple[RuntimeHealthItem, ...]
    text: str
    attention_count: int
    provider_preview_kind: str


READINESS_PROFILES = (
    ReadinessProfile(
        key="auto",
        preset="balanced",
        title_key="first_run_profile_auto",
        detail_key="first_run_profile_auto_detail",
    ),
    ReadinessProfile(
        key="quick",
        preset="low_latency",
        title_key="first_run_profile_quick",
        detail_key="first_run_profile_quick_detail",
    ),
    ReadinessProfile(
        key="offline",
        preset="offline_lite",
        title_key="first_run_profile_offline",
        detail_key="first_run_profile_offline_detail",
    ),
    ReadinessProfile(
        key="quality",
        preset="quality",
        title_key="first_run_profile_quality",
        detail_key="first_run_profile_quality_detail",
    ),
    ReadinessProfile(
        key="meeting_document",
        preset="balanced",
        title_key="first_run_profile_meeting_document",
        detail_key="first_run_profile_meeting_document_detail",
        overrides={"audio_source": "document_editor"},
    ),
)


class ReadinessController:
    def __init__(
        self,
        config_provider: Callable[[], AppConfig],
        fallback_config: AppConfig,
        *,
        profiles: tuple[ReadinessProfile, ...] = READINESS_PROFILES,
    ) -> None:
        self._config_provider = config_provider
        self._fallback_config = fallback_config
        self._profiles = profiles
        self._selected_profile = profiles[0].key if profiles else "auto"

    @property
    def profiles(self) -> tuple[ReadinessProfile, ...]:
        return self._profiles

    @property
    def selected_profile_key(self) -> str:
        return self._selected_profile

    def select_profile(self, profile_key: str) -> ReadinessProfile:
        profile = self.profile(profile_key)
        self._selected_profile = profile.key
        return profile

    def profile(self, profile_key: str | None = None) -> ReadinessProfile:
        selected = str(profile_key or self._selected_profile or "").strip()
        return next((profile for profile in self._profiles if profile.key == selected), self._profiles[0])

    def profile_config(self, profile_key: str | None = None) -> AppConfig:
        try:
            config = self._config_provider()
        except Exception:
            config = self._fallback_config
        profile = self.profile(profile_key)
        config = _config_with_preset(config, profile.preset)
        return _replace_config_values(config, dict(profile.overrides or {}))

    def status(self, profile_key: str | None = None) -> ReadinessStatus:
        config = self.profile_config(profile_key)
        items = build_runtime_health(config)
        attention = tuple(item for item in items if item.status == "ATTENTION")
        return ReadinessStatus(
            config=config,
            items=items,
            text=format_runtime_health(items),
            attention_count=len(attention),
            provider_preview_kind=provider_preview_kind(items),
        )


def provider_preview_kind(items: tuple[object, ...]) -> str:
    attention_names = [
        str(getattr(item, "name", "") or "").lower() for item in items if getattr(item, "status", "") == "ATTENTION"
    ]
    for name, kind in (
        ("asr", "asr"),
        ("translation", "translation"),
        ("tts", "tts"),
        ("ocr", "ocr"),
    ):
        if name in attention_names:
            return kind
    return "tts"


def _config_with_preset(config: AppConfig, preset_id: str) -> AppConfig:
    preset = PERFORMANCE_PRESETS.get(preset_id) or {}
    return _replace_config_values(config, preset)


def _replace_config_values(config: AppConfig, values: dict[str, Any]) -> AppConfig:
    field_names = {field.name for field in fields(AppConfig)}
    updates = {name: value for name, value in values.items() if name in field_names and value is not None}
    return replace(config, **updates) if updates else config
