# AI Player Release Checklist

Use this checklist before sharing a build.

## Source Baseline

- Pick the target profile from `docs\release_profiles.md` and use its install,
  smoke, model, and distribution expectations for this build.
- Confirm the working tree contains only intended changes with `git status --short --branch`.
- Review untracked files with `git ls-files -o --exclude-standard` and either add them intentionally or move generated scratch files under ignored paths.
- Review binary fixture changes separately with `git diff --stat` so regenerated samples are not bundled by accident.
- Install the release dependency set with `.\.venv\Scripts\python.exe -m pip install -c constraints\windows-release-py310.txt -e ".[dev,packaging,offline-ai,gpu,audio-separation,audit]"`.
- Run `.\.venv\Scripts\python.exe -m ruff check .`.
- Run `.\.venv\Scripts\python.exe -m pytest`.
- Run `.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py`.
- Review `docs\test_coverage_map.md` and note any workflow gaps that must be
  covered by manual smoke for this release.
- Leave `AI_PLAYER_INCLUDE_EXTRA_YTDLP_PLUGINS` unset for public release builds.
  Use `scripts\build_internal.ps1` only for internal builds that install private
  yt-dlp plugin packages.
- Run `.\scripts\audit_dependencies.ps1` and triage any unresolved advisories. If audit tools are not installed yet, run it once with `-InstallTools`.
- Run `.\scripts\audit_dependencies.ps1 -ReviewAcceptedVulnerabilities`
  before release approval to verify the only remaining findings are explicitly
  accepted in `docs\dependency_audit.md`.

## Runtime Smoke Test

- Start the app with `.\.venv\Scripts\python.exe main.py`.
- Open a short local video and confirm playback starts.
- Open a transcript file and confirm transcript mode can be selected.
- Open a small text/PDF document and confirm segments are created.
- Enter text in the document editor source and confirm a transcript timeline is created.
- If an OpenAI cleanup API key is configured, restart the app and confirm the key
  remains configured without plaintext in `data\config\settings.json`.

## AI Pipeline Smoke Test

- Run one short ASR pass when a Whisper model exists.
- Run `.\.venv\Scripts\python.exe .\scripts\asr_regression.py --max-wer 0.35` when the local Vietnamese sample set is present.
- Run one translation with the selected translator.
- Run one TTS voice test with the selected provider.
- Start dubbing briefly, then stop/reset and confirm the app remains responsive.

## Export Smoke Test

- Export a short dubbed media file.
- Run the release smoke coverage with `.\.venv\Scripts\python.exe -m pytest tests\test_release_smoke.py`.
- Re-open exported files with a normal media player and confirm duration is plausible.

## Portable Build

- Build with `.\scripts\build_portable.ps1`.
- List available signing certificates with `.\scripts\build_portable.ps1 -ListCodeSigningCerts`.
- On machines with enterprise code integrity enforcement, build with `.\scripts\build_portable.ps1 -RequireSignature`.
- If multiple signing certificates are available, add `-CodeSigningCertThumbprint "<real-thumbprint>"`.
- If the signing certificate is provided as a `.pfx` or `.p12` file, use `-CodeSigningPfxPath` and pass the password as a `SecureString`.
- Launch the app from `dist\portable`.
- Run `.\scripts\smoke_launch_app.ps1 -AppPath "dist\portable\AI Player Lite\AI Player\AI Player.exe"` and confirm it stays running for the smoke window.
- Run Runtime Doctor from the portable app.
- Record the completed smoke results in `docs\manual_smoke_results.md`.
