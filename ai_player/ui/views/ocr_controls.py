from __future__ import annotations

from ai_player.ui.features import layout as layout_types


def build(context):
    context.layout._transcript_cleanup_api_base_edit = layout_types.QLineEdit(
        context.config.transcript_cleanup_api_base
    )
    context.layout._transcript_cleanup_api_base_edit.setPlaceholderText(
        context.settings._tr("cleanup_api_base_placeholder")
    )
    context.layout._transcript_cleanup_api_key_edit = layout_types.QLineEdit(context.config.transcript_cleanup_api_key)
    context.layout._transcript_cleanup_api_key_edit.setPlaceholderText(
        context.settings._tr("cleanup_api_key_placeholder")
    )
    context.layout._transcript_cleanup_api_key_edit.setEchoMode(layout_types.QLineEdit.EchoMode.Password)
    context.layout._transcript_cleanup_api_key_status = context.ui._api_key_status_label()
    context.layout._cleanup_timeout_slider, context.layout._cleanup_timeout_value = context.ui._labeled_slider(
        minimum=1,
        maximum=120,
        step=1,
        value=int(context.config.transcript_cleanup_timeout_seconds),
        formatter=lambda value: f"{value} s",
    )
    context.layout._transcript_cleanup_mode_combo.currentIndexChanged.connect(
        context.settings._sync_transcript_cleanup_controls
    )
    context.layout._transcript_cleanup_provider_combo.currentIndexChanged.connect(
        context.settings._sync_transcript_cleanup_controls
    )
    context.layout._vieneu_temperature_slider, context.layout._vieneu_temperature_value = context.ui._labeled_slider(
        minimum=0,
        maximum=100,
        step=5,
        value=int(context.config.vieneu_tts_temperature * 100),
        formatter=lambda value: f"{value / 100:.2f}",
    )
    context.layout._vieneu_max_chars_slider, context.layout._vieneu_max_chars_value = context.ui._labeled_slider(
        minimum=80,
        maximum=320,
        step=20,
        value=context.config.vieneu_tts_max_chars_chunk,
        formatter=lambda value: f"{value}",
    )
    context.layout._runtime_warmup_enabled_check = layout_types.QCheckBox(
        context.settings._tr("runtime_warmup_enabled")
    )
    context.layout._runtime_warmup_enabled_check.setProperty("i18n_key", "runtime_warmup_enabled")
    context.layout._runtime_warmup_enabled_check.setChecked(context.config.runtime_warmup_enabled)
    context.layout._runtime_warmup_whisper_check = layout_types.QCheckBox(
        context.settings._tr("runtime_warmup_whisper")
    )
    context.layout._runtime_warmup_whisper_check.setProperty("i18n_key", "runtime_warmup_whisper")
    context.layout._runtime_warmup_whisper_check.setChecked(context.config.runtime_warmup_whisper)
    context.layout._runtime_warmup_translation_check = layout_types.QCheckBox(
        context.settings._tr("runtime_warmup_translation")
    )
    context.layout._runtime_warmup_translation_check.setProperty("i18n_key", "runtime_warmup_translation")
    context.layout._runtime_warmup_translation_check.setChecked(context.config.runtime_warmup_translation)
    context.layout._runtime_warmup_tts_check = layout_types.QCheckBox(context.settings._tr("runtime_warmup_tts"))
    context.layout._runtime_warmup_tts_check.setProperty("i18n_key", "runtime_warmup_tts")
    context.layout._runtime_warmup_tts_check.setChecked(context.config.runtime_warmup_tts)

    context.layout._ocr_fps_slider, context.layout._ocr_fps_value = context.ui._labeled_slider(
        minimum=2,
        maximum=100,
        step=1,
        value=int(context.config.ocr_fps * 10),
        formatter=lambda value: f"{value / 10:.1f}",
    )
    context.layout._ocr_crop_top_slider, context.layout._ocr_crop_top_value = context.ui._labeled_slider(
        minimum=0,
        maximum=95,
        step=1,
        value=int(context.config.ocr_crop_top_ratio * 100),
        formatter=lambda value: f"{value} %",
    )
    context.layout._ocr_crop_height_slider, context.layout._ocr_crop_height_value = context.ui._labeled_slider(
        minimum=5,
        maximum=100,
        step=1,
        value=int(context.config.ocr_crop_height_ratio * 100),
        formatter=lambda value: f"{value} %",
    )
    context.layout._ocr_scale_slider, context.layout._ocr_scale_value = context.ui._labeled_slider(
        minimum=100,
        maximum=400,
        step=25,
        value=int(context.config.ocr_scale * 100),
        formatter=lambda value: f"{value / 100:.2f}x",
    )
    context.layout._ocr_psm_slider, context.layout._ocr_psm_value = context.ui._labeled_slider(
        minimum=3,
        maximum=13,
        step=1,
        value=int(context.config.ocr_psm),
        formatter=lambda value: f"{value}",
    )
    context.layout._ocr_threshold_check = layout_types.QCheckBox(context.settings._tr("ocr_threshold"))
    context.layout._ocr_threshold_check.setProperty("i18n_key", "ocr_threshold")
    context.layout._ocr_threshold_check.setChecked(context.config.ocr_threshold)
    context.layout._ocr_min_confidence_slider, context.layout._ocr_min_confidence_value = context.ui._labeled_slider(
        minimum=0,
        maximum=100,
        step=5,
        value=int(context.config.ocr_min_confidence),
        formatter=lambda value: f"{value} %",
    )
    context.layout._ocr_merge_similarity_slider, context.layout._ocr_merge_similarity_value = (
        context.ui._labeled_slider(
            minimum=0,
            maximum=100,
            step=1,
            value=int(context.config.ocr_merge_similarity * 100),
            formatter=lambda value: f"{value} %",
        )
    )
    context.layout._ocr_timeout_slider, context.layout._ocr_timeout_value = context.ui._labeled_slider(
        minimum=3,
        maximum=180,
        step=1,
        value=int(context.config.ocr_timeout_seconds),
        formatter=lambda value: f"{value} s",
    )

    context.layout._vieneu_core_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._vieneu_core_combo)
    context.layout._vieneu_core_combo.addItem(context.settings._tr("vieneu_core_local"), "local")
    context.layout._vieneu_core_combo.setCurrentIndex(0)
    context.layout._vieneu_python_edit = layout_types.QLineEdit(context.config.vieneu_tts_python)
    layout_types.build_provider_preview_panel(context)
