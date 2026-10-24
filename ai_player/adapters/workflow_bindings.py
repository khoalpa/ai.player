"""Composition of workflow contracts with platform/provider implementations."""

from __future__ import annotations

from ai_player.application import workflow_ports


def document() -> workflow_ports.DocumentDependencies:
    from ai_player.adapters.ai.transcript_cleanup import TranscriptCleaner as TranscriptCleaner
    from ai_player.adapters.media.document_reader import DocumentPage as DocumentPage
    from ai_player.adapters.media.ffmpeg import ProcessCancelled as ProcessCancelled
    from ai_player.adapters.media.ffmpeg import run_ffmpeg_cancelable as run_ffmpeg_cancelable
    from ai_player.adapters.pipeline.aligned_audio import aligned_timeline_inputs as aligned_timeline_inputs
    from ai_player.adapters.pipeline.aligned_audio import mix_timeline_inputs_chunked as mix_timeline_inputs_chunked
    from ai_player.adapters.pipeline.document_export_voice import build_document_export_cue as build_document_export_cue
    from ai_player.adapters.pipeline.document_export_voice import (
        build_prepared_document_export_cues as build_prepared_document_export_cues,
    )
    from ai_player.adapters.pipeline.export_media import document_video_args as document_video_args
    from ai_player.adapters.pipeline.export_media import document_video_concat_lines as document_video_concat_lines
    from ai_player.adapters.pipeline.export_media import mux_document_video_args as mux_document_video_args
    from ai_player.adapters.pipeline.export_media import silence_args as silence_args
    from ai_player.adapters.pipeline.export_media import to_wav_args as to_wav_args
    from ai_player.adapters.pipeline.export_media import trim_leading_silence_args as trim_leading_silence_args
    from ai_player.adapters.pipeline.export_utils import _clean_message as _clean_message
    from ai_player.adapters.pipeline.export_utils import _duration_seconds as _duration_seconds
    from ai_player.adapters.pipeline.export_utils import _export_worker_count as _export_worker_count
    from ai_player.adapters.pipeline.export_utils import _json_text as _json_text
    from ai_player.adapters.pipeline.export_utils import _percent_value as _percent_value
    from ai_player.adapters.pipeline.export_utils import _render_text_page_image as _render_text_page_image
    from ai_player.adapters.pipeline.export_utils import _translate_texts as _translate_texts
    from ai_player.adapters.tts.tts import create_tts_provider as create_tts_provider
    from ai_player.runtime.offline_env import OfflineEnvironmentToken as OfflineEnvironmentToken
    from ai_player.runtime.offline_env import pop_hf_offline_environment as pop_hf_offline_environment
    from ai_player.runtime.offline_env import push_hf_offline_environment as push_hf_offline_environment
    from ai_player.runtime.translation_runtime import (
        get_shared_vietnamese_translator as get_shared_vietnamese_translator,
    )

    return workflow_ports.DocumentDependencies(
        OfflineEnvironmentToken=OfflineEnvironmentToken,
        pop_hf_offline_environment=pop_hf_offline_environment,
        push_hf_offline_environment=push_hf_offline_environment,
        DocumentPage=DocumentPage,
        ProcessCancelled=ProcessCancelled,
        run_ffmpeg_cancelable=run_ffmpeg_cancelable,
        TranscriptCleaner=TranscriptCleaner,
        get_shared_vietnamese_translator=get_shared_vietnamese_translator,
        create_tts_provider=create_tts_provider,
        aligned_timeline_inputs=aligned_timeline_inputs,
        mix_timeline_inputs_chunked=mix_timeline_inputs_chunked,
        build_document_export_cue=build_document_export_cue,
        build_prepared_document_export_cues=build_prepared_document_export_cues,
        document_video_args=document_video_args,
        document_video_concat_lines=document_video_concat_lines,
        mux_document_video_args=mux_document_video_args,
        silence_args=silence_args,
        to_wav_args=to_wav_args,
        trim_leading_silence_args=trim_leading_silence_args,
        _clean_message=_clean_message,
        _duration_seconds=_duration_seconds,
        _export_worker_count=_export_worker_count,
        _json_text=_json_text,
        _percent_value=_percent_value,
        _render_text_page_image=_render_text_page_image,
        _translate_texts=_translate_texts,
    )


def export() -> workflow_ports.ExportDependencies:
    from ai_player.adapters.ai.asr import should_use_online_asr as should_use_online_asr
    from ai_player.adapters.ai.asr import transcribe_asr as transcribe_asr
    from ai_player.adapters.ai.speaker_voice_selector import VoiceGenderSelector as VoiceGenderSelector
    from ai_player.adapters.ai.transcript_cleanup import TranscriptCleaner as TranscriptCleaner
    from ai_player.adapters.media.audio_matcher import extract_audio_range as extract_audio_range
    from ai_player.adapters.media.audio_matcher import match_tts_to_reference as match_tts_to_reference
    from ai_player.adapters.media.demucs_separation import DemucsSeparationError as DemucsSeparationError
    from ai_player.adapters.media.demucs_separation import demucs_available as demucs_available
    from ai_player.adapters.media.demucs_separation import demucs_command as demucs_command
    from ai_player.adapters.media.ffmpeg import ProcessCancelled as ProcessCancelled
    from ai_player.adapters.media.ffmpeg import make_silence as ffmpeg_make_silence
    from ai_player.adapters.media.ffmpeg import probe_duration_seconds as probe_duration_seconds
    from ai_player.adapters.media.ffmpeg import run_cancelable_process as run_cancelable_process
    from ai_player.adapters.media.ffmpeg import run_ffmpeg_cancelable as run_ffmpeg_cancelable
    from ai_player.adapters.pipeline.aligned_audio import aligned_timeline_inputs as aligned_timeline_inputs
    from ai_player.adapters.pipeline.aligned_audio import mix_timeline_inputs_chunked as mix_timeline_inputs_chunked
    from ai_player.adapters.pipeline.asr_fallback import (
        transcribe_model_with_device_fallback as transcribe_model_with_device_fallback,
    )
    from ai_player.adapters.pipeline.export_audio import _duration_seconds as _duration_seconds
    from ai_player.adapters.pipeline.export_audio import _make_silence as _make_silence
    from ai_player.adapters.pipeline.export_audio import _probe_duration_seconds as _probe_duration_seconds
    from ai_player.adapters.pipeline.export_media import extract_source_audio_args as extract_source_audio_args
    from ai_player.adapters.pipeline.export_media import full_quality_audio_args as full_quality_audio_args
    from ai_player.adapters.pipeline.export_media import mux_video_args as mux_video_args
    from ai_player.adapters.pipeline.export_media import silence_args as silence_args
    from ai_player.adapters.pipeline.export_media import to_wav_args as to_wav_args
    from ai_player.adapters.pipeline.export_media import trim_leading_silence_args as trim_leading_silence_args
    from ai_player.adapters.pipeline.export_utils import _align_text_results as _align_text_results
    from ai_player.adapters.pipeline.export_utils import _clean_message as _clean_message
    from ai_player.adapters.pipeline.export_utils import _clean_transcript_many as _clean_transcript_many
    from ai_player.adapters.pipeline.export_utils import _duration_value as _duration_value
    from ai_player.adapters.pipeline.export_utils import _effective_whisper_device as _effective_whisper_device
    from ai_player.adapters.pipeline.export_utils import _export_worker_count as _export_worker_count
    from ai_player.adapters.pipeline.export_utils import _ffmpeg_escape as _ffmpeg_escape
    from ai_player.adapters.pipeline.export_utils import _json_number as _json_number
    from ai_player.adapters.pipeline.export_utils import _json_text as _json_text
    from ai_player.adapters.pipeline.export_utils import _percent_value as _percent_value
    from ai_player.adapters.pipeline.export_utils import _safe_float as _safe_float
    from ai_player.adapters.pipeline.export_utils import _segment_export_items as _segment_export_items
    from ai_player.adapters.pipeline.export_utils import _segments_words_payload as _segments_words_payload
    from ai_player.adapters.pipeline.export_utils import _source_cues_from_segments as _source_cues_from_segments_data
    from ai_player.adapters.pipeline.export_utils import _to_wav as _to_wav
    from ai_player.adapters.pipeline.export_utils import _transcript_export_items as _transcript_export_items
    from ai_player.adapters.pipeline.export_utils import _translate_texts as _translate_texts
    from ai_player.adapters.pipeline.export_utils import _trim_leading_silence as _trim_leading_silence
    from ai_player.adapters.pipeline.export_utils import _tts_disabled as _tts_disabled
    from ai_player.adapters.pipeline.export_utils import export_rejects_audio_source as export_rejects_audio_source
    from ai_player.adapters.pipeline.export_utils import export_requires_asr as export_requires_asr
    from ai_player.adapters.pipeline.export_utils import export_uses_transcript_source as export_uses_transcript_source
    from ai_player.adapters.pipeline.source_export_voice import (
        build_prepared_source_export_cues as build_prepared_source_export_cues,
    )
    from ai_player.adapters.pipeline.source_export_voice import build_source_export_cue as build_source_export_cue
    from ai_player.adapters.pipeline.source_export_voice import (
        prepare_source_export_items as prepare_source_export_items,
    )
    from ai_player.adapters.pipeline.source_export_voice import translate_export_items as translate_export_items
    from ai_player.adapters.pipeline.staged_audio_stems import create_source_audio_stems as create_source_audio_stems
    from ai_player.adapters.pipeline.staged_export_utils import StagedExportPaths as StagedExportPaths
    from ai_player.adapters.pipeline.staged_export_utils import prepare_staged_output_dir as prepare_staged_output_dir
    from ai_player.adapters.pipeline.staged_export_utils import staged_manifest_payload as staged_manifest_payload
    from ai_player.adapters.pipeline.staged_export_utils import write_staged_manifest as write_staged_manifest
    from ai_player.adapters.pipeline.staged_target_voice import build_target_voice_cue as build_target_voice_cue
    from ai_player.adapters.pipeline.staged_target_voice import build_target_voice_cues as build_target_voice_cues
    from ai_player.adapters.pipeline.staged_target_voice import (
        target_voice_artifact_paths as target_voice_artifact_paths,
    )
    from ai_player.adapters.pipeline.transcript_export_voice import (
        build_prepared_transcript_export_cues as build_prepared_transcript_export_cues,
    )
    from ai_player.adapters.pipeline.transcript_export_voice import (
        build_transcript_export_cue as build_transcript_export_cue,
    )
    from ai_player.adapters.tts.tts import TTSError as TTSError
    from ai_player.adapters.tts.tts import create_tts_provider as create_tts_provider
    from ai_player.runtime.offline_env import OfflineEnvironmentToken as OfflineEnvironmentToken
    from ai_player.runtime.offline_env import pop_hf_offline_environment as pop_hf_offline_environment
    from ai_player.runtime.offline_env import push_hf_offline_environment as push_hf_offline_environment
    from ai_player.runtime.translation_runtime import (
        get_shared_vietnamese_translator as get_shared_vietnamese_translator,
    )
    from ai_player.runtime.whisper_runtime import SharedWhisperModel as SharedWhisperModel
    from ai_player.runtime.whisper_runtime import effective_whisper_compute_type as shared_whisper_compute_type
    from ai_player.runtime.whisper_runtime import get_shared_whisper_model as get_shared_whisper_model
    from ai_player.runtime.whisper_runtime import whisper_transcribe_kwargs as whisper_transcribe_kwargs

    return workflow_ports.ExportDependencies(
        _make_silence=_make_silence,
        _duration_seconds=_duration_seconds,
        _probe_duration_seconds=_probe_duration_seconds,
        OfflineEnvironmentToken=OfflineEnvironmentToken,
        pop_hf_offline_environment=pop_hf_offline_environment,
        push_hf_offline_environment=push_hf_offline_environment,
        should_use_online_asr=should_use_online_asr,
        transcribe_asr=transcribe_asr,
        extract_audio_range=extract_audio_range,
        match_tts_to_reference=match_tts_to_reference,
        DemucsSeparationError=DemucsSeparationError,
        demucs_available=demucs_available,
        demucs_command=demucs_command,
        ProcessCancelled=ProcessCancelled,
        probe_duration_seconds=probe_duration_seconds,
        run_cancelable_process=run_cancelable_process,
        run_ffmpeg_cancelable=run_ffmpeg_cancelable,
        ffmpeg_make_silence=ffmpeg_make_silence,
        VoiceGenderSelector=VoiceGenderSelector,
        TranscriptCleaner=TranscriptCleaner,
        get_shared_vietnamese_translator=get_shared_vietnamese_translator,
        TTSError=TTSError,
        create_tts_provider=create_tts_provider,
        SharedWhisperModel=SharedWhisperModel,
        get_shared_whisper_model=get_shared_whisper_model,
        whisper_transcribe_kwargs=whisper_transcribe_kwargs,
        shared_whisper_compute_type=shared_whisper_compute_type,
        aligned_timeline_inputs=aligned_timeline_inputs,
        mix_timeline_inputs_chunked=mix_timeline_inputs_chunked,
        transcribe_model_with_device_fallback=transcribe_model_with_device_fallback,
        extract_source_audio_args=extract_source_audio_args,
        full_quality_audio_args=full_quality_audio_args,
        mux_video_args=mux_video_args,
        silence_args=silence_args,
        to_wav_args=to_wav_args,
        trim_leading_silence_args=trim_leading_silence_args,
        _align_text_results=_align_text_results,
        _clean_message=_clean_message,
        _clean_transcript_many=_clean_transcript_many,
        _duration_value=_duration_value,
        _effective_whisper_device=_effective_whisper_device,
        _export_worker_count=_export_worker_count,
        _ffmpeg_escape=_ffmpeg_escape,
        _json_number=_json_number,
        _json_text=_json_text,
        _percent_value=_percent_value,
        _safe_float=_safe_float,
        _segment_export_items=_segment_export_items,
        _segments_words_payload=_segments_words_payload,
        _to_wav=_to_wav,
        _transcript_export_items=_transcript_export_items,
        _translate_texts=_translate_texts,
        _trim_leading_silence=_trim_leading_silence,
        _tts_disabled=_tts_disabled,
        export_rejects_audio_source=export_rejects_audio_source,
        export_requires_asr=export_requires_asr,
        export_uses_transcript_source=export_uses_transcript_source,
        _source_cues_from_segments_data=_source_cues_from_segments_data,
        build_prepared_source_export_cues=build_prepared_source_export_cues,
        build_source_export_cue=build_source_export_cue,
        prepare_source_export_items=prepare_source_export_items,
        translate_export_items=translate_export_items,
        create_source_audio_stems=create_source_audio_stems,
        StagedExportPaths=StagedExportPaths,
        prepare_staged_output_dir=prepare_staged_output_dir,
        staged_manifest_payload=staged_manifest_payload,
        write_staged_manifest=write_staged_manifest,
        build_target_voice_cue=build_target_voice_cue,
        build_target_voice_cues=build_target_voice_cues,
        target_voice_artifact_paths=target_voice_artifact_paths,
        build_prepared_transcript_export_cues=build_prepared_transcript_export_cues,
        build_transcript_export_cue=build_transcript_export_cue,
    )


def meeting() -> workflow_ports.MeetingDependencies:
    from ai_player.adapters.ai.asr import should_use_online_asr as should_use_online_asr
    from ai_player.adapters.ai.asr import transcribe_asr as transcribe_asr
    from ai_player.adapters.ai.transcript_cleanup import TranscriptCleaner as TranscriptCleaner
    from ai_player.adapters.media.capture_sources import (
        capture_system_microphone_audio as capture_system_microphone_audio,
    )
    from ai_player.adapters.media.ffmpeg import concat_escape as _ffmpeg_escape
    from ai_player.adapters.media.ffmpeg import concat_escape as concat_escape
    from ai_player.adapters.media.ffmpeg import ffmpeg_executable as ffmpeg_executable
    from ai_player.adapters.media.ffmpeg import ffplay_executable as ffplay_executable
    from ai_player.adapters.media.ffmpeg import terminate_process as terminate_process
    from ai_player.adapters.pipeline.asr_fallback import (
        transcribe_model_with_device_fallback as transcribe_model_with_device_fallback,
    )
    from ai_player.adapters.tts.tts import create_tts_provider as create_tts_provider
    from ai_player.runtime.offline_env import OfflineEnvironmentToken as OfflineEnvironmentToken
    from ai_player.runtime.offline_env import pop_hf_offline_environment as pop_hf_offline_environment
    from ai_player.runtime.offline_env import push_hf_offline_environment as push_hf_offline_environment
    from ai_player.runtime.translation_runtime import (
        get_shared_vietnamese_translator as get_shared_vietnamese_translator,
    )
    from ai_player.runtime.whisper_runtime import SharedWhisperModel as SharedWhisperModel
    from ai_player.runtime.whisper_runtime import effective_whisper_compute_type as shared_whisper_compute_type
    from ai_player.runtime.whisper_runtime import effective_whisper_device as _effective_whisper_device
    from ai_player.runtime.whisper_runtime import get_shared_whisper_model as get_shared_whisper_model
    from ai_player.runtime.whisper_runtime import whisper_transcribe_kwargs as whisper_transcribe_kwargs

    return workflow_ports.MeetingDependencies(
        _ffmpeg_escape=_ffmpeg_escape,
        OfflineEnvironmentToken=OfflineEnvironmentToken,
        pop_hf_offline_environment=pop_hf_offline_environment,
        push_hf_offline_environment=push_hf_offline_environment,
        should_use_online_asr=should_use_online_asr,
        transcribe_asr=transcribe_asr,
        capture_system_microphone_audio=capture_system_microphone_audio,
        concat_escape=concat_escape,
        ffmpeg_executable=ffmpeg_executable,
        ffplay_executable=ffplay_executable,
        terminate_process=terminate_process,
        TranscriptCleaner=TranscriptCleaner,
        get_shared_vietnamese_translator=get_shared_vietnamese_translator,
        create_tts_provider=create_tts_provider,
        SharedWhisperModel=SharedWhisperModel,
        get_shared_whisper_model=get_shared_whisper_model,
        whisper_transcribe_kwargs=whisper_transcribe_kwargs,
        shared_whisper_compute_type=shared_whisper_compute_type,
        _effective_whisper_device=_effective_whisper_device,
        transcribe_model_with_device_fallback=transcribe_model_with_device_fallback,
    )


def realtime() -> workflow_ports.RealtimeDependencies:
    from ai_player.adapters.ai.asr import should_use_online_asr as should_use_online_asr
    from ai_player.adapters.ai.asr import transcribe_asr as transcribe_asr
    from ai_player.adapters.ai.speaker_voice_selector import VoiceGenderSelector as VoiceGenderSelector
    from ai_player.adapters.ai.speaker_voice_selector import select_voice_for_reference as select_voice_for_reference
    from ai_player.adapters.ai.subtitle_ocr import recognize_hard_subtitles as recognize_hard_subtitles
    from ai_player.adapters.ai.transcript_cleanup import TranscriptCleaner as TranscriptCleaner
    from ai_player.adapters.ai.transcript_cleanup import (
        is_online_transcript_cleanup_provider as is_online_transcript_cleanup_provider,
    )
    from ai_player.adapters.media.audio_matcher import audio_duration_seconds as audio_duration_seconds
    from ai_player.adapters.media.audio_matcher import extract_audio_range as extract_audio_range
    from ai_player.adapters.media.audio_matcher import match_tts_to_reference as match_tts_to_reference
    from ai_player.adapters.media.capture_sources import capture_microphone_audio as capture_microphone_audio
    from ai_player.adapters.media.capture_sources import capture_system_audio as capture_system_audio
    from ai_player.adapters.media.capture_sources import (
        capture_system_microphone_audio as capture_system_microphone_audio,
    )
    from ai_player.adapters.media.ffmpeg import ProcessCancelled as ProcessCancelled
    from ai_player.adapters.media.ffmpeg import ffplay_executable as ffplay_executable
    from ai_player.adapters.media.ffmpeg import make_silence as ffmpeg_make_silence
    from ai_player.adapters.media.ffmpeg import run_ffmpeg_cancelable as run_ffmpeg_cancelable
    from ai_player.adapters.media.ffmpeg import terminate_process as terminate_process
    from ai_player.adapters.pipeline.asr_fallback import (
        transcribe_model_with_device_fallback as transcribe_model_with_device_fallback,
    )
    from ai_player.adapters.sources.video_source import (
        is_telegram_web_progressive_url as is_telegram_web_progressive_url,
    )
    from ai_player.adapters.tts.tts import create_tts_provider as create_tts_provider
    from ai_player.adapters.tts.tts_base import is_pathological_tts_duration as is_pathological_tts_duration
    from ai_player.adapters.tts.tts_base import prepare_tts_text as prepare_tts_text
    from ai_player.runtime.offline_env import OfflineEnvironmentToken as OfflineEnvironmentToken
    from ai_player.runtime.offline_env import pop_hf_offline_environment as pop_hf_offline_environment
    from ai_player.runtime.offline_env import push_hf_offline_environment as push_hf_offline_environment
    from ai_player.runtime.runtime_telemetry import RUNTIME_TELEMETRY as RUNTIME_TELEMETRY
    from ai_player.runtime.translation_runtime import (
        get_shared_vietnamese_translator as get_shared_vietnamese_translator,
    )
    from ai_player.runtime.whisper_runtime import SharedWhisperModel as SharedWhisperModel
    from ai_player.runtime.whisper_runtime import effective_whisper_compute_type as shared_whisper_compute_type
    from ai_player.runtime.whisper_runtime import effective_whisper_device as _effective_whisper_device
    from ai_player.runtime.whisper_runtime import get_shared_whisper_model as get_shared_whisper_model
    from ai_player.runtime.whisper_runtime import whisper_transcribe_kwargs as whisper_transcribe_kwargs

    return workflow_ports.RealtimeDependencies(
        OfflineEnvironmentToken=OfflineEnvironmentToken,
        pop_hf_offline_environment=pop_hf_offline_environment,
        push_hf_offline_environment=push_hf_offline_environment,
        RUNTIME_TELEMETRY=RUNTIME_TELEMETRY,
        should_use_online_asr=should_use_online_asr,
        transcribe_asr=transcribe_asr,
        audio_duration_seconds=audio_duration_seconds,
        extract_audio_range=extract_audio_range,
        match_tts_to_reference=match_tts_to_reference,
        capture_microphone_audio=capture_microphone_audio,
        capture_system_audio=capture_system_audio,
        capture_system_microphone_audio=capture_system_microphone_audio,
        ProcessCancelled=ProcessCancelled,
        ffplay_executable=ffplay_executable,
        run_ffmpeg_cancelable=run_ffmpeg_cancelable,
        terminate_process=terminate_process,
        ffmpeg_make_silence=ffmpeg_make_silence,
        VoiceGenderSelector=VoiceGenderSelector,
        select_voice_for_reference=select_voice_for_reference,
        recognize_hard_subtitles=recognize_hard_subtitles,
        TranscriptCleaner=TranscriptCleaner,
        is_online_transcript_cleanup_provider=is_online_transcript_cleanup_provider,
        get_shared_vietnamese_translator=get_shared_vietnamese_translator,
        create_tts_provider=create_tts_provider,
        is_pathological_tts_duration=is_pathological_tts_duration,
        prepare_tts_text=prepare_tts_text,
        is_telegram_web_progressive_url=is_telegram_web_progressive_url,
        SharedWhisperModel=SharedWhisperModel,
        get_shared_whisper_model=get_shared_whisper_model,
        whisper_transcribe_kwargs=whisper_transcribe_kwargs,
        shared_whisper_compute_type=shared_whisper_compute_type,
        _effective_whisper_device=_effective_whisper_device,
        transcribe_model_with_device_fallback=transcribe_model_with_device_fallback,
    )


def sources() -> workflow_ports.SourcesDependencies:
    from ai_player.adapters.ai.provider_preview import preview_provider as preview_provider
    from ai_player.adapters.media.document_reader import create_document_transcript as create_document_transcript
    from ai_player.adapters.media.ffmpeg import ffmpeg_executable as ffmpeg_executable
    from ai_player.adapters.media.ffmpeg import terminate_process as terminate_process
    from ai_player.adapters.media.source_voice_filter import SourceVoiceFilterCancelled as SourceVoiceFilterCancelled
    from ai_player.adapters.media.source_voice_filter import apply_source_voice_filter as apply_source_voice_filter
    from ai_player.adapters.media.source_voice_filter import (
        read_source_voice_filter_backend as read_source_voice_filter_backend,
    )
    from ai_player.adapters.media.source_voice_filter import (
        resolve_source_voice_filter_command as resolve_source_voice_filter_command,
    )
    from ai_player.adapters.media.source_voice_filter import (
        source_voice_filter_cached_output_valid as source_voice_filter_cached_output_valid,
    )
    from ai_player.adapters.media.source_voice_filter import (
        write_source_voice_filter_metadata as write_source_voice_filter_metadata,
    )
    from ai_player.adapters.sources.telegram_channel import TelegramLoginConfig as TelegramLoginConfig
    from ai_player.adapters.sources.telegram_channel import TelegramLoginRequest as TelegramLoginRequest
    from ai_player.adapters.sources.telegram_channel import TelegramPasswordRequired as TelegramPasswordRequired
    from ai_player.adapters.sources.telegram_channel import complete_telegram_login as complete_telegram_login
    from ai_player.adapters.sources.telegram_channel import (
        download_telegram_channel_video as download_telegram_channel_video,
    )
    from ai_player.adapters.sources.telegram_channel import list_telegram_channel_items as list_telegram_channel_items
    from ai_player.adapters.sources.telegram_channel import (
        list_telegram_channel_items_authenticated as list_telegram_channel_items_authenticated,
    )
    from ai_player.adapters.sources.telegram_channel import list_telegram_channel_videos as list_telegram_channel_videos
    from ai_player.adapters.sources.telegram_channel import (
        list_telegram_channel_videos_authenticated as list_telegram_channel_videos_authenticated,
    )
    from ai_player.adapters.sources.telegram_channel import start_telegram_login as start_telegram_login
    from ai_player.adapters.sources.telegram_channel import (
        telegram_channel_item_translation_text as telegram_channel_item_translation_text,
    )
    from ai_player.adapters.sources.video_source import resolve_video_source as resolve_video_source
    from ai_player.adapters.sources.youtube_channel import list_youtube_channel_items as list_youtube_channel_items
    from ai_player.adapters.storage.media_cache import (
        playback_compat_cached_output_valid as playback_compat_cached_output_valid,
    )
    from ai_player.adapters.storage.media_cache import remove_playback_compat_output as remove_playback_compat_output
    from ai_player.adapters.storage.media_cache import write_playback_compat_metadata as write_playback_compat_metadata
    from ai_player.runtime.runtime_warmup import RuntimeWarmupCancelled as RuntimeWarmupCancelled
    from ai_player.runtime.runtime_warmup import warm_runtime_components as warm_runtime_components
    from ai_player.runtime.translation_runtime import (
        get_shared_vietnamese_translator as get_shared_vietnamese_translator,
    )

    return workflow_ports.SourcesDependencies(
        create_document_transcript=create_document_transcript,
        ffmpeg_executable=ffmpeg_executable,
        terminate_process=terminate_process,
        playback_compat_cached_output_valid=playback_compat_cached_output_valid,
        remove_playback_compat_output=remove_playback_compat_output,
        write_playback_compat_metadata=write_playback_compat_metadata,
        preview_provider=preview_provider,
        RuntimeWarmupCancelled=RuntimeWarmupCancelled,
        warm_runtime_components=warm_runtime_components,
        SourceVoiceFilterCancelled=SourceVoiceFilterCancelled,
        apply_source_voice_filter=apply_source_voice_filter,
        read_source_voice_filter_backend=read_source_voice_filter_backend,
        resolve_source_voice_filter_command=resolve_source_voice_filter_command,
        source_voice_filter_cached_output_valid=source_voice_filter_cached_output_valid,
        write_source_voice_filter_metadata=write_source_voice_filter_metadata,
        TelegramLoginConfig=TelegramLoginConfig,
        TelegramLoginRequest=TelegramLoginRequest,
        TelegramPasswordRequired=TelegramPasswordRequired,
        complete_telegram_login=complete_telegram_login,
        download_telegram_channel_video=download_telegram_channel_video,
        list_telegram_channel_items=list_telegram_channel_items,
        list_telegram_channel_items_authenticated=list_telegram_channel_items_authenticated,
        list_telegram_channel_videos=list_telegram_channel_videos,
        list_telegram_channel_videos_authenticated=list_telegram_channel_videos_authenticated,
        start_telegram_login=start_telegram_login,
        telegram_channel_item_translation_text=telegram_channel_item_translation_text,
        get_shared_vietnamese_translator=get_shared_vietnamese_translator,
        resolve_video_source=resolve_video_source,
        list_youtube_channel_items=list_youtube_channel_items,
    )
