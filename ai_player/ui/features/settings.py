from __future__ import annotations

import math
from dataclasses import replace

from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel, QLineEdit, QMessageBox, QPushButton, QSlider, QWidget

from ai_player.adapters.ai.asr import is_auto_asr_provider, is_online_asr_provider, normalize_asr_provider
from ai_player.adapters.ai.speaker_voice_selector import (
    is_online_speaker_gender_provider,
    normalize_speaker_gender_provider,
    normalize_voice_gender_mode,
)
from ai_player.adapters.ai.subtitle_ocr import is_online_ocr_provider, normalize_ocr_provider
from ai_player.adapters.ai.transcript_cleanup import is_online_transcript_cleanup_provider
from ai_player.adapters.ai.translation import (
    available_translation_models,
    is_ctranslate2_model_path,
    is_online_translation_provider,
    normalize_translator_provider,
)
from ai_player.adapters.media.source_voice_filter import (
    normalize_source_voice_filter_mode,
    normalize_source_voice_filter_model,
)
from ai_player.adapters.storage.settings_store import (
    load_asr_provider_api_keys,
    load_provider_api_secrets,
    save_app_config,
    save_asr_provider_api_keys,
    save_provider_api_secrets,
)
from ai_player.adapters.tts.tts import available_voices
from ai_player.adapters.tts.tts_base import available_tts_providers, is_online_tts_provider, normalize_tts_provider
from ai_player.adapters.tts.tts_vieneu import available_vieneu_models
from ai_player.adapters.tts.tts_voices import voice_gender
from ai_player.configuration import DEFAULT_PERFORMANCE_PRESET, AppConfig, read_preserved_source_terms_file
from ai_player.domain.audio_timeline import normalize_overlap_policy
from ai_player.runtime.runtime_catalog import (
    available_asr_providers,
    available_language_options,
    available_translation_provider_options,
)
from ai_player.ui.api_key_status_controller import ApiKeyStatusController
from ai_player.ui.features.base import Feature
from ai_player.ui.player_window_utils import (
    PERFORMANCE_PRESETS,
    UI_TEXT,
    UI_TEXT_ALIASES,
)
from ai_player.ui.player_window_utils import (
    dropdown_options as _dropdown_options,
)
from ai_player.ui.player_window_utils import (
    repair_mojibake as _repair_mojibake,
)
from ai_player.ui.player_window_utils import (
    ui_label as _ui_label,
)
from ai_player.ui.provider_secret_controller import ProviderSecretController


def _normalize_transcript_cleanup_provider(value: object) -> str:
    provider = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "openai_compatible": "openai",
        "api": "openai",
        "groqcloud": "groq",
        "gemini": "groq",
        "google_gemini": "groq",
        "google_ai": "groq",
        "ai_studio": "groq",
        "open_router": "openrouter",
        "openrouter_free": "openrouter",
        "hugging_face": "huggingface",
        "hf": "huggingface",
        "hf_inference": "huggingface",
        "hf_router": "huggingface",
        "ollama": "groq",
        "local": "groq",
        "headless": "groq",
        "headless_local": "groq",
        "local_headless": "groq",
        "transformers": "groq",
        "llamacpp": "groq",
        "llama_cpp": "groq",
    }
    return aliases.get(provider, provider or "groq")


class PlayerSettingsFeature(Feature):
    _PRIMARY_TRANSCRIPT_CLEANUP_API_PROVIDERS = {"groq"}
    _PRIMARY_TRANSCRIPT_CLEANUP_KEY_PROVIDERS = {"groq"}
    _ONLINE_PROVIDER_DETAIL_KEYS = {
        "asr": "runtime_privacy_detail_asr",
        "ocr": "runtime_privacy_detail_ocr",
        "translation": "runtime_privacy_detail_translation",
        "tts": "runtime_privacy_detail_tts",
        "cleanup": "runtime_privacy_detail_cleanup",
    }
    _ONLINE_PROVIDER_FEATURE_KEYS = {
        "asr": "online_provider_consent_feature_asr",
        "ocr": "online_provider_consent_feature_ocr",
        "translation": "online_provider_consent_feature_translation",
        "tts": "online_provider_consent_feature_tts",
        "cleanup": "online_provider_consent_feature_cleanup",
    }

    def _refresh_tts_options(self, *_args) -> None:
        provider = self.context.settings._selected_tts_provider()
        is_vieneu = provider == "vieneu"
        self.context.layout._tts_mode_label.setVisible(is_vieneu)
        self.context.layout._vieneu_mode_combo.setVisible(is_vieneu)
        self.context.layout._tts_model_label.setVisible(is_vieneu)
        self.context.layout._vieneu_model_combo.setVisible(is_vieneu)
        self.context.settings._refresh_vieneu_models()
        self.context.settings._refresh_tts_voices()
        self.context.settings._sync_vieneu_advanced_controls()

    def _advanced_provider_options_enabled(self) -> bool:
        checkbox = self.context.get("_advanced_provider_options_check", None)
        if checkbox is not None:
            return checkbox.isChecked()
        return bool(getattr(self.context.config, "show_advanced_provider_options", False))

    def _refresh_advanced_provider_options(self, *_args) -> None:
        self.context.settings._refresh_asr_provider_options()
        self.context.settings._refresh_translation_provider_options()
        self.context.settings._refresh_tts_provider_options()
        self.context.settings._sync_asr_controls()
        self.context.settings._refresh_translation_models()
        self.context.settings._refresh_tts_options()
        self.context.settings._sync_api_key_statuses()

    def _refresh_asr_provider_options(self) -> None:
        if not self.context.has("_asr_provider_combo"):
            return
        current = normalize_asr_provider(self.context.settings._selected_asr_provider())
        options = available_asr_providers(include_advanced=self.context.settings._advanced_provider_options_enabled())
        if current not in {option.id for option in options}:
            advanced = next(
                (option for option in available_asr_providers(include_advanced=True) if option.id == current),
                None,
            )
            if advanced is not None:
                options.append(advanced)
        self.context.settings._replace_combo_options(
            self.context.layout._asr_provider_combo,
            [(option.name, option.id) for option in options],
            current=current,
        )

    def _refresh_translation_provider_options(self) -> None:
        if not self.context.has("_translator_combo"):
            return
        current = normalize_translator_provider(
            self.context.layout._translator_combo.currentData() or self.context.config.translator_provider
        )
        language = self.context.settings._selected_gui_language()
        options = available_translation_provider_options(
            language,
            include_advanced=self.context.settings._advanced_provider_options_enabled(),
        )
        if current not in {option.id for option in options}:
            advanced = next(
                (
                    option
                    for option in available_translation_provider_options(language, include_advanced=True)
                    if option.id == current
                ),
                None,
            )
            if advanced is not None:
                options.append(advanced)
        self.context.settings._replace_combo_options(
            self.context.layout._translator_combo,
            [(option.name, option.id) for option in options],
            current=current,
        )

    def _refresh_tts_provider_options(self) -> None:
        if not self.context.has("_tts_provider_combo"):
            return
        current = normalize_tts_provider(self.context.settings._selected_tts_provider())
        options = available_tts_providers(include_advanced=self.context.settings._advanced_provider_options_enabled())
        if current not in {option.id for option in options}:
            advanced = next(
                (option for option in available_tts_providers(include_advanced=True) if option.id == current),
                None,
            )
            if advanced is not None:
                options.append(advanced)
        self.context.settings._replace_combo_options(
            self.context.layout._tts_provider_combo,
            [(option.name, option.id) for option in options],
            current=current,
        )

    def _refresh_vieneu_models(self, *_args) -> None:
        previous_model = self.context.settings._selected_vieneu_model() or self.context.config.vieneu_tts_model_name
        self.context.layout._vieneu_model_combo.clear()

        for model in available_vieneu_models(self.context.settings._selected_vieneu_model_mode(), self.context.config):
            self.context.layout._vieneu_model_combo.addItem(
                model.name,
                {"id": model.id, "offline": model.offline},
            )

        index = self.context.layout._vieneu_model_combo.findData(
            {"id": previous_model, "offline": self.context.settings._selected_vieneu_model_offline()}
        )
        if index < 0:
            for row in range(self.context.layout._vieneu_model_combo.count()):
                data = self.context.layout._vieneu_model_combo.itemData(row) or {}
                if data.get("id") == previous_model:
                    index = row
                    break
        self.context.layout._vieneu_model_combo.setCurrentIndex(max(0, index))
        self.context.settings._refresh_tts_voices()

    def _refresh_tts_voices(self, *_args) -> None:
        provider = self.context.settings._selected_tts_provider()
        previous_voice = (
            self.context.settings._editable_combo_value(self.context.layout._tts_voice_combo)
            or self.context.config.tts_voice
        )
        previous_male_voice = (
            self.context.settings._editable_combo_value(self.context.layout._tts_male_voice_combo)
            or self.context.config.tts_male_voice
        )
        previous_female_voice = (
            self.context.settings._editable_combo_value(self.context.layout._tts_female_voice_combo)
            or self.context.config.tts_female_voice
        )
        self.context.layout._tts_voice_combo.clear()
        self.context.layout._tts_male_voice_combo.clear()
        self.context.layout._tts_female_voice_combo.clear()

        voices = available_voices(provider, self.context.settings._current_tts_config())
        for voice in voices:
            self.context.layout._tts_voice_combo.addItem(voice.name, voice.id)

        preferred_voice = previous_voice
        if provider != self.context.config.tts_provider:
            preferred_voice = voices[0].id if voices else ""
        index = self.context.layout._tts_voice_combo.findData(preferred_voice)
        if index < 0 and preferred_voice:
            self.context.layout._tts_voice_combo.addItem(preferred_voice, preferred_voice)
            index = self.context.layout._tts_voice_combo.findData(preferred_voice)
        self.context.layout._tts_voice_combo.setCurrentIndex(max(0, index))
        self.context.settings._populate_gender_voice_combo(
            self.context.layout._tts_male_voice_combo,
            voices,
            "male",
            previous_male_voice,
        )
        self.context.settings._populate_gender_voice_combo(
            self.context.layout._tts_female_voice_combo,
            voices,
            "female",
            previous_female_voice,
        )
        self.context.settings._sync_auto_voice_controls_enabled()

    def _sync_auto_voice_controls_enabled(self, *_args) -> None:
        enabled = self.context.layout._auto_voice_gender_check.isChecked()
        for widget in (
            self.context.layout._auto_voice_gender_mode_combo,
            self.context.layout._tts_male_voice_combo,
            self.context.layout._tts_female_voice_combo,
        ):
            widget.setEnabled(enabled)
        ai_enabled = enabled and self.context.settings._selected_auto_voice_gender_mode() == "ai"
        if self.context.has("_speaker_gender_model_combo"):
            self.context.layout._speaker_gender_model_combo.setEnabled(ai_enabled)
        if self.context.has("_speaker_gender_provider_combo"):
            self.context.layout._speaker_gender_provider_combo.setEnabled(ai_enabled)
        online = ai_enabled and is_online_speaker_gender_provider(
            self.context.settings._selected_speaker_gender_provider()
        )
        for widget_name in (
            "_speaker_gender_api_base_edit",
            "_speaker_gender_api_key_edit",
            "_speaker_gender_timeout_slider",
            "_speaker_gender_timeout_value",
        ):
            widget = self.context.get(widget_name, None)
            if widget is not None:
                widget.setEnabled(online)
        if not online:
            api_base = self.context.get("_speaker_gender_api_base_edit", None)
            api_key = self.context.get("_speaker_gender_api_key_edit", None)
            if api_base is not None and api_base.text():
                api_base.clear()
            if api_key is not None and api_key.text():
                api_key.clear()
        self.context.settings._sync_api_key_statuses()

    def _sync_auto_match_controls_enabled(self, *_args) -> None:
        if not self.context.has("_auto_match_audio_check"):
            return
        enabled = self.context.layout._auto_match_audio_check.isChecked()
        for widget in (
            self.context.layout._speed_min_slider,
            self.context.layout._speed_min_value,
            self.context.layout._speed_max_slider,
            self.context.layout._speed_max_value,
            self.context.layout._volume_gain_min_slider,
            self.context.layout._volume_gain_min_value,
            self.context.layout._volume_gain_max_slider,
            self.context.layout._volume_gain_max_value,
        ):
            widget.setEnabled(enabled)

    def _populate_gender_voice_combo(
        self,
        combo: QComboBox,
        voices,
        gender: str,
        preferred_voice: str,
    ) -> None:
        provider = self.context.settings._selected_tts_provider()
        gendered_voices = [voice for voice in voices if voice_gender(provider, voice.id) == gender]
        if not gendered_voices:
            gendered_voices = list(voices)
        for voice in gendered_voices:
            combo.addItem(voice.name, voice.id)
        index = combo.findData(preferred_voice)
        if index < 0 and preferred_voice:
            combo.addItem(preferred_voice, preferred_voice)
            index = combo.findData(preferred_voice)
        combo.setCurrentIndex(max(0, index))

    def _selected_tts_provider(self) -> str:
        return self.context.layout._tts_provider_combo.currentData() or self.context.config.tts_provider

    def _selected_gui_language(self) -> str:
        return self.context.layout._ui_language_combo.currentData() or self.context.config.gui_language or "vi"

    def _selected_audio_source(self) -> str:
        return self.context.layout._audio_source_combo.currentData() or self.context.config.audio_source

    def _selected_source_filter_mode(self) -> str:
        if self.context.has("_source_filter_mode_combo"):
            return normalize_source_voice_filter_mode(self.context.layout._source_filter_mode_combo.currentData())
        return normalize_source_voice_filter_mode(self.context.config.original_audio_voice_filter_mode)

    def _selected_source_filter_model(self) -> str:
        if self.context.has("_source_filter_model_combo"):
            return normalize_source_voice_filter_model(self.context.layout._source_filter_model_combo.currentData())
        return normalize_source_voice_filter_model(self.context.config.original_audio_voice_filter_model)

    def _sync_source_filter_controls(self, *_args) -> None:
        if not self.context.has("_source_filter_check"):
            return
        enabled = self.context.layout._source_filter_check.isChecked()
        provider = self.context.settings._selected_source_filter_mode()
        if self.context.has("_source_filter_mode_combo"):
            self.context.layout._source_filter_mode_combo.setEnabled(enabled)
        if self.context.has("_source_filter_model_combo"):
            self.context.layout._source_filter_model_combo.setEnabled(enabled and provider != "fast")

    def _selected_video_aspect_ratio(self) -> str:
        value = self.context.layout._aspect_combo.currentData() if self.context.has("_aspect_combo") else ""
        return value if value in {"16:9", "9:16"} else "16:9"

    def _selected_playback_video_quality(self) -> str:
        if self.context.has("_playback_quality_combo"):
            return (
                self.context.layout._playback_quality_combo.currentData() or self.context.config.playback_video_quality
            )
        return self.context.config.playback_video_quality

    def _selected_video_url_full_cache(self) -> bool:
        if self.context.has("_video_url_full_cache_check"):
            return self.context.layout._video_url_full_cache_check.isChecked()
        return self.context.config.video_url_full_cache

    def _selected_video_cache_dir(self) -> str:
        if self.context.has("_video_cache_dir_edit"):
            return self.context.layout._video_cache_dir_edit.text().strip()
        return self.context.config.video_cache_dir

    def _selected_source_language(self) -> str:
        return self.context.layout._source_language_combo.currentData() or "auto"

    def _selected_target_language(self) -> str:
        return self.context.layout._target_language_combo.currentData() or "vi"

    def _language_pair_changed(self, *_args) -> None:
        self.context.settings._queue_save_settings()

    def _selected_asr_provider(self) -> str:
        if self.context.has("_asr_provider_combo"):
            return self.context.layout._asr_provider_combo.currentData() or self.context.config.asr_provider
        return self.context.config.asr_provider

    def _asr_api_key_cache(self) -> dict[str, str]:
        return self.context.settings._provider_secret_cache("asr_api_key")

    def _remember_asr_api_key_for_provider(self, provider: str) -> None:
        self.context.settings._remember_provider_secrets_for_kind("asr", provider)

    def _restore_asr_api_key_for_provider(self, provider: str) -> None:
        self.context.settings._restore_provider_secrets_for_kind("asr", provider)

    def _provider_secret_controller(self) -> ProviderSecretController:
        controller = self.context.get("_provider_secrets", None)
        if controller is None:
            controller = ProviderSecretController(
                self.context,
                load_asr_provider_api_keys=load_asr_provider_api_keys,
                load_provider_api_secrets=load_provider_api_secrets,
                save_asr_provider_api_keys=save_asr_provider_api_keys,
                save_provider_api_secrets=save_provider_api_secrets,
            )
            self.context.settings._provider_secrets = controller
        return controller

    def _api_key_status_controller(self) -> ApiKeyStatusController:
        controller = self.context.get("_api_key_statuses", None)
        if controller is None:
            controller = ApiKeyStatusController(self.context)
            self.context.settings._api_key_statuses = controller
        return controller

    def _provider_secret_cache(self, secret_name: str) -> dict[str, str]:
        return self.context.settings._provider_secret_controller().cache(secret_name)

    def _secret_controls_for_kind(self, kind: str) -> tuple[tuple[str, str], ...]:
        return self.context.settings._provider_secret_controller().controls_for_kind(kind)

    def _remember_provider_secrets_for_kind(self, kind: str, provider: object | None = None) -> None:
        self.context.settings._provider_secret_controller().remember_kind(kind, provider)

    def _restore_provider_secrets_for_kind(self, kind: str, provider: object | None = None) -> None:
        self.context.settings._provider_secret_controller().restore_kind(kind, provider)

    def _secret_provider_for_kind(self, kind: str, provider: object | None = None) -> str:
        if kind == "asr":
            return self.context.settings._asr_secret_provider(
                provider if provider is not None else self.context.settings._selected_asr_provider()
            )
        if kind == "ocr":
            return normalize_ocr_provider(
                provider if provider is not None else self.context.settings._selected_ocr_provider()
            )
        if kind == "translation":
            selected = provider if provider is not None else self.context.layout._translator_combo.currentData()
            return normalize_translator_provider(selected)
        if kind == "tts":
            return normalize_tts_provider(
                provider if provider is not None else self.context.settings._selected_tts_provider()
            )
        if kind == "cleanup":
            return _normalize_transcript_cleanup_provider(
                provider if provider is not None else self.context.settings._selected_transcript_cleanup_provider()
            )
        if kind == "speaker_gender":
            return normalize_speaker_gender_provider(
                provider if provider is not None else self.context.settings._selected_speaker_gender_provider()
            )
        return str(provider or "").strip().lower().replace("-", "_").replace(" ", "_")

    def _config_secret_provider(self, secret_name: str) -> str:
        if secret_name == "asr_api_key":
            return self.context.settings._asr_secret_provider(self.context.config.asr_provider)
        if secret_name == "ocr_api_key":
            return normalize_ocr_provider(self.context.config.ocr_provider)
        if secret_name == "translator_api_key":
            return normalize_translator_provider(self.context.config.translator_provider)
        if secret_name in {"tts_api_key", "tts_api_secret"}:
            return normalize_tts_provider(self.context.config.tts_provider)
        if secret_name == "transcript_cleanup_api_key":
            return _normalize_transcript_cleanup_provider(self.context.config.transcript_cleanup_provider)
        if secret_name == "speaker_gender_api_key":
            return normalize_speaker_gender_provider(self.context.config.speaker_gender_provider)
        return ""

    def _asr_secret_provider(self, provider: object) -> str:
        normalized = normalize_asr_provider(str(provider or ""))
        if normalized != "auto":
            return normalized
        api_base = (
            self.context.layout._asr_api_base_edit.text().strip().lower()
            if self.context.has("_asr_api_base_edit")
            else ""
        )
        if "assemblyai" in api_base:
            return "assemblyai"
        if "speechmatics" in api_base:
            return "speechmatics"
        language_hints = (
            self.context.layout._asr_language_hints_edit.text().strip()
            if self.context.has("_asr_language_hints_edit")
            else ""
        )
        source_language = (
            self.context.settings._selected_source_language() if self.context.has("_source_language_combo") else "auto"
        )
        if language_hints or not source_language or source_language == "auto":
            return "speechmatics"
        return "assemblyai"

    def _selected_asr_model(self) -> str:
        if self.context.has("_asr_model_combo"):
            return (
                self.context.settings._combo_value(self.context.layout._asr_model_combo)
                or self.context.config.whisper_model
            )
        return self.context.config.whisper_model

    def _sync_asr_controls(self, *_args) -> None:
        if not self.context.has("_asr_provider_combo"):
            return
        provider = self.context.settings._selected_asr_provider()
        online = is_online_asr_provider(provider)
        auto = is_auto_asr_provider(provider)
        for widget_name in (
            "_asr_model_combo",
            "_whisper_device_combo",
            "_whisper_compute_combo",
            "_whisper_beam_slider",
            "_whisper_beam_value",
            "_whisper_vad_check",
            "_whisper_offline_check",
        ):
            widget = self.context.get(widget_name, None)
            if widget is not None:
                widget.setEnabled(not online or auto)
        for widget_name in ("_asr_api_base_edit", "_asr_language_hints_edit", "_asr_api_key_edit"):
            widget = self.context.get(widget_name, None)
            if widget is not None:
                widget.setEnabled(online or auto)
        self.context.settings._sync_api_key_statuses()

    def _selected_ocr_provider(self) -> str:
        if self.context.has("_ocr_provider_combo"):
            return self.context.layout._ocr_provider_combo.currentData() or self.context.config.ocr_provider
        return self.context.config.ocr_provider

    def _selected_ocr_model(self) -> str:
        if self.context.has("_ocr_model_combo"):
            return (
                self.context.settings._combo_value(self.context.layout._ocr_model_combo)
                or self.context.config.ocr_model
            )
        return self.context.config.ocr_model

    def _sync_ocr_controls(self, *_args) -> None:
        if not self.context.has("_ocr_provider_combo"):
            return
        online = is_online_ocr_provider(self.context.settings._selected_ocr_provider())
        for widget_name in (
            "_ocr_api_base_edit",
            "_ocr_api_key_edit",
            "_ocr_api_region_edit",
            "_ocr_timeout_slider",
            "_ocr_timeout_value",
        ):
            widget = self.context.get(widget_name, None)
            if widget is not None:
                widget.setEnabled(online)
        for widget_name in ("_ocr_psm_slider", "_ocr_psm_value"):
            widget = self.context.get(widget_name, None)
            if widget is not None:
                widget.setEnabled(not online)
        self.context.settings._sync_api_key_statuses()

    def _selected_translator_provider(self) -> str:
        provider = self.context.layout._translator_combo.currentData() or "nllb"
        if provider == "none" or is_online_translation_provider(provider):
            return provider
        if is_ctranslate2_model_path(self.context.settings._selected_nllb_model()):
            return "nllb_ct2"
        return provider

    def _selected_nllb_model(self) -> str:
        value = self.context.settings._combo_value(self.context.layout._nllb_model_combo)
        provider = self.context.layout._translator_combo.currentData()
        if provider == "none" or is_online_translation_provider(provider):
            return ""
        return value if value else self.context.config.local_translation_model

    def _translator_changed(self, *_args) -> None:
        self.context.settings._refresh_translation_models()
        self.context.settings._queue_save_settings()

    def _refresh_translation_models(self, preferred_path: str | None = None) -> None:
        if not self.context.has("_nllb_model_combo"):
            return
        current = preferred_path
        if current is None:
            data = self.context.layout._nllb_model_combo.currentData()
            current = None if data is None else str(data)
        provider = self.context.layout._translator_combo.currentData()
        if provider == "none" or is_online_translation_provider(provider):
            current = ""
        elif provider == "nllb" and current and is_ctranslate2_model_path(current):
            current = ""
        elif provider == "nllb_ct2" and current and not is_ctranslate2_model_path(current):
            current = ""
        self.context.layout._nllb_model_combo.blockSignals(True)
        try:
            self.context.layout._nllb_model_combo.clear()
            for model in available_translation_models(provider):
                self.context.layout._nllb_model_combo.addItem(model.name, model.path)
            index = self.context.layout._nllb_model_combo.findData(current)
            if index < 0 and current:
                self.context.layout._nllb_model_combo.addItem(current, current)
                index = self.context.layout._nllb_model_combo.findData(current)
            self.context.layout._nllb_model_combo.setCurrentIndex(max(0, index))
        finally:
            self.context.layout._nllb_model_combo.blockSignals(False)
        self.context.settings._sync_translation_model_combo_enabled()

    def _nllb_model_changed(self, *_args) -> None:
        if is_ctranslate2_model_path(self.context.settings._selected_nllb_model()):
            self.context.settings._set_combo_data(self.context.layout._translator_combo, "nllb_ct2")
        self.context.settings._sync_translation_model_combo_enabled()
        self.context.settings._queue_save_settings()

    def _sync_translation_model_combo_enabled(self) -> None:
        provider = self.context.layout._translator_combo.currentData()
        online = is_online_translation_provider(provider)
        self.context.layout._nllb_model_combo.setEnabled(
            provider != "none" and not online and self.context.layout._nllb_model_combo.count() > 0
        )
        for widget_name in (
            "_translation_device_combo",
            "_translation_max_tokens_slider",
            "_translation_max_tokens_value",
            "_translation_beams_slider",
            "_translation_beams_value",
            "_translation_offline_check",
        ):
            widget = self.context.get(widget_name, None)
            if widget is not None:
                widget.setEnabled(provider != "none" and not online)
        for widget_name in ("_translator_api_base_edit", "_translator_api_key_edit", "_translator_api_region_edit"):
            widget = self.context.get(widget_name, None)
            if widget is not None:
                widget.setEnabled(online)
        self.context.settings._sync_api_key_statuses()

    def _selected_performance_preset(self) -> str:
        return self.context.layout._performance_preset_combo.currentData() or DEFAULT_PERFORMANCE_PRESET

    def _selected_export_video_quality(self) -> str:
        return self.context.layout._export_video_quality_combo.currentData() or self.context.config.export_video_quality

    def _selected_translation_device(self) -> str:
        return (
            self.context.layout._translation_device_combo.currentData() or self.context.config.local_translation_device
        )

    def _selected_whisper_device(self) -> str:
        return self.context.layout._whisper_device_combo.currentData() or self.context.config.whisper_device

    def _selected_whisper_compute(self) -> str:
        return self.context.layout._whisper_compute_combo.currentData() or self.context.config.whisper_compute_type

    def _selected_tts_voice(self) -> str:
        return self.context.settings._combo_value(self.context.layout._tts_voice_combo)

    def _selected_tts_male_voice(self) -> str:
        return (
            self.context.settings._combo_value(self.context.layout._tts_male_voice_combo)
            or self.context.settings._selected_tts_voice()
        )

    def _selected_tts_female_voice(self) -> str:
        return (
            self.context.settings._combo_value(self.context.layout._tts_female_voice_combo)
            or self.context.settings._selected_tts_voice()
        )

    def _selected_auto_voice_gender_mode(self) -> str:
        if self.context.has("_auto_voice_gender_mode_combo"):
            return normalize_voice_gender_mode(self.context.layout._auto_voice_gender_mode_combo.currentData())
        return normalize_voice_gender_mode(self.context.config.dubbing_auto_voice_gender_mode)

    def _selected_speaker_gender_model(self) -> str:
        if self.context.has("_speaker_gender_model_combo"):
            return self.context.settings._combo_value(self.context.layout._speaker_gender_model_combo)
        return self.context.config.speaker_gender_model

    def _selected_speaker_gender_provider(self) -> str:
        if self.context.has("_speaker_gender_provider_combo"):
            return normalize_speaker_gender_provider(self.context.layout._speaker_gender_provider_combo.currentData())
        return normalize_speaker_gender_provider(self.context.config.speaker_gender_provider)

    def _selected_overlap_policy(self) -> str:
        if self.context.has("_overlap_policy_combo"):
            return normalize_overlap_policy(self.context.layout._overlap_policy_combo.currentData())
        return normalize_overlap_policy(self.context.config.dubbing_overlap_policy)

    def _selected_vieneu_mode(self) -> str:
        return self.context.layout._vieneu_mode_combo.currentData() or self.context.config.vieneu_tts_mode

    def _selected_vieneu_model_mode(self) -> str:
        return self.context.settings._selected_vieneu_mode()

    def _selected_vieneu_model_data(self) -> dict:
        data = self.context.layout._vieneu_model_combo.currentData()
        return data if isinstance(data, dict) else {}

    def _selected_vieneu_model(self) -> str:
        return str(
            self.context.settings._selected_vieneu_model_data().get("id") or self.context.config.vieneu_tts_model_name
        )

    def _selected_vieneu_model_offline(self) -> bool:
        data = self.context.settings._selected_vieneu_model_data()
        if "offline" in data:
            return bool(data["offline"])
        return self.context.config.vieneu_tts_offline

    def _selected_vieneu_offline(self) -> bool:
        return (
            self.context.settings._selected_vieneu_model_offline()
            or self.context.layout._vieneu_offline_check.isChecked()
        )

    def _selected_vieneu_runtime(self) -> str:
        return self.context.layout._vieneu_runtime_combo.currentData() or self.context.config.vieneu_tts_runtime

    def _selected_vieneu_device(self) -> str:
        return self.context.layout._vieneu_device_combo.currentData() or self.context.config.vieneu_tts_device

    def _selected_vieneu_backend(self) -> str:
        return self.context.layout._vieneu_backend_combo.currentData() or self.context.config.vieneu_tts_backend

    def _selected_vieneu_core(self) -> str:
        return "local"

    def _selected_capture_backend(self) -> str:
        return self.context.layout._capture_backend_combo.currentData() or self.context.config.capture_backend

    def _selected_capture_system_device(self) -> str:
        return self.context.settings._combo_value(self.context.layout._capture_system_device_combo)

    def _selected_capture_microphone_device(self) -> str:
        return self.context.settings._combo_value(self.context.layout._capture_microphone_device_combo)

    def _selected_transcript_cleanup_mode(self) -> str:
        return (
            self.context.layout._transcript_cleanup_mode_combo.currentData()
            or self.context.config.transcript_cleanup_mode
        )

    def _selected_transcript_cleanup_provider(self) -> str:
        return (
            self.context.layout._transcript_cleanup_provider_combo.currentData()
            or self.context.config.transcript_cleanup_provider
        )

    def _selected_transcript_cleanup_model(self) -> str:
        index = self.context.layout._transcript_cleanup_model_combo.currentIndex()
        text = self.context.layout._transcript_cleanup_model_combo.currentText().strip()
        if index >= 0 and text == self.context.layout._transcript_cleanup_model_combo.itemText(index):
            data = self.context.layout._transcript_cleanup_model_combo.itemData(index)
            if data:
                return str(data).strip()
        return text

    def _sync_transcript_cleanup_controls(self, *_args) -> None:
        if not self.context.has("_transcript_cleanup_mode_combo"):
            return
        enabled = self.context.settings._selected_transcript_cleanup_mode() != "off"
        provider = self.context.settings._selected_transcript_cleanup_provider()
        self.context.layout._transcript_cleanup_provider_combo.setEnabled(enabled)
        self.context.layout._transcript_cleanup_model_combo.setEnabled(enabled)
        api_providers = self.context.settings._PRIMARY_TRANSCRIPT_CLEANUP_API_PROVIDERS
        key_providers = self.context.settings._PRIMARY_TRANSCRIPT_CLEANUP_KEY_PROVIDERS
        self.context.layout._transcript_cleanup_api_base_edit.setEnabled(enabled and provider in api_providers)
        self.context.layout._transcript_cleanup_api_key_edit.setEnabled(enabled and provider in key_providers)
        self.context.layout._cleanup_timeout_slider.setEnabled(enabled and provider in api_providers)
        self.context.layout._cleanup_timeout_value.setEnabled(enabled and provider in api_providers)
        if provider not in api_providers and self.context.layout._transcript_cleanup_api_base_edit.text():
            self.context.layout._transcript_cleanup_api_base_edit.clear()
        if provider not in key_providers and self.context.layout._transcript_cleanup_api_key_edit.text():
            self.context.layout._transcript_cleanup_api_key_edit.clear()
        self.context.settings._sync_api_key_statuses()

    def _sync_vieneu_advanced_controls(self, *_args) -> None:
        if not self.context.has("_vieneu_python_edit"):
            return
        provider = self.context.settings._selected_tts_provider()
        is_online = is_online_tts_provider(provider)
        self.context.layout._vieneu_offline_check.setEnabled(not is_online)
        for widget_name in (
            "_vieneu_python_edit",
            "_vieneu_runtime_combo",
            "_vieneu_device_combo",
            "_vieneu_backend_combo",
            "_vieneu_temperature_slider",
            "_vieneu_temperature_value",
            "_vieneu_max_chars_slider",
            "_vieneu_max_chars_value",
        ):
            widget = self.context.get(widget_name, None)
            if widget is not None:
                widget.setEnabled(not is_online)
        for widget_name in (
            "_tts_api_base_edit",
            "_tts_api_key_edit",
            "_tts_api_secret_edit",
            "_tts_api_region_edit",
            "_tts_model_edit",
        ):
            widget = self.context.get(widget_name, None)
            if widget is not None:
                widget.setEnabled(is_online)
        self.context.settings._sync_api_key_statuses()

    def _sync_api_key_statuses(self, *_args) -> None:
        self.context.settings._api_key_status_controller().sync()

    def _refresh_model_status_strip(self) -> None:
        self.context.settings._api_key_status_controller().refresh_model_status_strip()

    def _provider_status_text(
        self,
        *,
        provider: object,
        required: bool,
        has_value: bool,
        demo: bool = False,
        disabled: bool = False,
    ) -> tuple[str, str]:
        return self.context.settings._api_key_status_controller().provider_status_text(
            provider=provider,
            required=required,
            has_value=has_value,
            demo=demo,
            disabled=disabled,
        )

    def _set_model_status_pill(self, key: str, title: str, status: tuple[str, str]) -> None:
        self.context.settings._api_key_status_controller().set_model_status_pill(key, title, status)

    def _set_api_key_status(
        self,
        label: QLabel,
        *,
        required: bool,
        has_value: bool,
        demo: bool = False,
        secret: bool = False,
    ) -> None:
        self.context.settings._api_key_status_controller().set_api_key_status(
            label,
            required=required,
            has_value=has_value,
            demo=demo,
            secret=secret,
        )

    def _vieneu_core_changed(self, *_args) -> None:
        self.context.settings._refresh_vieneu_models()
        self.context.settings._sync_vieneu_advanced_controls()
        self.context.settings._queue_save_settings()

    @staticmethod
    def _combo_value(combo: QComboBox) -> str:
        text = combo.currentText().strip()
        data = combo.currentData()
        if combo.currentIndex() >= 0 and text == combo.itemText(combo.currentIndex()):
            return "" if data is None else str(data).strip()
        if text and text not in {"Auto", "Tự động"}:
            return text
        return "" if data is None else str(data).strip()

    def _editable_combo_value(self, combo: QComboBox) -> str:
        line_edit = combo.lineEdit() if combo.isEditable() else None
        if line_edit is not None:
            text = line_edit.text().strip()
            if text:
                return text
        return self.context.settings._combo_value(combo)

    def _current_runtime_config(self) -> AppConfig:
        preserved_terms = read_preserved_source_terms_file()
        config = replace(
            self.context.config,
            gui_language=self.context.settings._selected_gui_language(),
            show_advanced_provider_options=self.context.layout._advanced_provider_options_check.isChecked(),
            telegram_blacklisted_item_keys=tuple(sorted(self.context.sources.channel.blacklisted_item_keys)),
            telegram_blacklisted_content_keys=tuple(sorted(self.context.sources.channel.blacklisted_content_keys)),
            telegram_auto_open_videos=self.context.sources._telegram_auto_open_enabled(),
            telegram_last_url=self.context.sources._telegram_last_url_for_settings(),
            telegram_last_post_id=self.context.sources._telegram_last_post_id_for_settings(),
            telegram_last_search=self.context.sources._telegram_last_search_for_settings(),
            telegram_last_filter=self.context.sources._telegram_last_filter_for_settings(),
            telegram_side_panel_visible=bool(self.context.get("_telegram_side_panel_visible", True)),
            telegram_side_panel_sizes=self.context.sources._telegram_side_panel_sizes_for_settings(),
            video_aspect_ratio=self.context.settings._selected_video_aspect_ratio(),
            playback_video_quality=self.context.settings._selected_playback_video_quality(),
            video_url_full_cache=self.context.settings._selected_video_url_full_cache(),
            video_url_play_after_cache_percent=int(self.context.config.video_url_play_after_cache_percent),
            video_cache_dir=self.context.settings._selected_video_cache_dir(),
            video_url_recent_urls=self.context.sources._video_url_recent_urls_for_settings(),
            audio_source=self.context.settings._selected_audio_source(),
            capture_backend=self.context.settings._selected_capture_backend(),
            capture_system_device=self.context.settings._selected_capture_system_device(),
            capture_microphone_device=self.context.settings._selected_capture_microphone_device(),
            transcript_cleanup_mode=self.context.settings._selected_transcript_cleanup_mode(),
            transcript_cleanup_provider=self.context.settings._selected_transcript_cleanup_provider(),
            transcript_cleanup_model=self.context.settings._selected_transcript_cleanup_model(),
            transcript_cleanup_api_base=self.context.layout._transcript_cleanup_api_base_edit.text().strip(),
            transcript_cleanup_api_key=self.context.layout._transcript_cleanup_api_key_edit.text().strip(),
            transcript_cleanup_timeout_seconds=float(self.context.layout._cleanup_timeout_slider.value()),
            transcript_path=self.context.layout._transcript_path_edit.text().strip(),
            asr_provider=self.context.settings._selected_asr_provider(),
            asr_api_base=self.context.layout._asr_api_base_edit.text().strip(),
            asr_api_key=self.context.layout._asr_api_key_edit.text().strip(),
            asr_language_hints=self.context.layout._asr_language_hints_edit.text().strip(),
            whisper_model=self.context.settings._selected_asr_model(),
            performance_preset=self.context.settings._selected_performance_preset(),
            export_video_quality=self.context.settings._selected_export_video_quality(),
            whisper_device=self.context.settings._selected_whisper_device(),
            whisper_offline=self.context.layout._whisper_offline_check.isChecked(),
            whisper_compute_type=self.context.settings._selected_whisper_compute(),
            whisper_beam_size=int(self.context.layout._whisper_beam_slider.value()),
            whisper_vad_filter=self.context.layout._whisper_vad_check.isChecked(),
            ocr_provider=self.context.settings._selected_ocr_provider(),
            ocr_model=self.context.settings._selected_ocr_model(),
            ocr_api_base=self.context.layout._ocr_api_base_edit.text().strip(),
            ocr_api_key=self.context.layout._ocr_api_key_edit.text().strip(),
            ocr_api_region=self.context.layout._ocr_api_region_edit.text().strip(),
            ocr_timeout_seconds=float(self.context.layout._ocr_timeout_slider.value()),
            ocr_fps=float(self.context.layout._ocr_fps_slider.value() / 10),
            ocr_crop_top_ratio=float(self.context.layout._ocr_crop_top_slider.value() / 100),
            ocr_crop_height_ratio=float(self.context.layout._ocr_crop_height_slider.value() / 100),
            ocr_scale=float(self.context.layout._ocr_scale_slider.value() / 100),
            ocr_psm=int(self.context.layout._ocr_psm_slider.value()),
            ocr_threshold=self.context.layout._ocr_threshold_check.isChecked(),
            ocr_min_confidence=float(self.context.layout._ocr_min_confidence_slider.value()),
            ocr_merge_similarity=float(self.context.layout._ocr_merge_similarity_slider.value() / 100),
            local_translation_device=self.context.settings._selected_translation_device(),
            local_translation_model=self.context.settings._selected_nllb_model(),
            local_translation_offline=self.context.layout._translation_offline_check.isChecked(),
            translator_api_base=self.context.layout._translator_api_base_edit.text().strip(),
            translator_api_key=self.context.layout._translator_api_key_edit.text().strip(),
            translator_api_region=self.context.layout._translator_api_region_edit.text().strip(),
            preserve_source_terms=self.context.layout._preserve_terms_check.isChecked(),
            preserved_source_terms=preserved_terms,
            preserve_english_terms=self.context.layout._preserve_terms_check.isChecked(),
            preserved_english_terms=preserved_terms,
            translation_max_tokens=int(self.context.layout._translation_max_tokens_slider.value()),
            translation_num_beams=int(self.context.layout._translation_beams_slider.value()),
            segment_seconds=int(self.context.layout._segment_seconds_slider.value()),
            dubbing_start_delay_seconds=float(self.context.layout._start_delay_slider.value()),
            dubbing_prebuffer_segments=int(self.context.layout._prebuffer_segments_slider.value()),
            dubbing_lookahead_segments=int(self.context.layout._lookahead_segments_slider.value()),
            dubbing_min_ready_ahead_seconds=float(self.context.layout._dubbing_buffer_slider.value()),
            dubbing_voice_volume=int(self.context.layout._dub_volume_slider.value()),
            dubbing_speed_percent=int(self.context.layout._dub_speed_slider.value()),
            dubbing_auto_match_audio=self.context.layout._auto_match_audio_check.isChecked(),
            dubbing_overlap_policy=self.context.settings._selected_overlap_policy(),
            dubbing_auto_voice_gender=self.context.layout._auto_voice_gender_check.isChecked(),
            dubbing_auto_voice_gender_mode=self.context.settings._selected_auto_voice_gender_mode(),
            speaker_gender_provider=self.context.settings._selected_speaker_gender_provider(),
            speaker_gender_api_base=self.context.layout._speaker_gender_api_base_edit.text().strip(),
            speaker_gender_api_key=self.context.layout._speaker_gender_api_key_edit.text().strip(),
            speaker_gender_timeout_seconds=float(self.context.layout._speaker_gender_timeout_slider.value()),
            speaker_gender_model=self.context.settings._selected_speaker_gender_model(),
            dubbing_speed_min=float(self.context.layout._speed_min_slider.value() / 100),
            dubbing_speed_max=float(self.context.layout._speed_max_slider.value() / 100),
            dubbing_volume_gain_min_db=float(self.context.layout._volume_gain_min_slider.value()),
            dubbing_volume_gain_max_db=float(self.context.layout._volume_gain_max_slider.value()),
            original_audio_volume=int(self.context.layout._volume_slider.value()),
            original_audio_voice_filter=self.context.layout._source_filter_check.isChecked(),
            original_audio_voice_filter_mode=self.context.settings._selected_source_filter_mode(),
            original_audio_voice_filter_model=self.context.settings._selected_source_filter_model(),
            original_audio_playback_delay_seconds=int(self.context.layout._video_delay_slider.value()),
            dubbing_enabled_by_default=self.context.layout._dub_button.isChecked(),
            source_language=self.context.settings._selected_source_language(),
            target_language=self.context.settings._selected_target_language(),
            translator_provider=self.context.settings._selected_translator_provider(),
            tts_provider=self.context.settings._selected_tts_provider(),
            tts_voice=self.context.settings._selected_tts_voice(),
            tts_male_voice=self.context.settings._selected_tts_male_voice(),
            tts_female_voice=self.context.settings._selected_tts_female_voice(),
            tts_api_base=self.context.layout._tts_api_base_edit.text().strip(),
            tts_api_key=self.context.layout._tts_api_key_edit.text().strip(),
            tts_api_secret=self.context.layout._tts_api_secret_edit.text().strip(),
            tts_api_region=self.context.layout._tts_api_region_edit.text().strip(),
            tts_model=self.context.layout._tts_model_edit.text().strip(),
            runtime_warmup_enabled=self.context.layout._runtime_warmup_enabled_check.isChecked(),
            runtime_warmup_whisper=self.context.layout._runtime_warmup_whisper_check.isChecked(),
            runtime_warmup_translation=self.context.layout._runtime_warmup_translation_check.isChecked(),
            runtime_warmup_tts=self.context.layout._runtime_warmup_tts_check.isChecked(),
            vieneu_tts_runtime=self.context.settings._selected_vieneu_runtime(),
            vieneu_tts_python=self.context.layout._vieneu_python_edit.text().strip(),
            vieneu_tts_core=self.context.settings._selected_vieneu_core(),
            vieneu_tts_mode=self.context.settings._selected_vieneu_mode(),
            vieneu_tts_model_name=self.context.settings._selected_vieneu_model(),
            vieneu_tts_offline=self.context.settings._selected_vieneu_offline(),
            vieneu_tts_device=self.context.settings._selected_vieneu_device(),
            vieneu_tts_backend=self.context.settings._selected_vieneu_backend(),
            vieneu_tts_temperature=float(self.context.layout._vieneu_temperature_slider.value() / 100),
            vieneu_tts_max_chars_chunk=int(self.context.layout._vieneu_max_chars_slider.value()),
        )
        return config

    def _current_tts_config(self) -> AppConfig:
        return self.context.settings._current_runtime_config()

    def _apply_selected_performance_preset(self, *_args) -> None:
        preset_id = self.context.settings._selected_performance_preset()
        preset = PERFORMANCE_PRESETS.get(preset_id)
        if not preset:
            return

        self.context.settings._set_combo_data(self.context.layout._audio_source_combo, preset.get("audio_source"))
        self.context.settings._set_combo_data(self.context.layout._source_language_combo, preset.get("source_language"))
        self.context.settings._set_combo_data(self.context.layout._target_language_combo, preset.get("target_language"))
        self.context.settings._set_combo_data(self.context.layout._translator_combo, preset.get("translator_provider"))
        self.context.settings._set_combo_data(
            self.context.layout._nllb_model_combo, preset.get("local_translation_model")
        )
        self.context.settings._set_combo_data(
            self.context.layout._translation_device_combo, preset.get("local_translation_device")
        )
        self.context.settings._set_checkbox(
            self.context.layout._translation_offline_check, preset.get("local_translation_offline")
        )
        self.context.settings._set_line_edit_text(
            self.context.layout._translator_api_base_edit, preset.get("translator_api_base")
        )
        self.context.settings._set_line_edit_text(
            self.context.layout._translator_api_region_edit, preset.get("translator_api_region")
        )
        self.context.settings._set_slider_value(
            self.context.layout._translation_max_tokens_slider, preset.get("translation_max_tokens")
        )
        self.context.settings._set_slider_value(
            self.context.layout._translation_beams_slider, preset.get("translation_num_beams")
        )

        self.context.settings._set_combo_data(self.context.layout._tts_provider_combo, preset.get("tts_provider"))
        self.context.settings._set_combo_data(self.context.layout._vieneu_mode_combo, preset.get("vieneu_tts_mode"))
        self.context.settings._refresh_vieneu_models()
        self.context.settings._set_vieneu_model(preset.get("vieneu_tts_model_name"))
        self.context.settings._refresh_tts_voices()
        self.context.settings._set_combo_data(self.context.layout._tts_voice_combo, preset.get("tts_voice"))
        self.context.settings._set_combo_data(self.context.layout._tts_male_voice_combo, preset.get("tts_male_voice"))
        self.context.settings._set_combo_data(
            self.context.layout._tts_female_voice_combo, preset.get("tts_female_voice")
        )
        self.context.settings._set_combo_data(
            self.context.layout._vieneu_runtime_combo, preset.get("vieneu_tts_runtime")
        )
        self.context.settings._set_combo_data(self.context.layout._vieneu_device_combo, preset.get("vieneu_tts_device"))
        self.context.settings._set_combo_data(
            self.context.layout._vieneu_backend_combo, preset.get("vieneu_tts_backend")
        )
        self.context.settings._set_combo_data(self.context.layout._vieneu_core_combo, "local")
        self.context.settings._set_checkbox(self.context.layout._vieneu_offline_check, preset.get("vieneu_tts_offline"))
        self.context.settings._set_line_edit_text(self.context.layout._tts_api_base_edit, preset.get("tts_api_base"))
        self.context.settings._set_line_edit_text(
            self.context.layout._tts_api_region_edit, preset.get("tts_api_region")
        )
        self.context.settings._set_line_edit_text(self.context.layout._tts_model_edit, preset.get("tts_model"))
        self.context.settings._set_slider_value(
            self.context.layout._vieneu_temperature_slider,
            self.context.settings._scaled_preset_value(
                preset.get("vieneu_tts_temperature"),
                fallback=self.context.config.vieneu_tts_temperature,
                scale=100,
            ),
        )
        self.context.settings._set_slider_value(
            self.context.layout._vieneu_max_chars_slider, preset.get("vieneu_tts_max_chars_chunk")
        )

        self.context.settings._set_combo_data(self.context.layout._whisper_device_combo, preset.get("whisper_device"))
        self.context.settings._set_combo_data(self.context.layout._asr_provider_combo, preset.get("asr_provider"))
        self.context.settings._set_combo_data(self.context.layout._asr_model_combo, preset.get("whisper_model"))
        self.context.settings._set_line_edit_text(self.context.layout._asr_api_base_edit, preset.get("asr_api_base"))
        self.context.settings._set_combo_data(self.context.layout._ocr_provider_combo, preset.get("ocr_provider"))
        self.context.settings._set_combo_data(self.context.layout._ocr_model_combo, preset.get("ocr_model"))
        self.context.settings._set_line_edit_text(self.context.layout._ocr_api_base_edit, preset.get("ocr_api_base"))
        self.context.settings._set_line_edit_text(
            self.context.layout._ocr_api_region_edit, preset.get("ocr_api_region")
        )
        self.context.settings._set_slider_value(
            self.context.layout._ocr_timeout_slider, preset.get("ocr_timeout_seconds")
        )
        self.context.settings._set_combo_data(
            self.context.layout._whisper_compute_combo, preset.get("whisper_compute_type")
        )
        self.context.settings._set_slider_value(
            self.context.layout._whisper_beam_slider, preset.get("whisper_beam_size")
        )
        self.context.settings._set_checkbox(self.context.layout._whisper_vad_check, preset.get("whisper_vad_filter"))
        self.context.settings._set_checkbox(self.context.layout._whisper_offline_check, preset.get("whisper_offline"))
        whisper_model = preset.get("whisper_model")
        if whisper_model:
            self.context.config = replace(self.context.config, whisper_model=str(whisper_model))
        play_after_cache_percent = preset.get("video_url_play_after_cache_percent")
        if play_after_cache_percent is not None:
            self.context.config = replace(
                self.context.config, video_url_play_after_cache_percent=int(play_after_cache_percent)
            )
        self.context.settings._set_combo_data(
            self.context.layout._playback_quality_combo, preset.get("playback_video_quality")
        )
        self.context.settings._set_checkbox(
            self.context.layout._video_url_full_cache_check, preset.get("video_url_full_cache")
        )
        self.context.settings._set_slider_value(
            self.context.layout._segment_seconds_slider, preset.get("segment_seconds")
        )
        self.context.settings._set_slider_value(
            self.context.layout._start_delay_slider, preset.get("dubbing_start_delay_seconds")
        )
        self.context.settings._set_slider_value(
            self.context.layout._prebuffer_segments_slider, preset.get("dubbing_prebuffer_segments")
        )
        self.context.settings._set_slider_value(
            self.context.layout._dubbing_buffer_slider,
            preset.get("dubbing_min_ready_ahead_seconds"),
        )
        self.context.settings._set_slider_value(
            self.context.layout._lookahead_segments_slider,
            preset.get("dubbing_lookahead_segments"),
        )
        self.context.settings._set_slider_value(
            self.context.layout._dub_speed_slider, preset.get("dubbing_speed_percent")
        )
        self.context.settings._set_checkbox(
            self.context.layout._auto_voice_gender_check, preset.get("dubbing_auto_voice_gender")
        )
        self.context.settings._set_combo_data(
            self.context.layout._auto_voice_gender_mode_combo, preset.get("dubbing_auto_voice_gender_mode")
        )
        self.context.settings._set_combo_data(
            self.context.layout._speaker_gender_provider_combo, preset.get("speaker_gender_provider")
        )
        self.context.settings._set_combo_data(
            self.context.layout._speaker_gender_model_combo, preset.get("speaker_gender_model")
        )
        self.context.settings._set_line_edit_text(
            self.context.layout._speaker_gender_api_base_edit, preset.get("speaker_gender_api_base")
        )
        self.context.settings._set_slider_value(
            self.context.layout._speaker_gender_timeout_slider, preset.get("speaker_gender_timeout_seconds")
        )
        self.context.settings._set_checkbox(
            self.context.layout._auto_match_audio_check, preset.get("dubbing_auto_match_audio")
        )
        self.context.settings._set_combo_data(
            self.context.layout._overlap_policy_combo, preset.get("dubbing_overlap_policy")
        )
        self.context.settings._set_slider_value(
            self.context.layout._video_delay_slider, preset.get("original_audio_playback_delay_seconds")
        )
        self.context.settings._set_checkbox(
            self.context.layout._source_filter_check, preset.get("original_audio_voice_filter")
        )
        self.context.settings._set_combo_data(
            self.context.layout._source_filter_mode_combo, preset.get("original_audio_voice_filter_mode")
        )
        self.context.settings._set_combo_data(
            self.context.layout._source_filter_model_combo, preset.get("original_audio_voice_filter_model")
        )
        self.context.settings._set_combo_data(
            self.context.layout._export_video_quality_combo, preset.get("export_video_quality")
        )
        self.context.settings._set_slider_value(
            self.context.layout._speed_min_slider,
            self.context.settings._scaled_preset_value(
                preset.get("dubbing_speed_min"),
                fallback=self.context.config.dubbing_speed_min,
                scale=100,
            ),
        )
        self.context.settings._set_slider_value(
            self.context.layout._speed_max_slider,
            self.context.settings._scaled_preset_value(
                preset.get("dubbing_speed_max"),
                fallback=self.context.config.dubbing_speed_max,
                scale=100,
            ),
        )
        self.context.settings._set_slider_value(
            self.context.layout._volume_gain_min_slider, preset.get("dubbing_volume_gain_min_db")
        )
        self.context.settings._set_slider_value(
            self.context.layout._volume_gain_max_slider, preset.get("dubbing_volume_gain_max_db")
        )
        self.context.settings._set_checkbox(
            self.context.layout._runtime_warmup_tts_check, preset.get("runtime_warmup_tts")
        )
        self.context.settings._set_combo_data(
            self.context.layout._transcript_cleanup_mode_combo, preset.get("transcript_cleanup_mode")
        )
        self.context.settings._set_combo_data(
            self.context.layout._transcript_cleanup_provider_combo, preset.get("transcript_cleanup_provider")
        )
        self.context.settings._set_combo_data(
            self.context.layout._transcript_cleanup_model_combo, preset.get("transcript_cleanup_model")
        )
        self.context.settings._set_line_edit_text(
            self.context.layout._transcript_cleanup_api_base_edit, preset.get("transcript_cleanup_api_base")
        )
        self.context.settings._set_slider_value(
            self.context.layout._cleanup_timeout_slider, preset.get("transcript_cleanup_timeout_seconds")
        )
        self.context.settings._sync_auto_voice_controls_enabled()
        self.context.settings._sync_auto_match_controls_enabled()
        self.context.sources._sync_audio_source_controls()
        self.context.settings._sync_asr_controls()
        self.context.settings._sync_ocr_controls()
        self.context.settings._sync_vieneu_advanced_controls()
        self.context.settings._refresh_preset_inspector()
        self.context.settings._save_settings()
        self.context.window.statusBar().showMessage(self.context.settings._tr("status_preset_applied"))

    def _refresh_preset_inspector(self) -> None:
        label = self.context.get("_preset_inspector", None)
        if label is None:
            return
        preset_id = self.context.settings._selected_performance_preset()
        key = f"preset_inspector_{preset_id}"
        text = self.context.settings._tr(key)
        if text == key:
            text = self.context.settings._tr("preset_inspector_default")
        label.setText(text)
        if self.context.has("_refresh_preset_cards"):
            self.context.layout._refresh_preset_cards()

    def _connect_settings_autosave(self) -> None:
        self.context.settings._online_provider_consent_values: set[tuple[str, str]] = set()
        self.context.settings._online_provider_previous_values = {
            "asr": self.context.settings._selected_asr_provider(),
            "ocr": self.context.settings._selected_ocr_provider(),
            "translation": self.context.layout._translator_combo.currentData() or "nllb",
            "tts": self.context.settings._selected_tts_provider(),
            "cleanup": self.context.settings._selected_transcript_cleanup_provider(),
            "cleanup_mode": self.context.settings._selected_transcript_cleanup_mode(),
            "speaker_gender": self.context.settings._selected_speaker_gender_provider(),
        }
        combos = (
            self.context.layout._ui_language_combo,
            self.context.layout._performance_preset_combo,
            self.context.layout._export_video_quality_combo,
            self.context.layout._playback_quality_combo,
            self.context.layout._audio_source_combo,
            self.context.layout._source_filter_mode_combo,
            self.context.layout._source_filter_model_combo,
            self.context.layout._speaker_gender_model_combo,
            self.context.layout._speaker_gender_provider_combo,
            self.context.layout._source_language_combo,
            self.context.layout._target_language_combo,
            self.context.layout._asr_provider_combo,
            self.context.layout._asr_model_combo,
            self.context.layout._ocr_provider_combo,
            self.context.layout._ocr_model_combo,
            self.context.layout._translator_combo,
            self.context.layout._nllb_model_combo,
            self.context.layout._translation_device_combo,
            self.context.layout._tts_provider_combo,
            self.context.layout._vieneu_mode_combo,
            self.context.layout._vieneu_model_combo,
            self.context.layout._tts_voice_combo,
            self.context.layout._auto_voice_gender_mode_combo,
            self.context.layout._overlap_policy_combo,
            self.context.layout._tts_male_voice_combo,
            self.context.layout._tts_female_voice_combo,
            self.context.layout._whisper_device_combo,
            self.context.layout._whisper_compute_combo,
            self.context.layout._vieneu_runtime_combo,
            self.context.layout._vieneu_device_combo,
            self.context.layout._vieneu_backend_combo,
            self.context.layout._vieneu_core_combo,
            self.context.layout._capture_backend_combo,
            self.context.layout._capture_system_device_combo,
            self.context.layout._capture_microphone_device_combo,
            self.context.layout._transcript_cleanup_mode_combo,
            self.context.layout._transcript_cleanup_provider_combo,
            self.context.layout._transcript_cleanup_model_combo,
        )
        for combo in combos:
            combo.currentIndexChanged.connect(self.context.settings._queue_save_settings)
            if combo.isEditable():
                combo.lineEdit().editingFinished.connect(self.context.settings._queue_save_settings)

        checks = (
            self.context.layout._advanced_provider_options_check,
            self.context.layout._preserve_terms_check,
            self.context.layout._runtime_warmup_enabled_check,
            self.context.layout._runtime_warmup_whisper_check,
            self.context.layout._runtime_warmup_translation_check,
            self.context.layout._runtime_warmup_tts_check,
            self.context.layout._whisper_vad_check,
            self.context.layout._whisper_offline_check,
            self.context.layout._translation_offline_check,
            self.context.layout._vieneu_offline_check,
            self.context.layout._auto_voice_gender_check,
            self.context.layout._auto_match_audio_check,
            self.context.layout._dub_button,
            self.context.layout._source_filter_check,
            self.context.layout._ocr_threshold_check,
            self.context.layout._video_url_full_cache_check,
            self.context.layout._telegram_channel_auto_open_check,
        )
        for checkbox in checks:
            checkbox.toggled.connect(self.context.settings._queue_save_settings)
        self.context.layout._advanced_provider_options_check.toggled.connect(
            self.context.settings._refresh_advanced_provider_options
        )
        self.context.layout._auto_match_audio_check.toggled.connect(
            self.context.settings._sync_auto_match_controls_enabled
        )
        self.context.layout._asr_provider_combo.currentIndexChanged.connect(self.context.settings._sync_asr_controls)
        self.context.layout._asr_provider_combo.currentIndexChanged.connect(
            lambda *_args: self.context.settings._online_provider_changed(
                "asr", self.context.layout._asr_provider_combo
            )
        )
        self.context.layout._ocr_provider_combo.currentIndexChanged.connect(self.context.settings._sync_ocr_controls)
        self.context.layout._ocr_provider_combo.currentIndexChanged.connect(
            lambda *_args: self.context.settings._online_provider_changed(
                "ocr", self.context.layout._ocr_provider_combo
            )
        )
        self.context.layout._speaker_gender_provider_combo.currentIndexChanged.connect(
            self.context.settings._sync_auto_voice_controls_enabled
        )
        self.context.layout._speaker_gender_provider_combo.currentIndexChanged.connect(
            lambda *_args: self.context.settings._provider_secret_changed(
                "speaker_gender", self.context.layout._speaker_gender_provider_combo
            )
        )
        self.context.layout._translator_combo.currentIndexChanged.connect(
            lambda *_args: self.context.settings._online_provider_changed(
                "translation", self.context.layout._translator_combo
            )
        )
        self.context.layout._tts_provider_combo.currentIndexChanged.connect(
            lambda *_args: self.context.settings._online_provider_changed(
                "tts", self.context.layout._tts_provider_combo
            )
        )
        self.context.layout._transcript_cleanup_provider_combo.currentIndexChanged.connect(
            lambda *_args: self.context.settings._online_provider_changed(
                "cleanup", self.context.layout._transcript_cleanup_provider_combo
            )
        )
        self.context.layout._transcript_cleanup_mode_combo.currentIndexChanged.connect(
            self.context.settings._online_cleanup_mode_changed
        )

        sliders = (
            self.context.layout._volume_slider,
            self.context.layout._dub_volume_slider,
            self.context.layout._translation_max_tokens_slider,
            self.context.layout._translation_beams_slider,
            self.context.layout._whisper_beam_slider,
            self.context.layout._ocr_fps_slider,
            self.context.layout._ocr_crop_top_slider,
            self.context.layout._ocr_crop_height_slider,
            self.context.layout._ocr_scale_slider,
            self.context.layout._ocr_psm_slider,
            self.context.layout._ocr_timeout_slider,
            self.context.layout._ocr_min_confidence_slider,
            self.context.layout._ocr_merge_similarity_slider,
            self.context.layout._cleanup_timeout_slider,
            self.context.layout._dubbing_buffer_slider,
            self.context.layout._dub_speed_slider,
            self.context.layout._video_delay_slider,
            self.context.layout._segment_seconds_slider,
            self.context.layout._prebuffer_segments_slider,
            self.context.layout._lookahead_segments_slider,
            self.context.layout._start_delay_slider,
            self.context.layout._speed_min_slider,
            self.context.layout._speed_max_slider,
            self.context.layout._volume_gain_min_slider,
            self.context.layout._volume_gain_max_slider,
            self.context.layout._vieneu_temperature_slider,
            self.context.layout._vieneu_max_chars_slider,
            self.context.layout._speaker_gender_timeout_slider,
        )
        for slider in sliders:
            slider.valueChanged.connect(self.context.settings._queue_save_settings)

        self.context.layout._asr_api_base_edit.textEdited.connect(self.context.settings._queue_save_settings)
        self.context.layout._asr_language_hints_edit.textEdited.connect(self.context.settings._queue_save_settings)
        self.context.layout._asr_api_key_edit.textEdited.connect(self.context.settings._queue_save_settings)
        self.context.layout._asr_api_key_edit.textEdited.connect(self.context.settings._sync_api_key_statuses)
        self.context.layout._ocr_api_base_edit.textEdited.connect(self.context.settings._queue_save_settings)
        self.context.layout._ocr_api_key_edit.textEdited.connect(self.context.settings._queue_save_settings)
        self.context.layout._ocr_api_key_edit.textEdited.connect(self.context.settings._sync_api_key_statuses)
        self.context.layout._ocr_api_region_edit.textEdited.connect(self.context.settings._queue_save_settings)
        self.context.layout._translator_api_base_edit.textEdited.connect(self.context.settings._queue_save_settings)
        self.context.layout._translator_api_key_edit.textEdited.connect(self.context.settings._queue_save_settings)
        self.context.layout._translator_api_key_edit.textEdited.connect(self.context.settings._sync_api_key_statuses)
        self.context.layout._translator_api_region_edit.textEdited.connect(self.context.settings._queue_save_settings)
        self.context.layout._tts_api_base_edit.textEdited.connect(self.context.settings._queue_save_settings)
        self.context.layout._tts_api_key_edit.textEdited.connect(self.context.settings._queue_save_settings)
        self.context.layout._tts_api_key_edit.textEdited.connect(self.context.settings._sync_api_key_statuses)
        self.context.layout._tts_api_secret_edit.textEdited.connect(self.context.settings._queue_save_settings)
        self.context.layout._tts_api_secret_edit.textEdited.connect(self.context.settings._sync_api_key_statuses)
        self.context.layout._tts_api_region_edit.textEdited.connect(self.context.settings._queue_save_settings)
        self.context.layout._tts_model_edit.textEdited.connect(self.context.settings._queue_save_settings)
        self.context.layout._speaker_gender_api_base_edit.textEdited.connect(self.context.settings._queue_save_settings)
        self.context.layout._speaker_gender_api_key_edit.textEdited.connect(self.context.settings._queue_save_settings)
        self.context.layout._speaker_gender_api_key_edit.textEdited.connect(
            self.context.settings._sync_api_key_statuses
        )
        self.context.layout._transcript_cleanup_api_base_edit.textEdited.connect(
            self.context.settings._queue_save_settings
        )
        self.context.layout._transcript_cleanup_api_key_edit.textEdited.connect(
            self.context.settings._queue_save_settings
        )
        self.context.layout._transcript_cleanup_api_key_edit.textEdited.connect(
            self.context.settings._sync_api_key_statuses
        )
        for line_edit in (self.context.layout._vieneu_python_edit,):
            line_edit.textEdited.connect(self.context.settings._queue_save_settings)
            line_edit.editingFinished.connect(self.context.settings._queue_save_settings)
        self.context.layout._vieneu_core_combo.currentIndexChanged.connect(self.context.settings._vieneu_core_changed)
        self.context.layout._vieneu_mode_combo.currentIndexChanged.connect(
            self.context.settings._sync_vieneu_advanced_controls
        )
        self.context.settings._restore_asr_api_key_for_provider(self.context.settings._selected_asr_provider())

    def _online_provider_changed(self, kind: str, combo: QComboBox) -> None:
        value = str(combo.currentData() or "")
        previous = str(self.context.get("_online_provider_previous_values", {}).get(kind, value) or "")
        self.context.settings._remember_provider_secrets_for_kind(kind, previous)
        if not self.context.settings._online_provider_requires_consent(kind, value):
            self.context.settings._restore_provider_secrets_for_kind(kind, value)
            self.context.settings._remember_online_provider_value(kind, value)
            return
        if self.context.settings._confirm_online_provider(kind, value):
            self.context.settings._restore_provider_secrets_for_kind(kind, value)
            self.context.settings._remember_online_provider_value(kind, value)
            return
        self.context.settings._revert_online_provider_combo(kind, combo, previous)
        self.context.settings._restore_provider_secrets_for_kind(kind, previous)
        self.context.window.statusBar().showMessage(self.context.settings._tr("online_provider_consent_rejected"))

    def _provider_secret_changed(self, kind: str, combo: QComboBox) -> None:
        value = str(combo.currentData() or "")
        previous = str(self.context.get("_online_provider_previous_values", {}).get(kind, value) or "")
        self.context.settings._remember_provider_secrets_for_kind(kind, previous)
        self.context.settings._restore_provider_secrets_for_kind(kind, value)
        self.context.settings._remember_online_provider_value(kind, value)

    def _online_cleanup_mode_changed(self, *_args) -> None:
        value = self.context.settings._selected_transcript_cleanup_mode()
        previous = str(self.context.get("_online_provider_previous_values", {}).get("cleanup_mode", value) or "")
        provider = self.context.settings._selected_transcript_cleanup_provider()
        if value == "off" or not is_online_transcript_cleanup_provider(provider):
            self.context.settings._remember_online_provider_value("cleanup_mode", value)
            return
        if self.context.settings._confirm_online_provider("cleanup", provider):
            self.context.settings._remember_online_provider_value("cleanup_mode", value)
            return
        self.context.settings._revert_online_provider_combo(
            "cleanup_mode", self.context.layout._transcript_cleanup_mode_combo, previous
        )
        self.context.window.statusBar().showMessage(self.context.settings._tr("online_provider_consent_rejected"))

    def _online_provider_requires_consent(self, kind: str, value: str) -> bool:
        provider = str(value or "")
        if kind == "asr":
            online = is_online_asr_provider(provider) or is_auto_asr_provider(provider)
        elif kind == "ocr":
            online = is_online_ocr_provider(provider)
        elif kind == "translation":
            online = is_online_translation_provider(provider)
        elif kind == "tts":
            normalized = normalize_tts_provider(provider)
            online = normalized == "edge" or is_online_tts_provider(normalized)
            provider = normalized
        elif kind == "cleanup":
            online = (
                self.context.settings._selected_transcript_cleanup_mode() != "off"
                and is_online_transcript_cleanup_provider(provider)
            )
        else:
            online = False
        if not online:
            return False
        return (kind, provider) not in self.context.get("_online_provider_consent_values", set())

    def _confirm_online_provider(self, kind: str, provider: str) -> bool:
        provider = str(provider or "")
        if not self.context.window.isVisible():
            self.context.settings._remember_online_provider_consent(kind, provider)
            return True
        feature = self.context.settings._tr(
            self.context.settings._ONLINE_PROVIDER_FEATURE_KEYS.get(kind, "online_provider_consent_feature_provider")
        )
        detail = self.context.settings._tr(
            self.context.settings._ONLINE_PROVIDER_DETAIL_KEYS.get(kind, "runtime_privacy_offline")
        )
        message = self.context.settings._tr("online_provider_consent_message").format(
            feature=feature,
            provider=provider,
            detail=detail,
        )
        accepted = (
            QMessageBox.question(
                self.context.window,
                self.context.settings._tr("online_provider_consent_title"),
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )
        if accepted:
            self.context.settings._remember_online_provider_consent(kind, provider)
        return accepted

    def _remember_online_provider_consent(self, kind: str, provider: str) -> None:
        if not self.context.has("_online_provider_consent_values"):
            self.context.settings._online_provider_consent_values = set()
        self.context.settings._online_provider_consent_values.add((kind, str(provider or "")))

    def _remember_online_provider_value(self, kind: str, value: str) -> None:
        if not self.context.has("_online_provider_previous_values"):
            self.context.settings._online_provider_previous_values = {}
        self.context.settings._online_provider_previous_values[kind] = str(value or "")

    def _revert_online_provider_combo(self, kind: str, combo: QComboBox, previous: str) -> None:
        was_blocked = combo.blockSignals(True)
        try:
            self.context.settings._set_combo_data(combo, previous)
        finally:
            combo.blockSignals(was_blocked)
        self.context.settings._remember_online_provider_value(kind, previous)
        self.context.settings._sync_online_provider_controls(kind)
        self.context.settings._queue_save_settings()

    def _sync_online_provider_controls(self, kind: str) -> None:
        if kind == "asr":
            self.context.settings._sync_asr_controls()
        elif kind == "ocr":
            self.context.settings._sync_ocr_controls()
        elif kind == "translation":
            self.context.settings._refresh_translation_models()
        elif kind == "tts":
            self.context.settings._refresh_tts_options()
        elif kind in {"cleanup", "cleanup_mode"}:
            self.context.settings._sync_transcript_cleanup_controls()

    def _queue_save_settings(self, *_args) -> None:
        self.context.layout._settings_save_timer.start()

    def _gui_language_changed(self, *_args) -> None:
        self.context.settings._refresh_language_pack_combos()
        self.context.settings._retranslate_ui()
        self.context.settings._queue_save_settings()

    def _ui_language(self) -> str:
        return (
            self.context.settings._selected_gui_language()
            if self.context.has("_ui_language_combo")
            else self.context.config.gui_language
        )

    def _tr(self, key: str) -> str:
        language = self.context.settings._ui_language()
        fallback = UI_TEXT.get("vi", {})
        return UI_TEXT.get(language, fallback).get(key, fallback.get(key, key))

    def _retranslate_ui(self) -> None:
        self.context.window.setWindowTitle(self.context.settings._tr("window_title"))
        self.context.settings._translate_child_widgets(self.context.window)
        if not self.context.channel_browser._video_path:
            if self.context.has("_sync_media_browser_address"):
                self.context.media_browser._sync_media_browser_address()
            else:
                self.context.layout._source_label.setText(self.context.settings._tr("source_empty"))
        if self.context.has("_settings_tabs"):
            self.context.layout._settings_tabs.setTabText(0, self.context.settings._tr("first_run_tab"))
            self.context.layout._settings_tabs.setTabText(1, self.context.settings._tr("task_center_tab"))
            self.context.layout._settings_tabs.setTabText(2, self.context.settings._tr("basic_tab"))
            self.context.layout._settings_tabs.setTabText(3, self.context.settings._tr("models_tab"))
            self.context.layout._settings_tabs.setTabText(4, self.context.settings._tr("offline_models_tab"))
            self.context.layout._settings_tabs.setTabText(5, self.context.settings._tr("advanced_tab"))
            self.context.layout._settings_tabs.setTabText(6, self.context.settings._tr("transcript_tab"))
            self.context.layout._settings_tabs.setTabText(7, self.context.settings._tr("runtime_tab"))
        if self.context.has("_task_center_table"):
            self.context.task_center._task_center_table.setHorizontalHeaderLabels(
                [
                    self.context.settings._tr("task_center_name"),
                    self.context.settings._tr("task_center_status"),
                    self.context.settings._tr("task_center_detail"),
                ]
            )
        if self.context.has("_task_center_log_view"):
            self.context.task_center._task_center_log_view.setPlaceholderText(
                self.context.settings._tr("task_center_log_empty")
            )
        if self.context.has("_refresh_global_task_status"):
            self.context.task_center._refresh_global_task_status()
        if self.context.has("_refresh_readiness_profile_text"):
            self.context.readiness._refresh_readiness_profile_text()
            self.context.readiness._refresh_readiness_status()
        if self.context.has("_offline_models_log"):
            self.context.offline_models._offline_models_log.setPlaceholderText(
                self.context.settings._tr("offline_models_log_placeholder")
            )
        if self.context.has("_document_view"):
            placeholder_key = (
                "document_editor_placeholder" if self.context.media.document.editor_active else "document_placeholder"
            )
            self.context.layout._document_view.setPlaceholderText(self.context.settings._tr(placeholder_key))
            self.context.ui._set_control_tooltip(self.context.layout._document_view, placeholder_key)
        if self.context.has("_transcript"):
            self.context.layout._transcript.setPlaceholderText(self.context.settings._tr("transcript_placeholder"))
        if self.context.has("_transcript_segment_table"):
            self.context.bindings._transcript_segment_table.setHorizontalHeaderLabels(
                [
                    self.context.settings._tr("transcript_segment_index"),
                    self.context.settings._tr("transcript_segment_content"),
                    self.context.settings._tr("transcript_segment_status"),
                ]
            )
            self.context.transcript._refresh_transcript_segment_table()
        if self.context.has("_refresh_transcript_status_strip"):
            self.context.transcript._refresh_transcript_status_strip()
        if self.context.has("_sync_transcript_segment_banner"):
            self.context.transcript._sync_transcript_segment_banner()
        if self.context.has("_transcript_segment_target_edit"):
            self.context.bindings._transcript_segment_target_edit.setPlaceholderText(
                self.context.settings._tr("transcript_segment_target_placeholder")
            )
        if self.context.has("_transcript_path_edit"):
            self.context.layout._transcript_path_edit.setPlaceholderText(
                self.context.settings._tr("transcript_file_placeholder")
            )
        if self.context.has("_refresh_header_menu_text"):
            self.context.layout._refresh_header_menu_text()
        if self.context.has("_refresh_media_start_launcher_text"):
            self.context.layout._refresh_media_start_launcher_text()
        if self.context.has("_sync_runtime_stop_tasks_button_width"):
            self.context.runtime._sync_runtime_stop_tasks_button_width()
        if self.context.has("_refresh_next_action_panel"):
            self.context.transcript._refresh_next_action_panel()
        if self.context.has("_preserve_terms_check"):
            self.context.layout._set_preserve_terms_tooltip()
        if self.context.has("_refresh_preset_inspector"):
            self.context.settings._refresh_preset_inspector()
        if self.context.has("_transcript_view_combo"):
            self.context.layout._transcript_view_combo.setAccessibleName(self.context.settings._tr("show_transcript"))
        if self.context.has("_transcript_type_combo"):
            self.context.layout._transcript_type_combo.setAccessibleName(self.context.settings._tr("transcript_type"))
        if self.context.has("_telegram_channel_title"):
            self.context.layout._telegram_channel_title.setText(
                self.context.settings._tr("telegram_channel_browser_title").format(
                    url=self.context.lifecycle.workers.pending_telegram_url or ""
                )
            )
        if self.context.has("_sync_telegram_side_panel_toggle_button"):
            self.context.channel_browser._sync_telegram_side_panel_toggle_button()
        if self.context.has("_sync_panel_visibility_buttons"):
            self.context.media._sync_panel_visibility_buttons()
        self.context.settings._retranslate_inline_option_combos()
        self.context.settings._sync_api_key_statuses()

    def _refresh_language_pack_combos(self) -> None:
        language = self.context.settings._selected_gui_language()
        dropdown_combos = (
            (self.context.layout._aspect_combo, _dropdown_options("video_aspects", language)),
            (self.context.layout._playback_quality_combo, _dropdown_options("playback_video_qualities", language)),
            (self.context.layout._audio_source_combo, _dropdown_options("audio_sources", language)),
            (self.context.layout._performance_preset_combo, _dropdown_options("performance_presets", language)),
            (self.context.layout._export_video_quality_combo, _dropdown_options("video_qualities", language)),
            (self.context.layout._translation_device_combo, _dropdown_options("translation_devices", language)),
            (self.context.layout._whisper_device_combo, _dropdown_options("whisper_devices", language)),
            (self.context.layout._whisper_compute_combo, _dropdown_options("whisper_compute_types", language)),
            (self.context.layout._vieneu_runtime_combo, _dropdown_options("vieneu_runtimes", language)),
            (self.context.layout._vieneu_device_combo, _dropdown_options("vieneu_devices", language)),
            (self.context.layout._vieneu_backend_combo, _dropdown_options("vieneu_backends", language)),
            (self.context.layout._capture_backend_combo, _dropdown_options("capture_backends", language)),
            (self.context.layout._overlap_policy_combo, _dropdown_options("dubbing_overlap_policies", language)),
            (
                self.context.layout._transcript_cleanup_mode_combo,
                _dropdown_options("transcript_cleanup_modes", language),
            ),
            (
                self.context.layout._transcript_cleanup_provider_combo,
                _dropdown_options("transcript_cleanup_providers", language),
            ),
            (self.context.layout._transcript_view_combo, _dropdown_options("transcript_views", language)),
            (self.context.layout._transcript_type_combo, _dropdown_options("transcript_types", language)),
        )
        for combo, options in dropdown_combos:
            self.context.settings._replace_combo_options(combo, options)
        self.context.settings._sync_transcript_cleanup_controls()
        self.context.settings._replace_combo_options(
            self.context.layout._source_language_combo,
            [
                (option.name, option.id)
                for option in available_language_options(include_auto=True, language_id=language)
            ],
        )
        self.context.settings._replace_combo_options(
            self.context.layout._target_language_combo,
            [
                (option.name, option.id)
                for option in available_language_options(include_auto=False, language_id=language)
            ],
        )
        self.context.settings._refresh_translation_provider_options()
        self.context.settings._refresh_translation_models()
        self.context.settings._retranslate_inline_option_combos()

    def _retranslate_inline_option_combos(self) -> None:
        if self.context.has("_subtitle_mode_combo"):
            self.context.settings._set_combo_item_text(
                self.context.layout._subtitle_mode_combo, "source", self.context.settings._tr("source")
            )
            self.context.settings._set_combo_item_text(
                self.context.layout._subtitle_mode_combo, "target", self.context.settings._tr("target")
            )
        if self.context.has("_subtitle_size_combo"):
            for value, key in ((18, "small"), (24, "medium"), (32, "large"), (40, "very_large")):
                self.context.settings._set_combo_item_text(
                    self.context.layout._subtitle_size_combo, value, self.context.settings._tr(key)
                )
        if self.context.has("_subtitle_color_combo"):
            for value, key in (
                ("#000000", "black"),
                ("#ffffff", "white"),
                ("#ffd54a", "yellow"),
                ("#66d9ff", "blue"),
                ("#7ee787", "green"),
                ("#ff8bd1", "pink"),
            ):
                self.context.settings._set_combo_item_text(
                    self.context.layout._subtitle_color_combo, value, self.context.settings._tr(key)
                )
        if self.context.has("_subtitle_background_combo"):
            for value, key in (
                ("rgba(0, 0, 0, 0)", "transparent"),
                ("rgba(0, 0, 0, 160)", "black"),
                ("rgba(255, 255, 255, 190)", "white"),
                ("rgba(255, 213, 74, 180)", "yellow"),
                ("rgba(102, 217, 255, 170)", "blue"),
                ("rgba(126, 231, 135, 170)", "green"),
                ("rgba(255, 139, 209, 170)", "pink"),
            ):
                self.context.settings._set_combo_item_text(
                    self.context.layout._subtitle_background_combo, value, self.context.settings._tr(key)
                )
        if self.context.has("_source_filter_mode_combo"):
            for value, key in (("ai", "source_filter_mode_ai"),):
                self.context.settings._set_combo_item_text(
                    self.context.layout._source_filter_mode_combo, value, self.context.settings._tr(key)
                )
        if self.context.has("_speaker_gender_provider_combo"):
            self.context.settings._set_combo_item_text(
                self.context.layout._speaker_gender_provider_combo,
                "local",
                self.context.settings._tr("speaker_gender_provider_local"),
            )
        if self.context.has("_telegram_channel_filter_combo"):
            for value, key in (
                ("all", "telegram_filter_all"),
                ("video", "telegram_filter_video"),
                ("photo", "telegram_filter_photo"),
                ("document", "telegram_filter_document"),
                ("audio", "telegram_filter_audio"),
                ("text", "telegram_filter_text"),
                ("blacklist", "telegram_filter_blacklist"),
            ):
                self.context.settings._set_combo_item_text(
                    self.context.layout._telegram_channel_filter_combo, value, self.context.settings._tr(key)
                )
        if self.context.has("_source_filter_model_combo"):
            self.context.settings._set_combo_item_text(
                self.context.layout._source_filter_model_combo,
                "htdemucs",
                self.context.settings._tr("source_filter_model_htdemucs"),
            )
            self.context.settings._set_combo_item_text(
                self.context.layout._source_filter_model_combo,
                "htdemucs_ft",
                self.context.settings._tr("source_filter_model_htdemucs_ft"),
            )
            self.context.settings._set_combo_item_text(
                self.context.layout._source_filter_model_combo,
                "htdemucs_6s",
                self.context.settings._tr("source_filter_model_htdemucs_6s"),
            )
            self.context.settings._set_combo_item_text(
                self.context.layout._source_filter_model_combo,
                "mdx_extra",
                self.context.settings._tr("source_filter_model_mdx"),
            )
        if self.context.has("_auto_voice_gender_mode_combo"):
            for value, key in (("ai", "voice_gender_mode_ai"),):
                self.context.settings._set_combo_item_text(
                    self.context.layout._auto_voice_gender_mode_combo, value, self.context.settings._tr(key)
                )
        if self.context.has("_vieneu_core_combo"):
            self.context.settings._set_combo_item_text(
                self.context.layout._vieneu_core_combo, "local", self.context.settings._tr("vieneu_core_local")
            )
        for combo_name in ("_capture_system_device_combo", "_capture_microphone_device_combo"):
            if self.context.has(combo_name):
                self.context.settings._set_combo_item_text(
                    self.context.get(combo_name), "", self.context.settings._tr("auto")
                )

    @staticmethod
    def _set_combo_item_text(combo: QComboBox, data, text: str) -> None:
        index = combo.findData(data)
        if index >= 0:
            combo.setItemText(index, text)

    @staticmethod
    def _replace_combo_options(combo: QComboBox, options: list[tuple[str, str]], *, current=None) -> None:
        if current is None:
            current = combo.currentData()
        was_blocked = combo.blockSignals(True)
        combo.clear()
        for label, value in options:
            combo.addItem(_ui_label(label), value)
        index = combo.findData(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(was_blocked)

    def _translate_child_widgets(self, root: QWidget) -> None:
        for widget in root.findChildren(QWidget):
            tooltip_key = widget.property("i18n_tooltip_key")
            if tooltip_key:
                widget.setToolTip(self.context.settings._tr(str(tooltip_key)))
            key = widget.property("i18n_key")
            if not key:
                text_method = getattr(widget, "text", None)
                if callable(text_method):
                    current_text = text_method()
                    key = UI_TEXT_ALIASES.get(current_text) or UI_TEXT_ALIASES.get(_repair_mojibake(current_text))
                    if key:
                        widget.setProperty("i18n_key", key)
            if not key:
                if widget.toolTip() and not tooltip_key:
                    widget.setToolTip(_repair_mojibake(widget.toolTip()))
                continue
            text = self.context.settings._tr(str(key))
            if isinstance(widget, QPushButton | QCheckBox | QLabel):
                widget.setText(text)
            elif isinstance(widget, QLineEdit):
                widget.setPlaceholderText(text)
            if widget.toolTip() and not tooltip_key:
                widget.setToolTip(_repair_mojibake(widget.toolTip()))
        self.context.settings._repair_combo_item_fonts()

    def _repair_combo_item_fonts(self) -> None:
        for combo in self.context.window.findChildren(QComboBox):
            for row in range(combo.count()):
                repaired = _repair_mojibake(combo.itemText(row))
                if repaired != combo.itemText(row):
                    combo.setItemText(row, repaired)

    @staticmethod
    def _set_combo_data(combo: QComboBox, value) -> None:
        if value is None:
            return
        index = combo.findData(value)
        if index < 0 and combo.isEditable():
            combo.addItem(str(value), str(value))
            index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def _set_slider_value(slider: QSlider, value) -> None:
        if value is None:
            return
        try:
            slider.setValue(int(value))
        except (OverflowError, TypeError, ValueError):
            return

    @staticmethod
    def _scaled_preset_value(value, *, fallback: float, scale: int) -> int:
        try:
            number = float(fallback if value is None else value)
        except (OverflowError, TypeError, ValueError):
            number = float(fallback)
        if not math.isfinite(number):
            try:
                number = float(fallback)
            except (OverflowError, TypeError, ValueError):
                number = 0.0
        if not math.isfinite(number):
            number = 0.0
        return int(number * scale)

    @staticmethod
    def _set_checkbox(checkbox: QCheckBox, value) -> None:
        if value is not None:
            checkbox.setChecked(bool(value))

    @staticmethod
    def _set_line_edit_text(line_edit: QLineEdit, value) -> None:
        if value is not None:
            line_edit.setText(str(value))

    def _set_vieneu_model(self, model_id) -> None:
        if not model_id:
            return
        wanted = str(model_id)
        for row in range(self.context.layout._vieneu_model_combo.count()):
            data = self.context.layout._vieneu_model_combo.itemData(row) or {}
            if isinstance(data, dict) and data.get("id") == wanted:
                self.context.layout._vieneu_model_combo.setCurrentIndex(row)
                return

    def _save_settings(self) -> None:
        self.context.settings._provider_secret_controller().save_all(
            ("asr", "ocr", "translation", "tts", "cleanup", "speaker_gender")
        )
        self.context.config = self.context.settings._current_runtime_config()
        save_app_config(self.context.config)
