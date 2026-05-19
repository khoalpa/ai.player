# Recovery Notes

This workspace was reconstructed after an accidental cleanup command removed source, Git metadata, tests, docs, samples, and local model files.

Recovered from:

- `C:\Users\lpak\AppData\Local\Temp\ai_player_wheel_check\ai_player-0.1.0-py3-none-any.whl`
- Content visible in the current Codex session

Not fully recoverable without another copy:

- Original Git history and index
- Newer uncommitted source changes after the wheel was built
- The previous full test suite
- Local offline model files under `models\`
- Previous generated release/build artifacts

Current goal: keep the project runnable, documented, and testable at a minimal baseline.

## Recovery Progress

- Recreated a minimal Git repository and committed the wheel-based baseline.
- Restored compatibility modules for shared Whisper loading, shared translation, runtime warm-up, audio playback, and Demucs wrapping.
- Recreated release/checklist docs, CI, sample video/transcript, and a smoke test suite.
- Downloaded core OCR tessdata packs: `eng`, `vie`, `osd`.

Current checks:

- `ruff check .` passes.
- `pytest` passes with the reconstructed smoke suite.
- `scripts\runtime_doctor.py --ci` runs and required runtime items are available.
