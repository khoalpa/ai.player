# AI Player Release Profiles

Use this matrix before building or sharing an artifact. Each release should pick
one profile explicitly so dependency install, smoke scope, and user expectations
match the package being produced.

Recommended verification order:

1. Build and smoke `Lite` first to validate packaging, launch, document, URL, and
   Edge-TTS paths without the full offline model/runtime cost.
2. Build `OfflineCpu` only after `Lite` passes, then verify local model folders
   and CPU ASR/translation/TTS/export flows.
3. Build `Gpu` only on a CUDA machine after `OfflineCpu` passes, then verify the
   GPU runtime and any audio-separation features included in the artifact.

Use `.\scripts\release_verify.ps1 -BuildProfiles Lite`, then rerun with
`-BuildProfiles OfflineCpu` or `-BuildProfiles Gpu` as the release scope expands.
Pass `-RequireSignature` for any artifact that will leave the development
machine or run under enterprise code-integrity policy.

## Lite

- Purpose: UI, document/transcript workflows, URL playback, Runtime Doctor, and
  Edge TTS when network access is available.
- Install: `.\.venv\Scripts\python.exe -m pip install -e ".[dev,packaging]"`
- Build: `.\scripts\release_verify.ps1 -BuildProfiles Lite`
- Model folders: not bundled.
- Required checks: `ruff`, `pytest`, `runtime_doctor.py --profile lite --ci`,
  PyInstaller smoke build, and `scripts\smoke_launch_app.ps1`.
- Manual smoke: local video playback, transcript import, small document import,
  Edge TTS if network is available.

## Offline CPU

- Purpose: offline ASR, translation, VieNeu-TTS, OCR, and export on machines
  without CUDA.
- Install: `.\.venv\Scripts\python.exe -m pip install -e ".[dev,packaging,offline-ai,audit]"`
- Build: `.\scripts\release_verify.ps1 -BuildProfiles OfflineCpu`
- Model folders: download or copy the default folders listed in `README.md`.
- Required checks: Lite checks plus dependency audit, accepted advisory review,
  `scripts\smoke_launch_app.ps1`, and Runtime Doctor with model/cache checks.
- Manual smoke: short ASR pass, NLLB translation, VieNeu-TTS synthesis, audio
  export, video export.

## GPU

- Purpose: offline workflows optimized for NVIDIA CUDA runtime.
- Install: `.\.venv\Scripts\python.exe -m pip install -c constraints\windows-release-py310.txt -e ".[dev,packaging,offline-ai,gpu,audio-separation,audit]"`
- Build: `.\scripts\release_verify.ps1 -BuildProfiles Gpu`
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

## Signing Decision

- Local development smoke: unsigned builds are acceptable when they stay on the
  developer machine.
- Private/team release: prefer `-RequireSignature`; record the certificate
  thumbprint or PFX source in the smoke notes.
- Public or enterprise release: require `-RequireSignature`, verify the portable
  executable signature, and do not publish if the signing step is skipped.
