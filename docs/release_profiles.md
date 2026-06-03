# AI Player Release Profiles

Use this matrix before building or sharing an artifact. Each release should pick
one profile explicitly so dependency install, smoke scope, and user expectations
match the package being produced.

## Lite

- Purpose: UI, document/transcript workflows, URL playback, Runtime Doctor, and
  Edge TTS when network access is available.
- Install: `.\.venv\Scripts\python.exe -m pip install -e ".[dev,packaging]"`
- Build: `.\scripts\build_portable.ps1`
- Model folders: not bundled.
- Required checks: `ruff`, `pytest`, `runtime_doctor.py --profile lite --ci`,
  PyInstaller smoke build, and `scripts\smoke_launch_app.ps1`.
- Manual smoke: local video playback, transcript import, small document import,
  Edge TTS if network is available.

## Offline CPU

- Purpose: offline ASR, translation, VieNeu-TTS, OCR, and export on machines
  without CUDA.
- Install: `.\.venv\Scripts\python.exe -m pip install -e ".[dev,packaging,offline-ai,audit]"`
- Build: `.\scripts\build_portable.ps1`
- Model folders: download or copy the default folders listed in `README.md`.
- Required checks: Lite checks plus dependency audit, accepted advisory review,
  `scripts\smoke_launch_app.ps1`, and Runtime Doctor with model/cache checks.
- Manual smoke: short ASR pass, NLLB translation, VieNeu-TTS synthesis, audio
  export, video export.

## GPU

- Purpose: offline workflows optimized for NVIDIA CUDA runtime.
- Install: `.\.venv\Scripts\python.exe -m pip install -c constraints\windows-release-py310.txt -e ".[dev,packaging,offline-ai,gpu,audio-separation,audit]"`
- Build: `.\scripts\build_portable.ps1`
- Model folders: same as Offline CPU, plus any Demucs/source-filter model needed
  by the target workflow.
- Required checks: Offline CPU checks plus GPU status in Runtime Doctor and at
  least one GPU-backed ASR or TTS smoke when hardware is available.
- Manual smoke: source filter or Demucs flow when that feature is included.

## Internal

- Purpose: private extractor/client builds and team-only runtime experiments.
- Install: start from the GPU profile, then install private packages locally.
- Build: `.\scripts\build_internal.ps1`
- Plugin scope: review `docs\plugin_policy.md` before creating or sharing the
  artifact.
- Environment: set private build flags only for this profile, such as
  `AI_PLAYER_INCLUDE_EXTRA_YTDLP_PLUGINS` or
  `AI_PLAYER_INCLUDE_PRIVATE_TELEGRAM_PLUGIN`.
- Required checks: GPU checks plus one private URL/client smoke for each private
  integration included in the artifact.
- Distribution: do not publish as a public release artifact.
