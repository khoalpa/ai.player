# Application restructuring

This checklist tracks the migration authorized on 2026-10-24. Existing local
changes are retained; the migration does not reset or commit the working tree.

## Completed implementation

- Group immutable configuration into ten independently defined sections.
- Add a persisted settings schema and atomic replacement of settings files.
- Introduce a task registry, cancellation tokens and bounded job history.
- Extract all five Qt worker modules into Qt-independent workflow engines.
- Add a Qt execution adapter with queued, generation-checked event delivery.
- Compose the main window from feature controllers; remove its 20 mixin bases
  and 72 state-forwarding properties.
- Move provider, platform and storage implementations into adapter packages.
- Move runtime diagnostics, model definitions and lifecycle utilities into runtime.
- Keep pure scheduling, deduplication and provider identifiers in domain.
- Generate speech into a temporary artifact and publish it only on success.
- Protect active TTS cache entries with leases and bound unused artifacts.
- Inject frozen provider/platform dependency records into every workflow.
- Split the main UI builder into functional view modules and settings assembly.
- Add tests for task cancellation, stale event rejection, configuration migration
  and architectural import boundaries.
- Verify the versioned isolated SDK patch profile before loading VieNeu.
- Share one manifest of raw runtime sources between Windows package builders.
- Keep the convenience dependency profile aligned with pyproject metadata.
- Separate fast/native CI jobs and update package paths and architecture docs.
- Fix the relocated audio-separation entrypoint and record early startup errors.
- Isolate Windows dependency discovery from unrelated applications' PATH entries.
  This fixes the incompatible ICU DLL selected during the first package smoke.

## Baseline and evidence

- Before restructuring: 771 fast tests passed.
- Final complete suite: **1,023 passed**, including Qt, FFmpeg and release tests
  (`data/tmp/restructure-final-tests.log`).
- Ruff lint and formatting checks: passed for the whole repository.
- Runtime doctor: all required items available (`data/tmp/restructure-doctor.log`).
- Workflow baseline guards: document, transcript and short video passed
  (`data/tmp/restructure-benchmark.log`).
- Composed window: rendered offscreen with a loaded Windows font and closed
  successfully (`output/restructure-ui.png`).
- CPU ONNX and CUDA PyTorch: actual v3 Turbo inference with sockets denied,
  empty temporary Hub caches, verified model hashes and 48 kHz output
  (`output/vieneu-v3-verification/{cpu,cuda}-report.json`).
- Application speech path: SpeechService, cache, provider and isolated server
  produced 48 kHz audio; one subprocess, clean shutdown, no partial files, with
  sockets denied in both processes
  (`output/vieneu-v3-verification/application-report.json`).
- Windows package: PyInstaller build passed and executable stayed running for
  15 seconds, with no startup error or native crash log content
  (`data/tmp/restructure-build.log`, `data/tmp/restructure-launch.log`).
- Packaged audio-separation entrypoint: `--demucs-runner --help` exited
  successfully after the module relocation.
- Packaged TTS sources: inference ran outside the checkout using only the raw
  sources in the final package, the dedicated SDK environment and the existing
  local v3 bundle. Both voices produced 48 kHz audio with sockets denied
  (`output/vieneu-v3-packaged-verification/cpu-report.json`).

The verified executable is `data/tmp/restructure-dist/AI Player/AI Player.exe`.
The package smoke is a local build, not an installer carrying every model. The
dedicated VieNeu environment and model bundle are prepared separately by the
existing setup scripts. UTF-8 output is required when redirecting the offline
verification CLI in Windows PowerShell.

## Separately blocked legacy-model removal

The earlier permanent deletion of the old `standard`, `turbo`, `codecs`,
`decoders` and `_hf-cache` directories was rejected by automatic approval review.
Those directories remain on disk. They are excluded from packaging and are not
runtime fallbacks. No blocked deletion was retried during this restructuring.

Generated logs and source snapshots are under `data/tmp/restructure-*` and are
excluded from the application package.
