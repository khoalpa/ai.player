from __future__ import annotations

import math
from dataclasses import replace

from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel, QLineEdit, QPushButton, QSlider, QWidget

from ai_player.core.config import DEFAULT_PERFORMANCE_PRESET, AppConfig, read_preserved_source_terms_file
from ai_player.core.runtime_catalog import available_language_options, available_translation_provider_options
from ai_player.core.settings_store import save_app_config
from ai_player.services.audio_timeline import normalize_overlap_policy
from ai_player.services.source_voice_filter import (
    normalize_source_voice_filter_mode,
    normalize_source_voice_filter_model,
)
from ai_player.services.speaker_voice_selector import normalize_voice_gender_mode
from ai_player.services.translation import available_translation_models, is_ctranslate2_model_path
from ai_player.services.tts import available_vieneu_models, available_voices, voice_gender
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


class PlayerSettingsMixin:
    def _refresh_tts_options(self, *_args) -> None:
        provider = self._selected_tts_provider()
        is_vieneu = provider == "vieneu"
        self._tts_mode_label.setVisible(is_vieneu)
        self._vieneu_mode_combo.setVisible(is_vieneu)
        self._tts_model_label.setVisible(is_vieneu)
        self._vieneu_model_combo.setVisible(is_vieneu)
        self._refresh_vieneu_models()
        self._refresh_tts_voices()

    def _refresh_vieneu_models(self, *_args) -> None:
        previous_model = self._selected_vieneu_model() or self._config.vieneu_tts_model_name
        self._vieneu_model_combo.clear()

        for model in available_vieneu_models(self._selected_vieneu_model_mode(), self._config):
            self._vieneu_model_combo.addItem(
                model.name,
                {"id": model.id, "offline": model.offline},
            )

        index = self._vieneu_model_combo.findData(
            {"id": previous_model, "offline": self._selected_vieneu_model_offline()}
        )
        if index < 0:
            for row in range(self._vieneu_model_combo.count()):
                data = self._vieneu_model_combo.itemData(row) or {}
                if data.get("id") == previous_model:
                    index = row
                    break
        self._vieneu_model_combo.setCurrentIndex(max(0, index))
        self._refresh_tts_voices()

    def _refresh_tts_voices(self, *_args) -> None:
        provider = self._selected_tts_provider()
        previous_voice = self._tts_voice_combo.currentData() or self._config.tts_voice
        previous_male_voice = self._tts_male_voice_combo.currentData() or self._config.tts_male_voice
        previous_female_voice = self._tts_female_voice_combo.currentData() or self._config.tts_female_voice
        self._tts_voice_combo.clear()
        self._tts_male_voice_combo.clear()
        self._tts_female_voice_combo.clear()

        voices = available_voices(provider, self._current_tts_config())
        for voice in voices:
            self._tts_voice_combo.addItem(voice.name, voice.id)

        preferred_voice = previous_voice
        if provider != self._config.tts_provider:
            preferred_voice = voices[0].id if voices else ""
        index = self._tts_voice_combo.findData(preferred_voice)
        self._tts_voice_combo.setCurrentIndex(max(0, index))
        self._populate_gender_voice_combo(
            self._tts_male_voice_combo,
            voices,
            "male",
            previous_male_voice,
        )
        self._populate_gender_voice_combo(
            self._tts_female_voice_combo,
            voices,
            "female",
            previous_female_voice,
        )
        self._sync_auto_voice_controls_enabled()

    def _sync_auto_voice_controls_enabled(self, *_args) -> None:
        enabled = self._auto_voice_gender_check.isChecked()
        for widget in (self._auto_voice_gender_mode_combo, self._tts_male_voice_combo, self._tts_female_voice_combo):
            widget.setEnabled(enabled)
        if hasattr(self, "_speaker_gender_model_combo"):
            self._speaker_gender_model_combo.setEnabled(enabled and self._selected_auto_voice_gender_mode() == "ai")

    def _sync_auto_match_controls_enabled(self, *_args) -> None:
        if not hasattr(self, "_auto_match_audio_check"):
            return
        enabled = self._auto_match_audio_check.isChecked()
        for widget in (
            self._speed_min_slider,
            self._speed_min_value,
            self._speed_max_slider,
            self._speed_max_value,
            self._volume_gain_min_slider,
            self._volume_gain_min_value,
            self._volume_gain_max_slider,
            self._volume_gain_max_value,
        ):
            widget.setEnabled(enabled)

    def _populate_gender_voice_combo(
        self,
        combo: QComboBox,
        voices,
        gender: str,
        preferred_voice: str,
    ) -> None:
        provider = self._selected_tts_provider()
        gendered_voices = [voice for voice in voices if voice_gender(provider, voice.id) == gender]
        if not gendered_voices:
            gendered_voices = list(voices)
        for voice in gendered_voices:
            combo.addItem(voice.name, voice.id)
        index = combo.findData(preferred_voice)
        combo.setCurrentIndex(max(0, index))

    def _selected_tts_provider(self) -> str:
        return self._tts_provider_combo.currentData() or self._config.tts_provider

    def _selected_gui_language(self) -> str:
        return self._ui_language_combo.currentData() or self._config.gui_language or "vi"

    def _selected_audio_source(self) -> str:
        return self._audio_source_combo.currentData() or self._config.audio_source

    def _selected_source_filter_mode(self) -> str:
        if hasattr(self, "_source_filter_mode_combo"):
            return normalize_source_voice_filter_mode(self._source_filter_mode_combo.currentData())
        return normalize_source_voice_filter_mode(self._config.original_audio_voice_filter_mode)

    def _selected_source_filter_model(self) -> str:
        if hasattr(self, "_source_filter_model_combo"):
            return normalize_source_voice_filter_model(self._source_filter_model_combo.currentData())
        return normalize_source_voice_filter_model(self._config.original_audio_voice_filter_model)

    def _sync_source_filter_controls(self, *_args) -> None:
        if not hasattr(self, "_source_filter_check"):
            return
        enabled = self._source_filter_check.isChecked()
        provider = self._selected_source_filter_mode()
        if hasattr(self, "_source_filter_mode_combo"):
            self._source_filter_mode_combo.setEnabled(enabled)
        if hasattr(self, "_source_filter_model_combo"):
            self._source_filter_model_combo.setEnabled(enabled and provider != "fast")

    def _selected_video_aspect_ratio(self) -> str:
        value = self._aspect_combo.currentData() if hasattr(self, "_aspect_combo") else ""
        return value if value in {"16:9", "9:16"} else "16:9"

    def _selected_playback_video_quality(self) -> str:
        if hasattr(self, "_playback_quality_combo"):
            return self._playback_quality_combo.currentData() or self._config.playback_video_quality
        return self._config.playback_video_quality

    def _selected_video_url_full_cache(self) -> bool:
        if hasattr(self, "_video_url_full_cache_check"):
            return self._video_url_full_cache_check.isChecked()
        return self._config.video_url_full_cache

    def _selected_source_language(self) -> str:
        return self._source_language_combo.currentData() or "auto"

    def _selected_target_language(self) -> str:
        return self._target_language_combo.currentData() or "vi"

    def _language_pair_changed(self, *_args) -> None:
        self._queue_save_settings()

    def _selected_asr_provider(self) -> str:
        if hasattr(self, "_asr_provider_combo"):
            return self._asr_provider_combo.currentData() or self._config.asr_provider
        return self._config.asr_provider

    def _selected_asr_model(self) -> str:
        if hasattr(self, "_asr_model_combo"):
            return self._combo_value(self._asr_model_combo) or self._config.whisper_model
        return self._config.whisper_model

    def _selected_ocr_provider(self) -> str:
        if hasattr(self, "_ocr_provider_combo"):
            return self._ocr_provider_combo.currentData() or self._config.ocr_provider
        return self._config.ocr_provider

    def _selected_ocr_model(self) -> str:
        if hasattr(self, "_ocr_model_combo"):
            return self._combo_value(self._ocr_model_combo) or self._config.ocr_model
        return self._config.ocr_model

    def _selected_translator_provider(self) -> str:
        provider = self._translator_combo.currentData() or "nllb"
        if provider == "none":
            return "none"
        if is_ctranslate2_model_path(self._selected_nllb_model()):
            return "nllb_ct2"
        return provider

    def _selected_nllb_model(self) -> str:
        value = self._combo_value(self._nllb_model_combo)
        provider = self._translator_combo.currentData()
        return value if value or provider == "none" else self._config.local_translation_model

    def _translator_changed(self, *_args) -> None:
        self._refresh_translation_models()
        self._queue_save_settings()

    def _refresh_translation_models(self, preferred_path: str | None = None) -> None:
        if not hasattr(self, "_nllb_model_combo"):
            return
        current = preferred_path
        if current is None:
            data = self._nllb_model_combo.currentData()
            current = None if data is None else str(data)
        provider = self._translator_combo.currentData()
        if provider == "none":
            current = ""
        elif provider == "nllb" and current and is_ctranslate2_model_path(current):
            current = ""
        elif provider == "nllb_ct2" and current and not is_ctranslate2_model_path(current):
            current = ""
        self._nllb_model_combo.blockSignals(True)
        try:
            self._nllb_model_combo.clear()
            for model in available_translation_models(provider):
                self._nllb_model_combo.addItem(model.name, model.path)
            index = self._nllb_model_combo.findData(current)
            if index < 0 and current:
                self._nllb_model_combo.addItem(current, current)
                index = self._nllb_model_combo.findData(current)
            self._nllb_model_combo.setCurrentIndex(max(0, index))
        finally:
            self._nllb_model_combo.blockSignals(False)
        self._sync_translation_model_combo_enabled()

    def _nllb_model_changed(self, *_args) -> None:
        if is_ctranslate2_model_path(self._selected_nllb_model()):
            self._set_combo_data(self._translator_combo, "nllb_ct2")
        self._sync_translation_model_combo_enabled()
        self._queue_save_settings()

    def _sync_translation_model_combo_enabled(self) -> None:
        provider = self._translator_combo.currentData()
        self._nllb_model_combo.setEnabled(provider != "none" and self._nllb_model_combo.count() > 0)

    def _selected_performance_preset(self) -> str:
        return self._performance_preset_combo.currentData() or DEFAULT_PERFORMANCE_PRESET

    def _selected_export_video_quality(self) -> str:
        return self._export_video_quality_combo.currentData() or self._config.export_video_quality

    def _selected_translation_device(self) -> str:
        return self._translation_device_combo.currentData() or self._config.local_translation_device

    def _selected_whisper_device(self) -> str:
        return self._whisper_device_combo.currentData() or self._config.whisper_device

    def _selected_whisper_compute(self) -> str:
        return self._whisper_compute_combo.currentData() or self._config.whisper_compute_type

    def _selected_tts_voice(self) -> str:
        return self._tts_voice_combo.currentData() or ""

    def _selected_tts_male_voice(self) -> str:
        return self._tts_male_voice_combo.currentData() or self._selected_tts_voice()

    def _selected_tts_female_voice(self) -> str:
        return self._tts_female_voice_combo.currentData() or self._selected_tts_voice()

    def _selected_auto_voice_gender_mode(self) -> str:
        if hasattr(self, "_auto_voice_gender_mode_combo"):
            return normalize_voice_gender_mode(self._auto_voice_gender_mode_combo.currentData())
        return normalize_voice_gender_mode(self._config.dubbing_auto_voice_gender_mode)

    def _selected_speaker_gender_model(self) -> str:
        if hasattr(self, "_speaker_gender_model_combo"):
            return self._combo_value(self._speaker_gender_model_combo)
        return self._config.speaker_gender_model

    def _selected_overlap_policy(self) -> str:
        if hasattr(self, "_overlap_policy_combo"):
            return normalize_overlap_policy(self._overlap_policy_combo.currentData())
        return normalize_overlap_policy(self._config.dubbing_overlap_policy)

    def _selected_vieneu_mode(self) -> str:
        return self._vieneu_mode_combo.currentData() or self._config.vieneu_tts_mode

    def _selected_vieneu_model_mode(self) -> str:
        return "remote" if self._selected_vieneu_core() == "remote" else self._selected_vieneu_mode()

    def _selected_vieneu_model_data(self) -> dict:
        data = self._vieneu_model_combo.currentData()
        return data if isinstance(data, dict) else {}

    def _selected_vieneu_model(self) -> str:
        return str(self._selected_vieneu_model_data().get("id") or self._config.vieneu_tts_model_name)

    def _selected_vieneu_model_offline(self) -> bool:
        if self._selected_vieneu_core() == "remote":
            return False
        data = self._selected_vieneu_model_data()
        if "offline" in data:
            return bool(data["offline"])
        return self._config.vieneu_tts_offline

    def _selected_vieneu_offline(self) -> bool:
        if self._selected_vieneu_core() == "remote":
            return False
        return self._selected_vieneu_model_offline() or self._vieneu_offline_check.isChecked()

    def _selected_vieneu_runtime(self) -> str:
        return self._vieneu_runtime_combo.currentData() or self._config.vieneu_tts_runtime

    def _selected_vieneu_device(self) -> str:
        return self._vieneu_device_combo.currentData() or self._config.vieneu_tts_device

    def _selected_vieneu_backend(self) -> str:
        return self._vieneu_backend_combo.currentData() or self._config.vieneu_tts_backend

    def _selected_vieneu_core(self) -> str:
        return self._vieneu_core_combo.currentData() or self._config.vieneu_tts_core

    def _selected_capture_backend(self) -> str:
        return self._capture_backend_combo.currentData() or self._config.capture_backend

    def _selected_capture_system_device(self) -> str:
        return self._combo_value(self._capture_system_device_combo)

    def _selected_capture_microphone_device(self) -> str:
        return self._combo_value(self._capture_microphone_device_combo)

    def _selected_transcript_cleanup_mode(self) -> str:
        return self._transcript_cleanup_mode_combo.currentData() or self._config.transcript_cleanup_mode

    def _selected_transcript_cleanup_provider(self) -> str:
        return self._transcript_cleanup_provider_combo.currentData() or self._config.transcript_cleanup_provider

    def _selected_transcript_cleanup_model(self) -> str:
        index = self._transcript_cleanup_model_combo.currentIndex()
        text = self._transcript_cleanup_model_combo.currentText().strip()
        if index >= 0 and text == self._transcript_cleanup_model_combo.itemText(index):
            data = self._transcript_cleanup_model_combo.itemData(index)
            if data:
                return str(data).strip()
        return text

    def _sync_transcript_cleanup_controls(self, *_args) -> None:
        if not hasattr(self, "_transcript_cleanup_mode_combo"):
            return
        enabled = self._selected_transcript_cleanup_mode() != "off"
        provider = self._selected_transcript_cleanup_provider()
        self._transcript_cleanup_provider_combo.setEnabled(enabled)
        self._transcript_cleanup_model_combo.setEnabled(enabled)
        self._transcript_cleanup_api_base_edit.setEnabled(enabled and provider in {"ollama", "openai"})
        self._transcript_cleanup_api_key_edit.setEnabled(enabled and provider == "openai")
        self._cleanup_timeout_slider.setEnabled(enabled and provider in {"ollama", "openai"})
        self._cleanup_timeout_value.setEnabled(enabled and provider in {"ollama", "openai"})

    def _sync_vieneu_advanced_controls(self, *_args) -> None:
        if not hasattr(self, "_vieneu_api_base_edit"):
            return
        remote = self._selected_vieneu_core() == "remote" or self._selected_vieneu_mode() == "remote"
        self._vieneu_api_base_edit.setEnabled(remote)
        self._vieneu_offline_check.setEnabled(not remote)

    def _vieneu_core_changed(self, *_args) -> None:
        self._refresh_vieneu_models()
        self._sync_vieneu_advanced_controls()
        self._queue_save_settings()

    @staticmethod
    def _combo_value(combo: QComboBox) -> str:
        text = combo.currentText().strip()
        data = combo.currentData()
        if combo.currentIndex() >= 0 and text == combo.itemText(combo.currentIndex()):
            return "" if data is None else str(data).strip()
        if text and text not in {"Auto", "Tự động"}:
            return text
        return "" if data is None else str(data).strip()

    def _current_runtime_config(self) -> AppConfig:
        preserved_terms = read_preserved_source_terms_file()
        config = replace(
            self._config,
            gui_language=self._selected_gui_language(),
            video_aspect_ratio=self._selected_video_aspect_ratio(),
            playback_video_quality=self._selected_playback_video_quality(),
            video_url_full_cache=self._selected_video_url_full_cache(),
            audio_source=self._selected_audio_source(),
            capture_backend=self._selected_capture_backend(),
            capture_system_device=self._selected_capture_system_device(),
            capture_microphone_device=self._selected_capture_microphone_device(),
            transcript_cleanup_mode=self._selected_transcript_cleanup_mode(),
            transcript_cleanup_provider=self._selected_transcript_cleanup_provider(),
            transcript_cleanup_model=self._selected_transcript_cleanup_model(),
            transcript_cleanup_api_base=self._transcript_cleanup_api_base_edit.text().strip(),
            transcript_cleanup_api_key=self._transcript_cleanup_api_key_edit.text().strip(),
            transcript_cleanup_timeout_seconds=float(self._cleanup_timeout_slider.value()),
            transcript_path=self._transcript_path_edit.text().strip(),
            asr_provider=self._selected_asr_provider(),
            whisper_model=self._selected_asr_model(),
            performance_preset=self._selected_performance_preset(),
            export_video_quality=self._selected_export_video_quality(),
            whisper_device=self._selected_whisper_device(),
            whisper_offline=self._whisper_offline_check.isChecked(),
            whisper_compute_type=self._selected_whisper_compute(),
            whisper_beam_size=int(self._whisper_beam_slider.value()),
            whisper_vad_filter=self._whisper_vad_check.isChecked(),
            ocr_provider=self._selected_ocr_provider(),
            ocr_model=self._selected_ocr_model(),
            ocr_fps=float(self._ocr_fps_slider.value() / 10),
            ocr_crop_top_ratio=float(self._ocr_crop_top_slider.value() / 100),
            ocr_crop_height_ratio=float(self._ocr_crop_height_slider.value() / 100),
            ocr_scale=float(self._ocr_scale_slider.value() / 100),
            ocr_psm=int(self._ocr_psm_slider.value()),
            ocr_threshold=self._ocr_threshold_check.isChecked(),
            ocr_min_confidence=float(self._ocr_min_confidence_slider.value()),
            ocr_merge_similarity=float(self._ocr_merge_similarity_slider.value() / 100),
            local_translation_device=self._selected_translation_device(),
            local_translation_model=self._selected_nllb_model(),
            local_translation_offline=self._translation_offline_check.isChecked(),
            preserve_source_terms=self._preserve_terms_check.isChecked(),
            preserved_source_terms=preserved_terms,
            preserve_english_terms=self._preserve_terms_check.isChecked(),
            preserved_english_terms=preserved_terms,
            translation_max_tokens=int(self._translation_max_tokens_slider.value()),
            translation_num_beams=int(self._translation_beams_slider.value()),
            segment_seconds=int(self._segment_seconds_slider.value()),
            dubbing_start_delay_seconds=float(self._start_delay_slider.value()),
            dubbing_prebuffer_segments=int(self._prebuffer_segments_slider.value()),
            dubbing_lookahead_segments=int(self._lookahead_segments_slider.value()),
            dubbing_min_ready_ahead_seconds=float(self._dubbing_buffer_slider.value()),
            dubbing_voice_volume=int(self._dub_volume_slider.value()),
            dubbing_speed_percent=int(self._dub_speed_slider.value()),
            dubbing_auto_match_audio=self._auto_match_audio_check.isChecked(),
            dubbing_overlap_policy=self._selected_overlap_policy(),
            dubbing_auto_voice_gender=self._auto_voice_gender_check.isChecked(),
            dubbing_auto_voice_gender_mode=self._selected_auto_voice_gender_mode(),
            speaker_gender_model=self._selected_speaker_gender_model(),
            dubbing_speed_min=float(self._speed_min_slider.value() / 100),
            dubbing_speed_max=float(self._speed_max_slider.value() / 100),
            dubbing_volume_gain_min_db=float(self._volume_gain_min_slider.value()),
            dubbing_volume_gain_max_db=float(self._volume_gain_max_slider.value()),
            original_audio_volume=int(self._volume_slider.value()),
            original_audio_voice_filter=self._source_filter_check.isChecked(),
            original_audio_voice_filter_mode=self._selected_source_filter_mode(),
            original_audio_voice_filter_model=self._selected_source_filter_model(),
            original_audio_playback_delay_seconds=int(self._video_delay_slider.value()),
            dubbing_enabled_by_default=self._dub_button.isChecked(),
            source_language=self._selected_source_language(),
            target_language=self._selected_target_language(),
            translator_provider=self._selected_translator_provider(),
            tts_provider=self._selected_tts_provider(),
            tts_voice=self._selected_tts_voice(),
            tts_male_voice=self._selected_tts_male_voice(),
            tts_female_voice=self._selected_tts_female_voice(),
            runtime_warmup_enabled=self._runtime_warmup_enabled_check.isChecked(),
            runtime_warmup_whisper=self._runtime_warmup_whisper_check.isChecked(),
            runtime_warmup_translation=self._runtime_warmup_translation_check.isChecked(),
            runtime_warmup_tts=self._runtime_warmup_tts_check.isChecked(),
            vieneu_tts_path=self._vieneu_path_edit.text().strip(),
            vieneu_tts_runtime=self._selected_vieneu_runtime(),
            vieneu_tts_python=self._vieneu_python_edit.text().strip(),
            vieneu_tts_core=self._selected_vieneu_core(),
            vieneu_tts_mode=self._selected_vieneu_mode(),
            vieneu_tts_api_base=self._vieneu_api_base_edit.text().strip(),
            vieneu_tts_model_name=self._selected_vieneu_model(),
            vieneu_tts_decoder_path=self._vieneu_decoder_path_edit.text().strip(),
            vieneu_tts_encoder_path=self._vieneu_encoder_path_edit.text().strip(),
            vieneu_tts_standard_codec_path=self._vieneu_standard_codec_path_edit.text().strip(),
            vieneu_tts_offline=self._selected_vieneu_offline(),
            vieneu_tts_device=self._selected_vieneu_device(),
            vieneu_tts_backend=self._selected_vieneu_backend(),
            vieneu_tts_temperature=float(self._vieneu_temperature_slider.value() / 100),
            vieneu_tts_max_chars_chunk=int(self._vieneu_max_chars_slider.value()),
        )
        return config

    def _current_tts_config(self) -> AppConfig:
        return self._current_runtime_config()

    def _apply_selected_performance_preset(self, *_args) -> None:
        preset_id = self._selected_performance_preset()
        preset = PERFORMANCE_PRESETS.get(preset_id)
        if not preset:
            return

        self._set_combo_data(self._audio_source_combo, preset.get("audio_source"))
        self._set_combo_data(self._source_language_combo, preset.get("source_language"))
        self._set_combo_data(self._target_language_combo, preset.get("target_language"))
        self._set_combo_data(self._translator_combo, preset.get("translator_provider"))
        self._set_combo_data(self._nllb_model_combo, preset.get("local_translation_model"))
        self._set_combo_data(self._translation_device_combo, preset.get("local_translation_device"))
        self._set_checkbox(self._translation_offline_check, preset.get("local_translation_offline"))
        self._set_slider_value(self._translation_max_tokens_slider, preset.get("translation_max_tokens"))
        self._set_slider_value(self._translation_beams_slider, preset.get("translation_num_beams"))

        self._set_combo_data(self._tts_provider_combo, preset.get("tts_provider"))
        self._set_combo_data(self._vieneu_mode_combo, preset.get("vieneu_tts_mode"))
        self._refresh_vieneu_models()
        self._set_vieneu_model(preset.get("vieneu_tts_model_name"))
        self._refresh_tts_voices()
        self._set_combo_data(self._tts_voice_combo, preset.get("tts_voice"))
        self._set_combo_data(self._tts_male_voice_combo, preset.get("tts_male_voice"))
        self._set_combo_data(self._tts_female_voice_combo, preset.get("tts_female_voice"))
        self._set_combo_data(self._vieneu_runtime_combo, preset.get("vieneu_tts_runtime"))
        self._set_combo_data(self._vieneu_device_combo, preset.get("vieneu_tts_device"))
        self._set_combo_data(self._vieneu_backend_combo, preset.get("vieneu_tts_backend"))
        self._set_combo_data(self._vieneu_core_combo, preset.get("vieneu_tts_core"))
        self._set_line_edit_text(self._vieneu_decoder_path_edit, preset.get("vieneu_tts_decoder_path"))
        self._set_line_edit_text(self._vieneu_encoder_path_edit, preset.get("vieneu_tts_encoder_path"))
        self._set_line_edit_text(self._vieneu_standard_codec_path_edit, preset.get("vieneu_tts_standard_codec_path"))
        self._set_checkbox(self._vieneu_offline_check, preset.get("vieneu_tts_offline"))
        self._set_slider_value(
            self._vieneu_temperature_slider,
            self._scaled_preset_value(
                preset.get("vieneu_tts_temperature"),
                fallback=self._config.vieneu_tts_temperature,
                scale=100,
            ),
        )
        self._set_slider_value(self._vieneu_max_chars_slider, preset.get("vieneu_tts_max_chars_chunk"))

        self._set_combo_data(self._whisper_device_combo, preset.get("whisper_device"))
        self._set_combo_data(self._asr_provider_combo, preset.get("asr_provider"))
        self._set_combo_data(self._asr_model_combo, preset.get("whisper_model"))
        self._set_combo_data(self._ocr_provider_combo, preset.get("ocr_provider"))
        self._set_combo_data(self._ocr_model_combo, preset.get("ocr_model"))
        self._set_combo_data(self._whisper_compute_combo, preset.get("whisper_compute_type"))
        self._set_slider_value(self._whisper_beam_slider, preset.get("whisper_beam_size"))
        self._set_checkbox(self._whisper_vad_check, preset.get("whisper_vad_filter"))
        self._set_checkbox(self._whisper_offline_check, preset.get("whisper_offline"))
        whisper_model = preset.get("whisper_model")
        if whisper_model:
            self._config = replace(self._config, whisper_model=str(whisper_model))
        self._set_slider_value(self._segment_seconds_slider, preset.get("segment_seconds"))
        self._set_slider_value(self._start_delay_slider, preset.get("dubbing_start_delay_seconds"))
        self._set_slider_value(self._prebuffer_segments_slider, preset.get("dubbing_prebuffer_segments"))
        self._set_slider_value(
            self._dubbing_buffer_slider,
            preset.get("dubbing_min_ready_ahead_seconds"),
        )
        self._set_slider_value(
            self._lookahead_segments_slider,
            preset.get("dubbing_lookahead_segments"),
        )
        self._set_slider_value(self._dub_speed_slider, preset.get("dubbing_speed_percent"))
        self._set_checkbox(self._auto_voice_gender_check, preset.get("dubbing_auto_voice_gender"))
        self._set_combo_data(self._auto_voice_gender_mode_combo, preset.get("dubbing_auto_voice_gender_mode"))
        self._set_checkbox(self._auto_match_audio_check, preset.get("dubbing_auto_match_audio"))
        self._set_combo_data(self._overlap_policy_combo, preset.get("dubbing_overlap_policy"))
        self._set_slider_value(self._video_delay_slider, preset.get("original_audio_playback_delay_seconds"))
        self._set_checkbox(self._source_filter_check, preset.get("original_audio_voice_filter"))
        self._set_combo_data(self._source_filter_mode_combo, preset.get("original_audio_voice_filter_mode"))
        self._set_combo_data(self._export_video_quality_combo, preset.get("export_video_quality"))
        self._set_slider_value(
            self._speed_min_slider,
            self._scaled_preset_value(
                preset.get("dubbing_speed_min"),
                fallback=self._config.dubbing_speed_min,
                scale=100,
            ),
        )
        self._set_slider_value(
            self._speed_max_slider,
            self._scaled_preset_value(
                preset.get("dubbing_speed_max"),
                fallback=self._config.dubbing_speed_max,
                scale=100,
            ),
        )
        self._set_slider_value(self._volume_gain_min_slider, preset.get("dubbing_volume_gain_min_db"))
        self._set_slider_value(self._volume_gain_max_slider, preset.get("dubbing_volume_gain_max_db"))
        self._set_checkbox(self._runtime_warmup_tts_check, preset.get("runtime_warmup_tts"))
        self._sync_auto_voice_controls_enabled()
        self._sync_auto_match_controls_enabled()
        self._sync_audio_source_controls()
        self._sync_vieneu_advanced_controls()
        self._save_settings()
        self.statusBar().showMessage(self._tr("status_preset_applied"))

    def _connect_settings_autosave(self) -> None:
        combos = (
            self._ui_language_combo,
            self._performance_preset_combo,
            self._export_video_quality_combo,
            self._playback_quality_combo,
            self._audio_source_combo,
            self._source_filter_mode_combo,
            self._source_filter_model_combo,
            self._speaker_gender_model_combo,
            self._source_language_combo,
            self._target_language_combo,
            self._asr_provider_combo,
            self._asr_model_combo,
            self._ocr_provider_combo,
            self._ocr_model_combo,
            self._translator_combo,
            self._nllb_model_combo,
            self._translation_device_combo,
            self._tts_provider_combo,
            self._vieneu_mode_combo,
            self._vieneu_model_combo,
            self._tts_voice_combo,
            self._auto_voice_gender_mode_combo,
            self._overlap_policy_combo,
            self._tts_male_voice_combo,
            self._tts_female_voice_combo,
            self._whisper_device_combo,
            self._whisper_compute_combo,
            self._vieneu_runtime_combo,
            self._vieneu_device_combo,
            self._vieneu_backend_combo,
            self._vieneu_core_combo,
            self._capture_backend_combo,
            self._capture_system_device_combo,
            self._capture_microphone_device_combo,
            self._transcript_cleanup_mode_combo,
            self._transcript_cleanup_provider_combo,
            self._transcript_cleanup_model_combo,
        )
        for combo in combos:
            combo.currentIndexChanged.connect(self._queue_save_settings)
            if combo.isEditable():
                combo.lineEdit().editingFinished.connect(self._queue_save_settings)

        checks = (
            self._preserve_terms_check,
            self._runtime_warmup_enabled_check,
            self._runtime_warmup_whisper_check,
            self._runtime_warmup_translation_check,
            self._runtime_warmup_tts_check,
            self._whisper_vad_check,
            self._whisper_offline_check,
            self._translation_offline_check,
            self._vieneu_offline_check,
            self._auto_voice_gender_check,
            self._auto_match_audio_check,
            self._dub_button,
            self._source_filter_check,
            self._ocr_threshold_check,
            self._video_url_full_cache_check,
        )
        for checkbox in checks:
            checkbox.toggled.connect(self._queue_save_settings)
        self._auto_match_audio_check.toggled.connect(self._sync_auto_match_controls_enabled)

        sliders = (
            self._volume_slider,
            self._dub_volume_slider,
            self._translation_max_tokens_slider,
            self._translation_beams_slider,
            self._whisper_beam_slider,
            self._ocr_fps_slider,
            self._ocr_crop_top_slider,
            self._ocr_crop_height_slider,
            self._ocr_scale_slider,
            self._ocr_psm_slider,
            self._ocr_min_confidence_slider,
            self._ocr_merge_similarity_slider,
            self._cleanup_timeout_slider,
            self._dubbing_buffer_slider,
            self._dub_speed_slider,
            self._video_delay_slider,
            self._segment_seconds_slider,
            self._prebuffer_segments_slider,
            self._lookahead_segments_slider,
            self._start_delay_slider,
            self._speed_min_slider,
            self._speed_max_slider,
            self._volume_gain_min_slider,
            self._volume_gain_max_slider,
            self._vieneu_temperature_slider,
            self._vieneu_max_chars_slider,
        )
        for slider in sliders:
            slider.valueChanged.connect(self._queue_save_settings)

        self._transcript_cleanup_api_base_edit.textEdited.connect(self._queue_save_settings)
        self._transcript_cleanup_api_key_edit.textEdited.connect(self._queue_save_settings)
        for line_edit in (
            self._vieneu_path_edit,
            self._vieneu_python_edit,
            self._vieneu_api_base_edit,
            self._vieneu_decoder_path_edit,
            self._vieneu_encoder_path_edit,
            self._vieneu_standard_codec_path_edit,
        ):
            line_edit.textEdited.connect(self._queue_save_settings)
            line_edit.editingFinished.connect(self._queue_save_settings)
        self._vieneu_core_combo.currentIndexChanged.connect(self._vieneu_core_changed)
        self._vieneu_mode_combo.currentIndexChanged.connect(self._sync_vieneu_advanced_controls)

    def _queue_save_settings(self, *_args) -> None:
        self._settings_save_timer.start()

    def _gui_language_changed(self, *_args) -> None:
        self._refresh_language_pack_combos()
        self._retranslate_ui()
        self._queue_save_settings()

    def _ui_language(self) -> str:
        return self._selected_gui_language() if hasattr(self, "_ui_language_combo") else self._config.gui_language

    def _tr(self, key: str) -> str:
        language = self._ui_language()
        fallback = UI_TEXT.get("vi", {})
        return UI_TEXT.get(language, fallback).get(key, fallback.get(key, key))

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(self._tr("window_title"))
        self._translate_child_widgets(self)
        if not self._video_path:
            if hasattr(self, "_sync_media_browser_address"):
                self._sync_media_browser_address()
            else:
                self._source_label.setText(self._tr("source_empty"))
        if hasattr(self, "_settings_tabs"):
            self._settings_tabs.setTabText(0, self._tr("basic_tab"))
            self._settings_tabs.setTabText(1, self._tr("models_tab"))
            self._settings_tabs.setTabText(2, self._tr("offline_models_tab"))
            self._settings_tabs.setTabText(3, self._tr("advanced_tab"))
            self._settings_tabs.setTabText(4, self._tr("transcript_tab"))
            self._settings_tabs.setTabText(5, self._tr("runtime_tab"))
        if hasattr(self, "_offline_models_log"):
            self._offline_models_log.setPlaceholderText(self._tr("offline_models_log_placeholder"))
        if hasattr(self, "_document_view"):
            placeholder_key = "document_editor_placeholder" if self._document_editor_active else "document_placeholder"
            self._document_view.setPlaceholderText(self._tr(placeholder_key))
            self._set_control_tooltip(self._document_view, placeholder_key)
        if hasattr(self, "_transcript"):
            self._transcript.setPlaceholderText(self._tr("transcript_placeholder"))
        if hasattr(self, "_transcript_path_edit"):
            self._transcript_path_edit.setPlaceholderText(self._tr("transcript_file_placeholder"))
        if hasattr(self, "_preserve_terms_check"):
            self._set_preserve_terms_tooltip()
        if hasattr(self, "_transcript_view_combo"):
            self._transcript_view_combo.setAccessibleName(self._tr("show_transcript"))
        if hasattr(self, "_transcript_type_combo"):
            self._transcript_type_combo.setAccessibleName(self._tr("transcript_type"))
        if hasattr(self, "_telegram_channel_title"):
            self._telegram_channel_title.setText(
                self._tr("telegram_channel_browser_title").format(url=self._pending_telegram_url or "")
            )
        self._retranslate_inline_option_combos()

    def _refresh_language_pack_combos(self) -> None:
        language = self._selected_gui_language()
        dropdown_combos = (
            (self._aspect_combo, _dropdown_options("video_aspects", language)),
            (self._playback_quality_combo, _dropdown_options("playback_video_qualities", language)),
            (self._audio_source_combo, _dropdown_options("audio_sources", language)),
            (self._performance_preset_combo, _dropdown_options("performance_presets", language)),
            (self._export_video_quality_combo, _dropdown_options("video_qualities", language)),
            (self._translation_device_combo, _dropdown_options("translation_devices", language)),
            (self._whisper_device_combo, _dropdown_options("whisper_devices", language)),
            (self._whisper_compute_combo, _dropdown_options("whisper_compute_types", language)),
            (self._vieneu_runtime_combo, _dropdown_options("vieneu_runtimes", language)),
            (self._vieneu_device_combo, _dropdown_options("vieneu_devices", language)),
            (self._vieneu_backend_combo, _dropdown_options("vieneu_backends", language)),
            (self._capture_backend_combo, _dropdown_options("capture_backends", language)),
            (self._overlap_policy_combo, _dropdown_options("dubbing_overlap_policies", language)),
            (self._transcript_cleanup_mode_combo, _dropdown_options("transcript_cleanup_modes", language)),
            (self._transcript_cleanup_provider_combo, _dropdown_options("transcript_cleanup_providers", language)),
            (self._transcript_view_combo, _dropdown_options("transcript_views", language)),
            (self._transcript_type_combo, _dropdown_options("transcript_types", language)),
        )
        for combo, options in dropdown_combos:
            self._replace_combo_options(combo, options)
        self._sync_transcript_cleanup_controls()
        self._replace_combo_options(
            self._source_language_combo,
            [
                (option.name, option.id)
                for option in available_language_options(include_auto=True, language_id=language)
            ],
        )
        self._replace_combo_options(
            self._target_language_combo,
            [
                (option.name, option.id)
                for option in available_language_options(include_auto=False, language_id=language)
            ],
        )
        self._replace_combo_options(
            self._translator_combo,
            [(option.name, option.id) for option in available_translation_provider_options(language)],
        )
        self._refresh_translation_models()
        self._retranslate_inline_option_combos()

    def _retranslate_inline_option_combos(self) -> None:
        if hasattr(self, "_subtitle_mode_combo"):
            self._set_combo_item_text(self._subtitle_mode_combo, "source", self._tr("source"))
            self._set_combo_item_text(self._subtitle_mode_combo, "target", self._tr("target"))
        if hasattr(self, "_subtitle_size_combo"):
            for value, key in ((18, "small"), (24, "medium"), (32, "large"), (40, "very_large")):
                self._set_combo_item_text(self._subtitle_size_combo, value, self._tr(key))
        if hasattr(self, "_subtitle_color_combo"):
            for value, key in (
                ("#000000", "black"),
                ("#ffffff", "white"),
                ("#ffd54a", "yellow"),
                ("#66d9ff", "blue"),
                ("#7ee787", "green"),
                ("#ff8bd1", "pink"),
            ):
                self._set_combo_item_text(self._subtitle_color_combo, value, self._tr(key))
        if hasattr(self, "_subtitle_background_combo"):
            for value, key in (
                ("rgba(0, 0, 0, 0)", "transparent"),
                ("rgba(0, 0, 0, 160)", "black"),
                ("rgba(255, 255, 255, 190)", "white"),
                ("rgba(255, 213, 74, 180)", "yellow"),
                ("rgba(102, 217, 255, 170)", "blue"),
                ("rgba(126, 231, 135, 170)", "green"),
                ("rgba(255, 139, 209, 170)", "pink"),
            ):
                self._set_combo_item_text(self._subtitle_background_combo, value, self._tr(key))
        if hasattr(self, "_source_filter_mode_combo"):
            for value, key in (
                ("fast", "source_filter_mode_fast"),
                ("ai", "source_filter_mode_ai"),
            ):
                self._set_combo_item_text(self._source_filter_mode_combo, value, self._tr(key))
        if hasattr(self, "_telegram_channel_filter_combo"):
            for value, key in (
                ("all", "telegram_filter_all"),
                ("video", "telegram_filter_video"),
                ("photo", "telegram_filter_photo"),
                ("document", "telegram_filter_document"),
                ("audio", "telegram_filter_audio"),
                ("text", "telegram_filter_text"),
            ):
                self._set_combo_item_text(self._telegram_channel_filter_combo, value, self._tr(key))
        if hasattr(self, "_source_filter_model_combo"):
            self._set_combo_item_text(
                self._source_filter_model_combo,
                "htdemucs",
                self._tr("source_filter_model_htdemucs"),
            )
            self._set_combo_item_text(
                self._source_filter_model_combo,
                "htdemucs_ft",
                self._tr("source_filter_model_htdemucs_ft"),
            )
            self._set_combo_item_text(
                self._source_filter_model_combo,
                "htdemucs_6s",
                self._tr("source_filter_model_htdemucs_6s"),
            )
            self._set_combo_item_text(self._source_filter_model_combo, "mdx_extra", self._tr("source_filter_model_mdx"))
        if hasattr(self, "_auto_voice_gender_mode_combo"):
            for value, key in (
                ("stable", "voice_gender_mode_stable"),
                ("balanced", "voice_gender_mode_balanced"),
                ("sensitive", "voice_gender_mode_sensitive"),
                ("ai", "voice_gender_mode_ai"),
            ):
                self._set_combo_item_text(self._auto_voice_gender_mode_combo, value, self._tr(key))
        if hasattr(self, "_vieneu_core_combo"):
            for value, key in (
                ("local", "vieneu_core_local"),
                ("remote", "vieneu_core_remote"),
            ):
                self._set_combo_item_text(self._vieneu_core_combo, value, self._tr(key))
        for combo_name in ("_capture_system_device_combo", "_capture_microphone_device_combo"):
            if hasattr(self, combo_name):
                self._set_combo_item_text(getattr(self, combo_name), "", self._tr("auto"))

    @staticmethod
    def _set_combo_item_text(combo: QComboBox, data, text: str) -> None:
        index = combo.findData(data)
        if index >= 0:
            combo.setItemText(index, text)

    @staticmethod
    def _replace_combo_options(combo: QComboBox, options: list[tuple[str, str]]) -> None:
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
                widget.setToolTip(self._tr(str(tooltip_key)))
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
            text = self._tr(str(key))
            if isinstance(widget, QPushButton | QCheckBox | QLabel):
                widget.setText(text)
            elif isinstance(widget, QLineEdit):
                widget.setPlaceholderText(text)
            if widget.toolTip() and not tooltip_key:
                widget.setToolTip(_repair_mojibake(widget.toolTip()))
        self._repair_combo_item_fonts()

    def _repair_combo_item_fonts(self) -> None:
        for combo in self.findChildren(QComboBox):
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
        for row in range(self._vieneu_model_combo.count()):
            data = self._vieneu_model_combo.itemData(row) or {}
            if isinstance(data, dict) and data.get("id") == wanted:
                self._vieneu_model_combo.setCurrentIndex(row)
                return

    def _save_settings(self) -> None:
        self._config = self._current_runtime_config()
        save_app_config(self._config)
