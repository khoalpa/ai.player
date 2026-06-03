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
  references for dubbing, export, meeting, Telegram, and document loading while
  preserving the existing mixin attribute API.
- `ai_player.ui.player_window_state.TelegramChannelState` owns Telegram channel
  browser items, translations, navigation flags, thumbnail source, and side panel
  state while preserving the existing mixin attribute API.
- `ai_player.ui.channel_browser` owns pure channel-browser decisions such as
  Telegram/YouTube provider detection, channel keys, post/video id parsing,
  media-kind normalization, search text, and filtered item selection.
