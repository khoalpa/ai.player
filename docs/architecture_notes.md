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
