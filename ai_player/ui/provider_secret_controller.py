from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_player.ui.features.context import WindowContext

from collections.abc import Callable

ProviderSecretLoader = Callable[[], dict[str, str]]
NamedProviderSecretLoader = Callable[[str], dict[str, str]]
ProviderSecretSaver = Callable[[dict[str, str]], None]
NamedProviderSecretSaver = Callable[[str, dict[str, str]], None]


class ProviderSecretController:
    SECRET_CONTROLS: dict[str, tuple[tuple[str, str], ...]] = {
        "asr": (("_asr_api_key_edit", "asr_api_key"),),
        "ocr": (("_ocr_api_key_edit", "ocr_api_key"),),
        "translation": (("_translator_api_key_edit", "translator_api_key"),),
        "tts": (
            ("_tts_api_key_edit", "tts_api_key"),
            ("_tts_api_secret_edit", "tts_api_secret"),
        ),
        "cleanup": (("_transcript_cleanup_api_key_edit", "transcript_cleanup_api_key"),),
        "speaker_gender": (("_speaker_gender_api_key_edit", "speaker_gender_api_key"),),
    }
    SECRET_NAMES: tuple[str, ...] = (
        "asr_api_key",
        "ocr_api_key",
        "translator_api_key",
        "tts_api_key",
        "tts_api_secret",
        "transcript_cleanup_api_key",
        "speaker_gender_api_key",
    )

    def __init__(
        self,
        owner: WindowContext,
        *,
        load_asr_provider_api_keys: ProviderSecretLoader,
        load_provider_api_secrets: NamedProviderSecretLoader,
        save_asr_provider_api_keys: ProviderSecretSaver,
        save_provider_api_secrets: NamedProviderSecretSaver,
    ) -> None:
        self.context = owner
        self._load_asr_provider_api_keys = load_asr_provider_api_keys
        self._load_provider_api_secrets = load_provider_api_secrets
        self._save_asr_provider_api_keys = save_asr_provider_api_keys
        self._save_provider_api_secrets = save_provider_api_secrets
        self._cache: dict[str, dict[str, str]] = {}

    @property
    def cache_map(self) -> dict[str, dict[str, str]]:
        return self._cache

    def cache(self, secret_name: str) -> dict[str, str]:
        if secret_name not in self._cache:
            if secret_name == "asr_api_key":
                keys = self._load_asr_provider_api_keys()
            else:
                keys = self._load_provider_api_secrets(secret_name)
            keys = dict(keys)
            provider = self.context.settings._config_secret_provider(secret_name)
            value = str(getattr(self.context.config, secret_name, "") or "")
            if value and provider:
                keys[provider] = value
            self._cache[secret_name] = keys
        return self._cache[secret_name]

    def controls_for_kind(self, kind: str) -> tuple[tuple[str, str], ...]:
        return self.SECRET_CONTROLS.get(kind, ())

    def remember_kind(self, kind: str, provider: object | None = None) -> None:
        provider_key = self.context.settings._secret_provider_for_kind(kind, provider)
        if not provider_key:
            return
        for widget_name, secret_name in self.controls_for_kind(kind):
            widget = self.context.get(widget_name, None)
            if widget is None:
                continue
            key = widget.text().strip()
            cache = self.cache(secret_name)
            if key:
                cache[provider_key] = key
            else:
                cache.pop(provider_key, None)

    def restore_kind(self, kind: str, provider: object | None = None) -> None:
        provider_key = self.context.settings._secret_provider_for_kind(kind, provider)
        for widget_name, secret_name in self.controls_for_kind(kind):
            widget = self.context.get(widget_name, None)
            if widget is None:
                continue
            key = self.cache(secret_name).get(provider_key, "")
            was_blocked = widget.blockSignals(True)
            try:
                widget.setText(key)
            finally:
                widget.blockSignals(was_blocked)
        self.context.settings._sync_api_key_statuses()

    def save_all(self, kinds: tuple[str, ...]) -> None:
        for kind in kinds:
            self.remember_kind(kind)
        for secret_name in self.SECRET_NAMES:
            self.cache(secret_name)
        for secret_name, keys in self._cache.items():
            if secret_name == "asr_api_key":
                self._save_asr_provider_api_keys(keys)
            else:
                self._save_provider_api_secrets(secret_name, keys)
