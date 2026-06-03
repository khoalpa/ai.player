# AI Player Test Coverage Map

Use this map to keep release risk visible as the app grows. It is not a
line-coverage report; it maps important user/runtime workflows to the tests that
protect them.

## Covered Workflows

- App startup and UI wiring:
  - `tests/test_player_window_smoke.py`
  - `tests/test_player_window_state.py`
  - `tests/test_player_window_utils.py`
- Settings, language resources, and runtime configuration:
  - `tests/test_settings_store.py`
  - `tests/test_runtime_catalog.py`
  - `tests/test_dependency_profiles.py`
  - `tests/test_config_paths.py`
- Runtime diagnostics and hardening:
  - `tests/test_runtime_diagnostics.py`
  - `tests/test_runtime_hardening.py`
  - `tests/test_runtime_recovery_modules.py`
  - `tests/test_recovery_baseline.py`
  - `tests/test_cli_encoding.py`
- Media source loading and URL handling:
  - `tests/test_channel_browser.py`
  - `tests/test_video_source.py`
  - `tests/test_video_url_controller.py`
  - `tests/test_player_window_media_cache.py`
  - `tests/test_player_window_smoke.py`
- Capture, ASR, translation, cleanup, OCR, and voices:
  - `tests/test_capture_sources.py`
  - `tests/test_whisper_runtime.py`
  - `tests/test_asr_options.py`
  - `tests/test_translation_runtime.py`
  - `tests/test_translation_config.py`
  - `tests/test_transcript_cleanup.py`
  - `tests/test_subtitle_ocr_config.py`
  - `tests/test_tts_voice.py`
  - `tests/test_speaker_voice_selector.py`
  - `tests/test_source_voice_filter.py`
- Audio scheduling, matching, and playback:
  - `tests/test_dubbing_schedule.py`
  - `tests/test_audio_matcher.py`
  - `tests/test_audio_timeline.py`
  - `tests/test_audio_playback.py`
  - `tests/test_worker_values.py`
- Export and document workflows:
  - `tests/test_export_helper_modules.py`
  - `tests/test_ffmpeg_helpers.py`
  - `tests/test_workflow_ffmpeg_exports.py`
  - `tests/test_workflow_documents.py`
  - `tests/test_release_smoke.py`
  - `tests/test_cache_progress_dialog.py`

## Current Gaps

- GUI tests still focus on construction, event-loop smoke, and widget/config
  wiring. Full click-through flows remain manual.
- Real AI model quality is covered by smoke/manual tests, not deterministic unit
  assertions, because model output varies by hardware/runtime.
- Packaging is smoke-built in CI, but portable app launch remains a manual smoke
  step before release.
- External policy issues such as Windows Application Control, code signing, and
  antivirus reputation need a dedicated release-machine checklist entry.
