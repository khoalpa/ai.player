from __future__ import annotations

from ai_player.ui.features import layout as layout_types


def build(context):
    context.layout._auto_match_audio_check.setProperty("i18n_key", "auto_match")
    context.layout._auto_match_audio_check.setChecked(context.config.dubbing_auto_match_audio)
    context.layout._dubbing_buffer_slider = context.ui._value_slider(
        minimum=0,
        maximum=600,
        step=10,
        value=int(context.config.dubbing_min_ready_ahead_seconds),
    )
    context.layout._dubbing_buffer_value = context.ui._value_label(
        f"{int(context.config.dubbing_min_ready_ahead_seconds)} s"
    )
    context.layout._dubbing_buffer_slider.valueChanged.connect(
        lambda value: context.layout._dubbing_buffer_value.setText(f"{value} s")
    )
    context.layout._dub_speed_slider = context.ui._value_slider(
        minimum=-20,
        maximum=20,
        step=5,
        value=context.config.dubbing_speed_percent,
    )
    context.layout._dub_speed_value = context.ui._value_label(f"{context.config.dubbing_speed_percent:+d} %")
    context.layout._dub_speed_slider.valueChanged.connect(
        lambda value: context.layout._dub_speed_value.setText(f"{value:+d} %")
    )
    context.layout._video_delay_slider = context.ui._value_slider(
        minimum=0,
        maximum=30,
        step=1,
        value=int(context.config.original_audio_playback_delay_seconds),
    )
    context.layout._video_delay_value = context.ui._value_label(
        f"{int(context.config.original_audio_playback_delay_seconds)} s"
    )
    context.layout._video_delay_slider.valueChanged.connect(
        lambda value: context.layout._video_delay_value.setText(f"{value} s")
    )
    context.layout._whisper_device_combo = context.ui._option_combo(
        layout_types._dropdown_options("whisper_devices", context.config.gui_language),
        context.config.whisper_device,
    )
    context.layout._whisper_compute_combo = context.ui._option_combo(
        layout_types._dropdown_options("whisper_compute_types", context.config.gui_language),
        context.config.whisper_compute_type,
    )
    context.layout._whisper_beam_slider, context.layout._whisper_beam_value = context.ui._labeled_slider(
        minimum=1,
        maximum=8,
        step=1,
        value=context.config.whisper_beam_size,
        formatter=lambda value: f"{value}",
    )
    context.layout._whisper_vad_check = layout_types.QCheckBox(context.settings._tr("whisper_vad_filter"))
    context.layout._whisper_vad_check.setProperty("i18n_key", "whisper_vad_filter")
    context.layout._whisper_vad_check.setChecked(context.config.whisper_vad_filter)
    context.layout._segment_seconds_slider, context.layout._segment_seconds_value = context.ui._labeled_slider(
        minimum=4,
        maximum=20,
        step=2,
        value=context.config.segment_seconds,
        formatter=lambda value: f"{value} s",
    )
    context.layout._prebuffer_segments_slider, context.layout._prebuffer_segments_value = context.ui._labeled_slider(
        minimum=1,
        maximum=4,
        step=1,
        value=context.config.dubbing_prebuffer_segments,
        formatter=lambda value: f"{value}",
    )
    context.layout._lookahead_segments_slider, context.layout._lookahead_segments_value = context.ui._labeled_slider(
        minimum=1,
        maximum=6,
        step=1,
        value=context.config.dubbing_lookahead_segments,
        formatter=lambda value: f"{value}",
    )
    context.layout._overlap_policy_combo = context.ui._option_combo(
        layout_types._dropdown_options("dubbing_overlap_policies", context.config.gui_language),
        context.config.dubbing_overlap_policy,
    )
    context.layout._start_delay_slider, context.layout._start_delay_value = context.ui._labeled_slider(
        minimum=0,
        maximum=5,
        step=1,
        value=int(context.config.dubbing_start_delay_seconds),
        formatter=lambda value: f"{value} s",
    )
    context.layout._speed_min_slider, context.layout._speed_min_value = context.ui._labeled_slider(
        minimum=80,
        maximum=100,
        step=5,
        value=int(context.config.dubbing_speed_min * 100),
        formatter=lambda value: f"{value} %",
    )
    context.layout._speed_max_slider, context.layout._speed_max_value = context.ui._labeled_slider(
        minimum=100,
        maximum=125,
        step=5,
        value=int(context.config.dubbing_speed_max * 100),
        formatter=lambda value: f"{value} %",
    )
    context.layout._volume_gain_min_slider, context.layout._volume_gain_min_value = context.ui._labeled_slider(
        minimum=-20,
        maximum=0,
        step=1,
        value=int(context.config.dubbing_volume_gain_min_db),
        formatter=lambda value: f"{value} dB",
    )
    context.layout._volume_gain_max_slider, context.layout._volume_gain_max_value = context.ui._labeled_slider(
        minimum=0,
        maximum=20,
        step=1,
        value=int(context.config.dubbing_volume_gain_max_db),
        formatter=lambda value: f"+{value} dB",
    )
    context.layout._vieneu_runtime_combo = context.ui._option_combo(
        layout_types._dropdown_options("vieneu_runtimes", context.config.gui_language),
        context.config.vieneu_tts_runtime,
    )
    context.layout._vieneu_device_combo = context.ui._option_combo(
        layout_types._dropdown_options("vieneu_devices", context.config.gui_language),
        context.config.vieneu_tts_device,
    )
    context.layout._vieneu_backend_combo = context.ui._option_combo(
        layout_types._dropdown_options("vieneu_backends", context.config.gui_language),
        context.config.vieneu_tts_backend,
    )
    context.layout._capture_devices_loaded = False
    capture_devices = context.layout._initial_capture_device_options()
    context.layout._capture_backend_combo = context.ui._option_combo(
        layout_types._dropdown_options("capture_backends", context.config.gui_language),
        context.config.capture_backend,
    )
    context.layout._capture_system_device_combo = context.ui._device_combo(
        capture_devices.get("system", []),
        context.config.capture_system_device,
    )
    context.layout._capture_microphone_device_combo = context.ui._device_combo(
        capture_devices.get("microphone", []),
        context.config.capture_microphone_device,
    )
    context.layout._transcript_cleanup_mode_combo = context.ui._option_combo(
        layout_types._dropdown_options("transcript_cleanup_modes", context.config.gui_language),
        context.config.transcript_cleanup_mode,
    )
    context.layout._transcript_cleanup_provider_combo = context.ui._option_combo(
        layout_types._dropdown_options("transcript_cleanup_providers", context.config.gui_language),
        context.config.transcript_cleanup_provider,
    )
    context.layout._transcript_cleanup_model_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._transcript_cleanup_model_combo)
    context.layout._transcript_cleanup_model_combo.setEditable(True)
    for option in layout_types.available_local_llm_options():
        context.layout._transcript_cleanup_model_combo.addItem(option.name, option.id)
    current_cleanup_model = context.config.transcript_cleanup_model
    cleanup_model_index = context.layout._transcript_cleanup_model_combo.findData(current_cleanup_model)
    if cleanup_model_index < 0 and current_cleanup_model:
        context.layout._transcript_cleanup_model_combo.addItem(current_cleanup_model, current_cleanup_model)
        cleanup_model_index = context.layout._transcript_cleanup_model_combo.findData(current_cleanup_model)
    context.layout._transcript_cleanup_model_combo.setCurrentIndex(max(0, cleanup_model_index))
    context.layout._transcript_cleanup_model_combo.setToolTip(context.settings._tr("cleanup_model_tooltip"))
