# Architecture Notes

## Player Window Refactoring

`PlayerWindow` is intentionally split across mixins, but it still owns a broad
set of UI state, worker lifecycle state, media state, document state, and runtime
status. Keep future changes moving state and behavior toward smaller owners
instead of adding new long-lived attributes directly to `PlayerWindow`.

Preferred extraction order:

- Worker lifecycle controllers for dubbing, export, source filtering, URL
  loading, and runtime warmup.
- Plain state containers for document playback, subtitle/live transcript state,
  media cache compatibility, and runtime metrics.
- Thin UI binding helpers that translate state changes into widget updates.

Each extraction should preserve the existing signal/slot behavior and land with
focused tests around the moved behavior.

Current extracted owners:

- `ai_player.workers.dubbing_schedule.DubbingAudioSchedule` owns pending target
  audio ordering, subtitle duplicate keys, and nearby text duplicate windows for
  realtime dubbing.
- `ai_player.ui.player_window_state.DocumentPlaybackState` and
  `SubtitleOverlayState` hold the first document/subtitle state moved out of
  `PlayerWindow` while preserving the old mixin attribute API.
- `ai_player.ui.player_window_state.MediaProcessingState` owns source voice
  filter worker state, playback compatibility worker state, and their cache maps
  while preserving the existing mixin attribute API.
- `ai_player.ui.player_window_state.PlaybackUiState` owns playback UI toggles,
  sidebar sizing, dialog references, and fullscreen flags while preserving the
  existing mixin attribute API.
- `ai_player.ui.player_window_state.MediaFrameState` owns media frame placement
  and fullscreen detach/restore bookkeeping while preserving the existing mixin
  attribute API.
- `ai_player.ui.player_window_state.RuntimeStatusState` owns Runtime tab timing,
  GPU status, and media probe cache state while preserving the existing mixin
  attribute API.
- `ai_player.ui.player_window_state.WorkerLifecycleState` owns long-lived worker
  references for dubbing, export, meeting, Telegram, and document loading plus
  generic worker stop/wait/delete behavior while preserving the existing mixin
  attribute API.
- `ai_player.ui.player_window_state.TelegramChannelState` owns Telegram channel
  browser items, translations, navigation flags, thumbnail source, and side panel
  state while preserving the existing mixin attribute API.
- `ai_player.ui.channel_browser` owns pure channel-browser decisions such as
  Telegram/YouTube provider detection, channel keys, post/video id parsing,
  media-kind normalization, search text, filtered item selection, item
  label/detail/HTML shaping, channel navigation, and persisted browser values.
- `ai_player.ui.video_url_controller` owns URL worker lifecycle plus pure
  retry/fallback decisions such as lower-quality retry selection, unrecoverable
  video errors, pending retry payloads, and browser fallback kwargs.
- `ai_player.ui.runtime_tab_controller.RuntimeTabController` owns Runtime tab
  refresh state, health/privacy/task summaries, media probing cache, and
  process/system/GPU diagnostics. `PlayerRuntimeMixin` should stay focused on
  building the Runtime tab widgets and delegating updates to the controller.
- `ai_player.ui.player_window_task_center.PlayerTaskCenterMixin` owns the
  user-facing Task Center dashboard. Long-running flows should update
  `_set_background_task_detail` so Task Center, Runtime, and status-bar views
  stay consistent without each worker owning duplicate UI.
- `ai_player.ui.provider_secret_controller.ProviderSecretController` owns the
  per-provider API key cache, restore, and save flow for ASR/OCR/translation/TTS
  settings. `PlayerSettingsMixin` keeps thin compatibility wrappers while the
  controller preserves secrets for online providers that may be hidden by the
  current Lite/offline provider profile.
- `ai_player.ui.media_start_panel` owns pure Media Start launcher decisions such
  as automatic profile selection, workflow badge keys, preset-card detail keys,
  and recent-source labels while `PlayerLayoutMixin` keeps widget construction
  and signal wiring.
- `ai_player.workers.dubbing_runtime` owns pure realtime dubbing decisions such
  as live/async source classification, segment worker counts, source-audio cache
  eligibility, and ready-ahead thresholds while `DubbingWorker` keeps Qt signals
  and long-running worker orchestration.

## TTS Service Boundaries

`ai_player.services.tts` is a compatibility facade for provider creation and
cross-provider voice selection. New callers should import provider-neutral
helpers from `tts_base.py`, Edge-specific behavior from `tts_edge.py`, online
provider behavior from `tts_online.py`, and VieNeu behavior from `tts_vieneu.py`.
Tests should monkey-patch those provider modules directly instead of relying on
facade-level hook synchronization.
