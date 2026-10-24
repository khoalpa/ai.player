from __future__ import annotations

from dataclasses import dataclass

from ai_player.ui.features import layout as layout_types


@dataclass(frozen=True)
class SettingsSections:
    advanced_capture_grid: layout_types.QGridLayout
    advanced_match_grid: layout_types.QGridLayout
    advanced_playback_grid: layout_types.QGridLayout
    advanced_terms_grid: layout_types.QGridLayout
    advanced_timing_grid: layout_types.QGridLayout
    asr_grid: layout_types.QGridLayout
    basic_playback_grid: layout_types.QGridLayout
    basic_processing_grid: layout_types.QGridLayout
    basic_source_grid: layout_types.QGridLayout
    basic_voice_grid: layout_types.QGridLayout
    cleanup_grid: layout_types.QGridLayout
    ocr_grid: layout_types.QGridLayout
    translation_grid: layout_types.QGridLayout
    tts_advanced_grid: layout_types.QGridLayout
    tts_grid: layout_types.QGridLayout
    voice_ai_grid: layout_types.QGridLayout


def build(context) -> SettingsSections:
    preset_row = layout_types.QWidget()
    preset_layout = layout_types.QHBoxLayout(preset_row)
    preset_layout.setContentsMargins(0, 0, 0, 0)
    preset_layout.setSpacing(8)
    preset_layout.addWidget(context.ui._field_label("preset"))
    preset_layout.addWidget(context.layout._performance_preset_combo, 1)
    context.layout._preset_inspector = layout_types.QLabel("")
    context.layout._preset_inspector.setObjectName("presetInspector")
    context.layout._preset_inspector.setWordWrap(True)
    context.layout._preset_cards = {}
    context.layout._preset_cards_panel = context.layout._preset_cards_panel_widget()

    basic_source_grid = layout_types.QGridLayout()
    basic_source_grid.setHorizontalSpacing(8)
    basic_source_grid.setVerticalSpacing(7)
    basic_source_grid.addWidget(preset_row, 0, 0, 1, 2)
    basic_source_grid.addWidget(context.layout._preset_inspector, 1, 0, 1, 2)
    basic_source_grid.addWidget(context.layout._preset_cards_panel, 2, 0, 1, 2)
    basic_source_grid.addWidget(context.ui._audio_source_panel(), 3, 0, 1, 2)
    basic_source_grid.addWidget(context.ui._field_label("source_language"), 4, 0)
    basic_source_grid.addWidget(context.layout._source_language_combo, 4, 1)
    basic_source_grid.addWidget(context.ui._field_label("target_language"), 5, 0)
    basic_source_grid.addWidget(context.layout._target_language_combo, 5, 1)

    basic_voice_grid = layout_types.QGridLayout()
    basic_voice_grid.setHorizontalSpacing(8)
    basic_voice_grid.setVerticalSpacing(7)
    basic_voice_grid.addWidget(context.ui._field_label("voice_default"), 0, 0)
    basic_voice_grid.addWidget(context.layout._tts_voice_combo, 0, 1)
    basic_voice_grid.addWidget(context.layout._auto_voice_gender_check, 1, 0, 1, 2)
    basic_voice_grid.addWidget(context.ui._field_label("voice_gender_mode"), 2, 0)
    basic_voice_grid.addWidget(context.layout._auto_voice_gender_mode_combo, 2, 1)
    basic_voice_grid.addWidget(context.ui._field_label("male_voice"), 3, 0)
    basic_voice_grid.addWidget(context.layout._tts_male_voice_combo, 3, 1)
    basic_voice_grid.addWidget(context.ui._field_label("female_voice"), 4, 0)
    basic_voice_grid.addWidget(context.layout._tts_female_voice_combo, 4, 1)

    basic_playback_grid = layout_types.QGridLayout()
    basic_playback_grid.setHorizontalSpacing(8)
    basic_playback_grid.setVerticalSpacing(7)
    basic_playback_grid.addWidget(context.ui._field_label("buffer"), 0, 0)
    basic_playback_grid.addWidget(
        context.ui._slider_row(context.layout._dubbing_buffer_slider, context.layout._dubbing_buffer_value), 0, 1
    )
    basic_playback_grid.addWidget(context.ui._field_label("speed"), 1, 0)
    basic_playback_grid.addWidget(
        context.ui._slider_row(context.layout._dub_speed_slider, context.layout._dub_speed_value), 1, 1
    )
    basic_playback_grid.addWidget(context.ui._field_label("video_delay"), 2, 0)
    basic_playback_grid.addWidget(
        context.ui._slider_row(context.layout._video_delay_slider, context.layout._video_delay_value), 2, 1
    )

    basic_processing_grid = layout_types.QGridLayout()
    basic_processing_grid.setHorizontalSpacing(8)
    basic_processing_grid.setVerticalSpacing(7)
    basic_processing_grid.addWidget(context.layout._source_filter_check, 0, 0, 1, 2)
    basic_processing_grid.addWidget(context.ui._field_label("source_filter_provider"), 1, 0)
    basic_processing_grid.addWidget(context.layout._source_filter_mode_combo, 1, 1)
    basic_processing_grid.addWidget(context.ui._field_label("export_video_quality"), 2, 0)
    basic_processing_grid.addWidget(context.layout._export_video_quality_combo, 2, 1)
    basic_processing_grid.addWidget(context.layout._video_url_full_cache_check, 3, 0, 1, 2)
    basic_processing_grid.addWidget(context.ui._field_label("video_cache_dir"), 4, 0)
    video_cache_dir_row = layout_types.QWidget()
    video_cache_dir_layout = layout_types.QHBoxLayout(video_cache_dir_row)
    video_cache_dir_layout.setContentsMargins(0, 0, 0, 0)
    video_cache_dir_layout.setSpacing(6)
    video_cache_dir_layout.addWidget(context.layout._video_cache_dir_edit, 1)
    video_cache_dir_layout.addWidget(context.layout._video_cache_dir_button)
    video_cache_dir_layout.addWidget(context.layout._video_cache_dir_reset_button)
    basic_processing_grid.addWidget(video_cache_dir_row, 4, 1)

    advanced_terms_grid = layout_types.QGridLayout()
    advanced_terms_grid.setHorizontalSpacing(8)
    advanced_terms_grid.setVerticalSpacing(7)
    advanced_terms_grid.addWidget(context.layout._preserve_terms_check, 0, 0, 1, 2)
    advanced_terms_grid.addWidget(context.ui._field_label("preserved_terms"), 1, 0)
    advanced_terms_grid.addWidget(context.layout._preserved_terms_file_edit, 1, 1)

    advanced_timing_grid = layout_types.QGridLayout()
    advanced_timing_grid.setHorizontalSpacing(8)
    advanced_timing_grid.setVerticalSpacing(7)
    advanced_timing_grid.addWidget(context.ui._field_label("segment_length"), 0, 0)
    advanced_timing_grid.addWidget(
        context.ui._slider_row(context.layout._segment_seconds_slider, context.layout._segment_seconds_value), 0, 1
    )
    advanced_timing_grid.addWidget(context.ui._field_label("prebuffer_segments"), 1, 0)
    advanced_timing_grid.addWidget(
        context.ui._slider_row(context.layout._prebuffer_segments_slider, context.layout._prebuffer_segments_value),
        1,
        1,
    )
    advanced_timing_grid.addWidget(context.ui._field_label("lookahead_segments"), 2, 0)
    advanced_timing_grid.addWidget(
        context.ui._slider_row(context.layout._lookahead_segments_slider, context.layout._lookahead_segments_value),
        2,
        1,
    )

    advanced_match_grid = layout_types.QGridLayout()
    advanced_match_grid.setHorizontalSpacing(8)
    advanced_match_grid.setVerticalSpacing(7)
    advanced_match_grid.addWidget(context.layout._auto_match_audio_check, 0, 0, 1, 2)
    advanced_match_grid.addWidget(context.ui._field_label("speed_min"), 1, 0)
    advanced_match_grid.addWidget(
        context.ui._slider_row(context.layout._speed_min_slider, context.layout._speed_min_value), 1, 1
    )
    advanced_match_grid.addWidget(context.ui._field_label("speed_max"), 2, 0)
    advanced_match_grid.addWidget(
        context.ui._slider_row(context.layout._speed_max_slider, context.layout._speed_max_value), 2, 1
    )
    advanced_match_grid.addWidget(context.ui._field_label("gain_min"), 3, 0)
    advanced_match_grid.addWidget(
        context.ui._slider_row(context.layout._volume_gain_min_slider, context.layout._volume_gain_min_value), 3, 1
    )
    advanced_match_grid.addWidget(context.ui._field_label("gain_max"), 4, 0)
    advanced_match_grid.addWidget(
        context.ui._slider_row(context.layout._volume_gain_max_slider, context.layout._volume_gain_max_value), 4, 1
    )

    advanced_playback_grid = layout_types.QGridLayout()
    advanced_playback_grid.setHorizontalSpacing(8)
    advanced_playback_grid.setVerticalSpacing(7)
    advanced_playback_grid.addWidget(context.ui._field_label("overlap_policy"), 0, 0)
    advanced_playback_grid.addWidget(context.layout._overlap_policy_combo, 0, 1)
    advanced_playback_grid.addWidget(context.ui._field_label("start_delay"), 1, 0)
    advanced_playback_grid.addWidget(
        context.ui._slider_row(context.layout._start_delay_slider, context.layout._start_delay_value), 1, 1
    )

    advanced_capture_grid = layout_types.QGridLayout()
    advanced_capture_grid.setHorizontalSpacing(8)
    advanced_capture_grid.setVerticalSpacing(7)
    advanced_capture_grid.addWidget(context.ui._field_label("capture_backend"), 0, 0)
    advanced_capture_grid.addWidget(context.layout._capture_backend_combo, 0, 1)
    advanced_capture_grid.addWidget(context.ui._field_label("system_audio"), 1, 0)
    advanced_capture_grid.addWidget(context.layout._capture_system_device_combo, 1, 1)
    advanced_capture_grid.addWidget(context.ui._field_label("microphone"), 2, 0)
    advanced_capture_grid.addWidget(context.layout._capture_microphone_device_combo, 2, 1)

    asr_grid = layout_types.QGridLayout()
    asr_grid.setHorizontalSpacing(8)
    asr_grid.setVerticalSpacing(7)
    asr_grid.addWidget(context.ui._field_label("asr_provider"), 0, 0)
    asr_grid.addWidget(context.layout._asr_provider_combo, 0, 1)
    asr_grid.addWidget(context.ui._field_label("asr_model"), 1, 0)
    asr_grid.addWidget(context.layout._asr_model_combo, 1, 1)
    asr_grid.addWidget(context.ui._field_label("asr_api_base"), 2, 0)
    asr_grid.addWidget(context.layout._asr_api_base_edit, 2, 1)
    asr_grid.addWidget(context.ui._field_label("asr_language_hints"), 3, 0)
    asr_grid.addWidget(context.layout._asr_language_hints_edit, 3, 1)
    asr_grid.addWidget(context.ui._field_label("asr_api_key"), 4, 0)
    asr_grid.addWidget(
        context.ui._api_key_control(context.layout._asr_api_key_edit, context.layout._asr_api_key_status), 4, 1
    )
    asr_grid.addWidget(context.ui._field_label("whisper_device"), 5, 0)
    asr_grid.addWidget(context.layout._whisper_device_combo, 5, 1)
    asr_grid.addWidget(context.ui._field_label("whisper_compute"), 6, 0)
    asr_grid.addWidget(context.layout._whisper_compute_combo, 6, 1)
    asr_grid.addWidget(context.ui._field_label("whisper_beam"), 7, 0)
    asr_grid.addWidget(
        context.ui._slider_row(context.layout._whisper_beam_slider, context.layout._whisper_beam_value), 7, 1
    )
    asr_grid.addWidget(context.layout._whisper_vad_check, 8, 0, 1, 2)
    asr_grid.addWidget(context.layout._whisper_offline_check, 9, 0, 1, 2)
    layout_types.add_provider_preview_row(asr_grid, context, "asr", 10)

    ocr_grid = layout_types.QGridLayout()
    ocr_grid.setHorizontalSpacing(8)
    ocr_grid.setVerticalSpacing(7)
    ocr_grid.addWidget(context.ui._field_label("ocr_provider"), 0, 0)
    ocr_grid.addWidget(context.layout._ocr_provider_combo, 0, 1)
    ocr_grid.addWidget(context.ui._field_label("ocr_model"), 1, 0)
    ocr_grid.addWidget(context.layout._ocr_model_combo, 1, 1)
    ocr_grid.addWidget(context.ui._field_label("ocr_api_base"), 2, 0)
    ocr_grid.addWidget(context.layout._ocr_api_base_edit, 2, 1)
    ocr_grid.addWidget(context.ui._field_label("ocr_api_key"), 3, 0)
    ocr_grid.addWidget(
        context.ui._api_key_control(context.layout._ocr_api_key_edit, context.layout._ocr_api_key_status), 3, 1
    )
    ocr_grid.addWidget(context.ui._field_label("ocr_api_region"), 4, 0)
    ocr_grid.addWidget(context.layout._ocr_api_region_edit, 4, 1)
    ocr_grid.addWidget(context.ui._field_label("ocr_timeout"), 5, 0)
    ocr_grid.addWidget(
        context.ui._slider_row(context.layout._ocr_timeout_slider, context.layout._ocr_timeout_value), 5, 1
    )
    ocr_grid.addWidget(context.ui._field_label("ocr_fps"), 6, 0)
    ocr_grid.addWidget(context.ui._slider_row(context.layout._ocr_fps_slider, context.layout._ocr_fps_value), 6, 1)
    ocr_grid.addWidget(context.ui._field_label("ocr_crop_top"), 7, 0)
    ocr_grid.addWidget(
        context.ui._slider_row(context.layout._ocr_crop_top_slider, context.layout._ocr_crop_top_value), 7, 1
    )
    ocr_grid.addWidget(context.ui._field_label("ocr_crop_height"), 8, 0)
    ocr_grid.addWidget(
        context.ui._slider_row(context.layout._ocr_crop_height_slider, context.layout._ocr_crop_height_value), 8, 1
    )
    ocr_grid.addWidget(context.ui._field_label("ocr_scale"), 9, 0)
    ocr_grid.addWidget(context.ui._slider_row(context.layout._ocr_scale_slider, context.layout._ocr_scale_value), 9, 1)
    ocr_grid.addWidget(context.ui._field_label("ocr_psm"), 10, 0)
    ocr_grid.addWidget(context.ui._slider_row(context.layout._ocr_psm_slider, context.layout._ocr_psm_value), 10, 1)
    ocr_grid.addWidget(context.layout._ocr_threshold_check, 11, 0, 1, 2)
    ocr_grid.addWidget(context.ui._field_label("ocr_min_confidence"), 12, 0)
    ocr_grid.addWidget(
        context.ui._slider_row(context.layout._ocr_min_confidence_slider, context.layout._ocr_min_confidence_value),
        12,
        1,
    )
    ocr_grid.addWidget(context.ui._field_label("ocr_merge_similarity"), 13, 0)
    ocr_grid.addWidget(
        context.ui._slider_row(context.layout._ocr_merge_similarity_slider, context.layout._ocr_merge_similarity_value),
        13,
        1,
    )
    layout_types.add_provider_preview_row(ocr_grid, context, "ocr", 14)

    translation_grid = layout_types.QGridLayout()
    translation_grid.setHorizontalSpacing(8)
    translation_grid.setVerticalSpacing(7)
    translation_grid.addWidget(context.ui._field_label("translator"), 0, 0)
    translation_grid.addWidget(context.layout._translator_combo, 0, 1)
    translation_grid.addWidget(context.ui._field_label("translation_model"), 1, 0)
    translation_grid.addWidget(context.layout._nllb_model_combo, 1, 1)
    translation_grid.addWidget(context.ui._field_label("translator_device"), 2, 0)
    translation_grid.addWidget(context.layout._translation_device_combo, 2, 1)
    translation_grid.addWidget(context.ui._field_label("translator_api_base"), 3, 0)
    translation_grid.addWidget(context.layout._translator_api_base_edit, 3, 1)
    translation_grid.addWidget(context.ui._field_label("translator_api_key"), 4, 0)
    translation_grid.addWidget(
        context.ui._api_key_control(context.layout._translator_api_key_edit, context.layout._translator_api_key_status),
        4,
        1,
    )
    translation_grid.addWidget(context.ui._field_label("translator_api_region"), 5, 0)
    translation_grid.addWidget(context.layout._translator_api_region_edit, 5, 1)
    translation_grid.addWidget(context.ui._field_label("translation_max_tokens"), 6, 0)
    translation_grid.addWidget(
        context.ui._slider_row(
            context.layout._translation_max_tokens_slider, context.layout._translation_max_tokens_value
        ),
        6,
        1,
    )
    translation_grid.addWidget(context.ui._field_label("translation_beams"), 7, 0)
    translation_grid.addWidget(
        context.ui._slider_row(context.layout._translation_beams_slider, context.layout._translation_beams_value), 7, 1
    )
    translation_grid.addWidget(context.layout._translation_offline_check, 8, 0, 1, 2)
    layout_types.add_provider_preview_row(translation_grid, context, "translation", 9)

    tts_grid = layout_types.QGridLayout()
    tts_grid.setHorizontalSpacing(8)
    tts_grid.setVerticalSpacing(7)
    tts_grid.addWidget(context.ui._field_label("tts"), 0, 0)
    tts_grid.addWidget(context.layout._tts_provider_combo, 0, 1)
    tts_grid.addWidget(context.layout._tts_mode_label, 1, 0)
    tts_grid.addWidget(context.layout._vieneu_mode_combo, 1, 1)
    tts_grid.addWidget(context.layout._tts_model_label, 2, 0)
    tts_grid.addWidget(context.layout._vieneu_model_combo, 2, 1)
    tts_grid.addWidget(context.ui._field_label("vieneu_core"), 3, 0)
    tts_grid.addWidget(context.layout._vieneu_core_combo, 3, 1)
    tts_grid.addWidget(context.ui._field_label("vieneu_runtime"), 4, 0)
    tts_grid.addWidget(context.layout._vieneu_runtime_combo, 4, 1)
    tts_grid.addWidget(context.ui._field_label("vieneu_device"), 5, 0)
    tts_grid.addWidget(context.layout._vieneu_device_combo, 5, 1)
    tts_grid.addWidget(context.ui._field_label("vieneu_backend"), 6, 0)
    tts_grid.addWidget(context.layout._vieneu_backend_combo, 6, 1)
    tts_grid.addWidget(context.ui._field_label("vieneu_temperature"), 7, 0)
    tts_grid.addWidget(
        context.ui._slider_row(context.layout._vieneu_temperature_slider, context.layout._vieneu_temperature_value),
        7,
        1,
    )
    tts_grid.addWidget(context.ui._field_label("tts_max_chars"), 8, 0)
    tts_grid.addWidget(
        context.ui._slider_row(context.layout._vieneu_max_chars_slider, context.layout._vieneu_max_chars_value), 8, 1
    )
    tts_grid.addWidget(context.layout._vieneu_offline_check, 9, 0, 1, 2)
    layout_types.add_provider_preview_row(tts_grid, context, "tts", 10)

    tts_advanced_grid = layout_types.QGridLayout()
    tts_advanced_grid.setHorizontalSpacing(8)
    tts_advanced_grid.setVerticalSpacing(7)
    tts_advanced_grid.addWidget(context.ui._field_label("vieneu_python"), 1, 0)
    tts_advanced_grid.addWidget(context.layout._vieneu_python_edit, 1, 1)
    tts_advanced_grid.addWidget(context.ui._field_label("tts_api_base"), 5, 0)
    tts_advanced_grid.addWidget(context.layout._tts_api_base_edit, 5, 1)
    tts_advanced_grid.addWidget(context.ui._field_label("tts_api_key"), 6, 0)
    tts_advanced_grid.addWidget(
        context.ui._api_key_control(context.layout._tts_api_key_edit, context.layout._tts_api_key_status), 6, 1
    )
    tts_advanced_grid.addWidget(context.ui._field_label("tts_api_secret"), 7, 0)
    tts_advanced_grid.addWidget(
        context.ui._api_key_control(context.layout._tts_api_secret_edit, context.layout._tts_api_secret_status), 7, 1
    )
    tts_advanced_grid.addWidget(context.ui._field_label("tts_api_region"), 8, 0)
    tts_advanced_grid.addWidget(context.layout._tts_api_region_edit, 8, 1)
    tts_advanced_grid.addWidget(context.ui._field_label("tts_model"), 9, 0)
    tts_advanced_grid.addWidget(context.layout._tts_model_edit, 9, 1)

    cleanup_grid = layout_types.QGridLayout()
    cleanup_grid.setHorizontalSpacing(8)
    cleanup_grid.setVerticalSpacing(7)
    cleanup_grid.addWidget(context.ui._field_label("transcript_cleanup"), 0, 0)
    cleanup_grid.addWidget(context.layout._transcript_cleanup_mode_combo, 0, 1)
    cleanup_grid.addWidget(context.ui._field_label("cleanup_provider"), 1, 0)
    cleanup_grid.addWidget(context.layout._transcript_cleanup_provider_combo, 1, 1)
    cleanup_grid.addWidget(context.ui._field_label("cleanup_model"), 2, 0)
    cleanup_grid.addWidget(context.layout._transcript_cleanup_model_combo, 2, 1)
    cleanup_grid.addWidget(context.ui._field_label("cleanup_api_base"), 3, 0)
    cleanup_grid.addWidget(context.layout._transcript_cleanup_api_base_edit, 3, 1)
    cleanup_grid.addWidget(context.ui._field_label("cleanup_api_key"), 4, 0)
    cleanup_grid.addWidget(
        context.ui._api_key_control(
            context.layout._transcript_cleanup_api_key_edit,
            context.layout._transcript_cleanup_api_key_status,
        ),
        4,
        1,
    )
    cleanup_grid.addWidget(context.ui._field_label("cleanup_timeout"), 5, 0)
    cleanup_grid.addWidget(
        context.ui._slider_row(context.layout._cleanup_timeout_slider, context.layout._cleanup_timeout_value), 5, 1
    )
    layout_types.add_provider_preview_row(cleanup_grid, context, "cleanup", 6)

    voice_ai_grid = layout_types.QGridLayout()
    voice_ai_grid.setHorizontalSpacing(8)
    voice_ai_grid.setVerticalSpacing(7)
    voice_ai_grid.addWidget(context.ui._field_label("speaker_gender_provider"), 0, 0)
    voice_ai_grid.addWidget(context.layout._speaker_gender_provider_combo, 0, 1)
    voice_ai_grid.addWidget(context.ui._field_label("speaker_gender_model"), 1, 0)
    voice_ai_grid.addWidget(context.layout._speaker_gender_model_combo, 1, 1)
    voice_ai_grid.addWidget(context.ui._field_label("speaker_gender_api_base"), 2, 0)
    voice_ai_grid.addWidget(context.layout._speaker_gender_api_base_edit, 2, 1)
    voice_ai_grid.addWidget(context.ui._field_label("speaker_gender_api_key"), 3, 0)
    voice_ai_grid.addWidget(
        context.ui._api_key_control(
            context.layout._speaker_gender_api_key_edit, context.layout._speaker_gender_api_key_status
        ),
        3,
        1,
    )
    voice_ai_grid.addWidget(context.ui._field_label("speaker_gender_timeout"), 4, 0)
    voice_ai_grid.addWidget(
        context.ui._slider_row(
            context.layout._speaker_gender_timeout_slider, context.layout._speaker_gender_timeout_value
        ),
        4,
        1,
    )
    voice_ai_grid.addWidget(context.ui._field_label("source_filter_model"), 5, 0)
    voice_ai_grid.addWidget(context.layout._source_filter_model_combo, 5, 1)
    layout_types.add_provider_preview_row(voice_ai_grid, context, "speaker_gender", 6)
    return SettingsSections(
        advanced_capture_grid=advanced_capture_grid,
        advanced_match_grid=advanced_match_grid,
        advanced_playback_grid=advanced_playback_grid,
        advanced_terms_grid=advanced_terms_grid,
        advanced_timing_grid=advanced_timing_grid,
        asr_grid=asr_grid,
        basic_playback_grid=basic_playback_grid,
        basic_processing_grid=basic_processing_grid,
        basic_source_grid=basic_source_grid,
        basic_voice_grid=basic_voice_grid,
        cleanup_grid=cleanup_grid,
        ocr_grid=ocr_grid,
        translation_grid=translation_grid,
        tts_advanced_grid=tts_advanced_grid,
        tts_grid=tts_grid,
        voice_ai_grid=voice_ai_grid,
    )
