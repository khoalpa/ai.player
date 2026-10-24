from __future__ import annotations

from ai_player.ui.features import layout as layout_types


def build(context):
    context.layout._asr_model_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._asr_model_combo)
    context.layout._asr_model_combo.setEditable(True)
    for model in layout_types.available_asr_models():
        context.layout._asr_model_combo.addItem(model.name, model.id)
    asr_model_index = context.layout._asr_model_combo.findData(context.config.whisper_model)
    if asr_model_index < 0 and context.config.whisper_model:
        context.layout._asr_model_combo.addItem(context.config.whisper_model, context.config.whisper_model)
        asr_model_index = context.layout._asr_model_combo.findData(context.config.whisper_model)
    context.layout._asr_model_combo.setCurrentIndex(max(0, asr_model_index))
    context.layout._asr_api_base_edit = layout_types.QLineEdit(context.config.asr_api_base)
    context.layout._asr_api_base_edit.setPlaceholderText(context.settings._tr("asr_api_base_placeholder"))
    context.layout._asr_language_hints_edit = layout_types.QLineEdit(context.config.asr_language_hints)
    context.layout._asr_language_hints_edit.setPlaceholderText(context.settings._tr("asr_language_hints_placeholder"))
    context.layout._asr_api_key_edit = layout_types.QLineEdit(context.config.asr_api_key)
    context.layout._asr_api_key_edit.setPlaceholderText(context.settings._tr("asr_api_key_placeholder"))
    context.layout._asr_api_key_edit.setEchoMode(layout_types.QLineEdit.EchoMode.Password)
    context.layout._asr_api_key_status = context.ui._api_key_status_label()

    context.layout._ocr_provider_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._ocr_provider_combo)
    for provider in layout_types.available_ocr_providers():
        context.layout._ocr_provider_combo.addItem(provider.name, provider.id)
    context.layout._ocr_provider_combo.setCurrentIndex(
        max(0, context.layout._ocr_provider_combo.findData(context.config.ocr_provider))
    )
    context.layout._ocr_model_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._ocr_model_combo)
    context.layout._ocr_model_combo.setEditable(True)
    for model in layout_types.available_ocr_models():
        context.layout._ocr_model_combo.addItem(model.name, model.id)
    ocr_model_index = context.layout._ocr_model_combo.findData(context.config.ocr_model)
    if ocr_model_index < 0 and context.config.ocr_model:
        context.layout._ocr_model_combo.addItem(context.config.ocr_model, context.config.ocr_model)
        ocr_model_index = context.layout._ocr_model_combo.findData(context.config.ocr_model)
    context.layout._ocr_model_combo.setCurrentIndex(max(0, ocr_model_index))
    context.layout._ocr_api_base_edit = layout_types.QLineEdit(context.config.ocr_api_base)
    context.layout._ocr_api_base_edit.setPlaceholderText(context.settings._tr("ocr_api_base_placeholder"))
    context.layout._ocr_api_key_edit = layout_types.QLineEdit(context.config.ocr_api_key)
    context.layout._ocr_api_key_edit.setPlaceholderText(context.settings._tr("ocr_api_key_placeholder"))
    context.layout._ocr_api_key_edit.setEchoMode(layout_types.QLineEdit.EchoMode.Password)
    context.layout._ocr_api_key_status = context.ui._api_key_status_label()
    context.layout._ocr_api_region_edit = layout_types.QLineEdit(context.config.ocr_api_region)
    context.layout._ocr_api_region_edit.setPlaceholderText(context.settings._tr("ocr_api_region_placeholder"))

    context.layout._translator_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._translator_combo)
    context.settings._refresh_translation_provider_options()
    context.layout._translator_combo.currentIndexChanged.connect(context.settings._translator_changed)
    context.layout._nllb_model_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._nllb_model_combo)
    context.layout._nllb_model_combo.setEditable(True)
    context.settings._refresh_translation_models(context.config.local_translation_model)
    context.layout._nllb_model_combo.currentIndexChanged.connect(context.settings._nllb_model_changed)
    context.layout._performance_preset_combo = context.ui._option_combo(
        layout_types._dropdown_options("performance_presets", context.config.gui_language),
        context.config.performance_preset,
    )
    context.layout._export_video_quality_combo = context.ui._option_combo(
        layout_types._dropdown_options("video_qualities", context.config.gui_language),
        context.config.export_video_quality,
    )
    context.layout._translation_device_combo = context.ui._option_combo(
        layout_types._dropdown_options("translation_devices", context.config.gui_language),
        context.config.local_translation_device,
    )
    context.layout._translator_api_base_edit = layout_types.QLineEdit(context.config.translator_api_base)
    context.layout._translator_api_base_edit.setPlaceholderText(context.settings._tr("translator_api_base_placeholder"))
    context.layout._translator_api_key_edit = layout_types.QLineEdit(context.config.translator_api_key)
    context.layout._translator_api_key_edit.setPlaceholderText(context.settings._tr("translator_api_key_placeholder"))
    context.layout._translator_api_key_edit.setEchoMode(layout_types.QLineEdit.EchoMode.Password)
    context.layout._translator_api_key_status = context.ui._api_key_status_label()
    context.layout._translator_api_region_edit = layout_types.QLineEdit(context.config.translator_api_region)
    context.layout._translator_api_region_edit.setPlaceholderText(
        context.settings._tr("translator_api_region_placeholder")
    )
    context.layout._preserve_terms_check = layout_types.QCheckBox(context.settings._tr("keep_terms"))
    context.layout._preserve_terms_check.setProperty("i18n_key", "keep_terms")
    context.layout._preserve_terms_check.setChecked(context.config.preserve_source_terms)
    context.layout._set_preserve_terms_tooltip()
    context.layout._preserved_terms_file_edit = layout_types.QLineEdit(context.config.preserved_source_terms_file)
    context.layout._preserved_terms_file_edit.setReadOnly(True)
    context.layout._whisper_offline_check = layout_types.QCheckBox(context.settings._tr("whisper_offline"))
    context.layout._whisper_offline_check.setProperty("i18n_key", "whisper_offline")
    context.layout._whisper_offline_check.setChecked(context.config.whisper_offline)
    context.layout._translation_offline_check = layout_types.QCheckBox(context.settings._tr("translator_offline"))
    context.layout._translation_offline_check.setProperty("i18n_key", "translator_offline")
    context.layout._translation_offline_check.setChecked(context.config.local_translation_offline)
    context.layout._vieneu_offline_check = layout_types.QCheckBox(context.settings._tr("vieneu_offline"))
    context.layout._vieneu_offline_check.setProperty("i18n_key", "vieneu_offline")
    context.layout._vieneu_offline_check.setChecked(context.config.vieneu_tts_offline)
    context.layout._translation_max_tokens_slider, context.layout._translation_max_tokens_value = (
        context.ui._labeled_slider(
            minimum=64,
            maximum=512,
            step=32,
            value=context.config.translation_max_tokens,
            formatter=lambda value: f"{value}",
        )
    )
    context.layout._translation_beams_slider, context.layout._translation_beams_value = context.ui._labeled_slider(
        minimum=1,
        maximum=6,
        step=1,
        value=context.config.translation_num_beams,
        formatter=lambda value: f"{value}",
    )

    context.layout._tts_provider_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._tts_provider_combo)
    context.settings._refresh_tts_provider_options()
    context.layout._tts_provider_combo.currentIndexChanged.connect(context.settings._refresh_tts_options)

    context.layout._tts_mode_label = context.ui._field_label("mode")
    context.layout._vieneu_mode_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._vieneu_mode_combo)
    for mode in layout_types.available_vieneu_modes():
        context.layout._vieneu_mode_combo.addItem(mode.name, mode.id)
    context.layout._vieneu_mode_combo.setCurrentIndex(
        max(0, context.layout._vieneu_mode_combo.findData(context.config.vieneu_tts_mode))
    )
    context.layout._vieneu_mode_combo.currentIndexChanged.connect(context.settings._refresh_vieneu_models)

    context.layout._tts_model_label = context.ui._field_label("model")
    context.layout._vieneu_model_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._vieneu_model_combo)
    context.layout._vieneu_model_combo.currentIndexChanged.connect(context.settings._refresh_tts_voices)

    context.layout._tts_voice_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._tts_voice_combo)
    context.layout._tts_voice_combo.setEditable(True)
    context.layout._tts_male_voice_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._tts_male_voice_combo)
    context.layout._tts_male_voice_combo.setEditable(True)
    context.layout._tts_female_voice_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._tts_female_voice_combo)
    context.layout._tts_female_voice_combo.setEditable(True)
    context.layout._tts_api_base_edit = layout_types.QLineEdit(context.config.tts_api_base)
    context.layout._tts_api_base_edit.setPlaceholderText(context.settings._tr("tts_api_base_placeholder"))
    context.layout._tts_api_key_edit = layout_types.QLineEdit(context.config.tts_api_key)
    context.layout._tts_api_key_edit.setPlaceholderText(context.settings._tr("tts_api_key_placeholder"))
    context.layout._tts_api_key_edit.setEchoMode(layout_types.QLineEdit.EchoMode.Password)
    context.layout._tts_api_key_status = context.ui._api_key_status_label()
    context.layout._tts_api_secret_edit = layout_types.QLineEdit(context.config.tts_api_secret)
    context.layout._tts_api_secret_edit.setPlaceholderText(context.settings._tr("tts_api_secret_placeholder"))
    context.layout._tts_api_secret_edit.setEchoMode(layout_types.QLineEdit.EchoMode.Password)
    context.layout._tts_api_secret_status = context.ui._api_key_status_label()
    context.layout._tts_api_region_edit = layout_types.QLineEdit(context.config.tts_api_region)
    context.layout._tts_api_region_edit.setPlaceholderText(context.settings._tr("tts_api_region_placeholder"))
    context.layout._tts_model_edit = layout_types.QLineEdit(context.config.tts_model)
    context.layout._tts_model_edit.setPlaceholderText(context.settings._tr("tts_model_placeholder"))
    context.layout._auto_voice_gender_check = layout_types.QCheckBox(context.settings._tr("auto_gender"))
    context.layout._auto_voice_gender_check.setProperty("i18n_key", "auto_gender")
    context.layout._auto_voice_gender_check.setChecked(context.config.dubbing_auto_voice_gender)
    context.layout._auto_voice_gender_check.toggled.connect(context.settings._sync_auto_voice_controls_enabled)
    context.layout._auto_voice_gender_mode_combo = layout_types.QComboBox()
    context.layout._auto_voice_gender_mode_combo.addItem(context.settings._tr("voice_gender_mode_ai"), "ai")
    context.layout._auto_voice_gender_mode_combo.setCurrentIndex(
        max(
            0,
            context.layout._auto_voice_gender_mode_combo.findData(
                layout_types.normalize_voice_gender_mode(context.config.dubbing_auto_voice_gender_mode)
            ),
        )
    )
    context.layout._auto_voice_gender_mode_combo.setToolTip(context.settings._tr("voice_gender_mode_tooltip"))
    context.layout._auto_voice_gender_mode_combo.setProperty("i18n_tooltip_key", "voice_gender_mode_tooltip")
    context.layout._auto_voice_gender_mode_combo.currentIndexChanged.connect(
        context.settings._sync_auto_voice_controls_enabled
    )
    context.layout._speaker_gender_model_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._speaker_gender_model_combo)
    context.layout._speaker_gender_model_combo.setEditable(True)
    for model in layout_types.available_speaker_gender_models():
        context.layout._speaker_gender_model_combo.addItem(model.name, model.id)
    speaker_gender_model_index = context.layout._speaker_gender_model_combo.findData(
        context.config.speaker_gender_model
    )
    if speaker_gender_model_index < 0 and context.config.speaker_gender_model:
        context.layout._speaker_gender_model_combo.addItem(
            context.config.speaker_gender_model,
            context.config.speaker_gender_model,
        )
        speaker_gender_model_index = context.layout._speaker_gender_model_combo.findData(
            context.config.speaker_gender_model
        )
    context.layout._speaker_gender_model_combo.setCurrentIndex(max(0, speaker_gender_model_index))
    context.layout._speaker_gender_model_combo.setToolTip(context.settings._tr("speaker_gender_model_tooltip"))
    context.layout._speaker_gender_model_combo.setProperty("i18n_tooltip_key", "speaker_gender_model_tooltip")
    context.layout._speaker_gender_provider_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._speaker_gender_provider_combo)
    context.layout._speaker_gender_provider_combo.addItem(
        context.settings._tr("speaker_gender_provider_local"), "local"
    )
    context.layout._speaker_gender_provider_combo.setCurrentIndex(
        max(
            0,
            context.layout._speaker_gender_provider_combo.findData(
                layout_types.normalize_speaker_gender_provider(context.config.speaker_gender_provider)
            ),
        )
    )
    context.layout._speaker_gender_api_base_edit = layout_types.QLineEdit(context.config.speaker_gender_api_base)
    context.layout._speaker_gender_api_base_edit.setPlaceholderText(
        context.settings._tr("speaker_gender_api_base_placeholder")
    )
    context.layout._speaker_gender_api_key_edit = layout_types.QLineEdit(context.config.speaker_gender_api_key)
    context.layout._speaker_gender_api_key_edit.setPlaceholderText(
        context.settings._tr("speaker_gender_api_key_placeholder")
    )
    context.layout._speaker_gender_api_key_edit.setEchoMode(layout_types.QLineEdit.EchoMode.Password)
    context.layout._speaker_gender_api_key_status = context.ui._api_key_status_label()
    context.layout._speaker_gender_timeout_slider, context.layout._speaker_gender_timeout_value = (
        context.ui._labeled_slider(
            minimum=3,
            maximum=120,
            step=1,
            value=int(context.config.speaker_gender_timeout_seconds),
            formatter=lambda value: f"{value} s",
        )
    )
    context.layout._auto_match_audio_check = layout_types.QCheckBox(context.settings._tr("auto_match"))
