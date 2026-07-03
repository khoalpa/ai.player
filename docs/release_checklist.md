# AI Player Release Checklist

Use this checklist before sharing a build.

## Source Baseline

- Pick the target profile from `docs\release_profiles.md` and use its install,
  smoke, model, and distribution expectations for this build.
- Verify profiles in order: `Lite` first, then `OfflineCpu`, then `Gpu` only
  when the previous profile passes and the release scope requires it. When
  verifying multiple profiles in one command, pass all selected profiles to
  `release_verify.ps1`; the script runs them in that order.
- Confirm the working tree contains only intended changes with `git status --short --branch`.
- Review untracked files with `git ls-files -o --exclude-standard` and either add them intentionally or move generated scratch files under ignored paths.
- Run `.\scripts\check_release_worktree.ps1 -FailOnModified` before creating a
  release artifact. This fails on untracked source/plugin files unless they are
  explicitly allowed with `-AllowUntrackedPath`.
- Review optional plugin scope against `docs\plugin_policy.md`, especially any
  untracked source under `plugins\`.
- Review `docs\release_artifact_inventory.md` for tracked root documents and
  bundled tool binaries before public release; move local/private artifacts out
  of the repository or document the release decision there.
- Review binary fixture changes separately with `git diff --stat` so regenerated samples are not bundled by accident.
- Install the release dependency set with `.\.venv\Scripts\python.exe -m pip install -c constraints\windows-release-py310.txt -e ".[dev,packaging,offline-ai,gpu,audio-separation,audit]"`.
- Run `.\.venv\Scripts\python.exe -m ruff check .`.
- Run `.\.venv\Scripts\python.exe -m pytest`.
- Run `.\scripts\release_verify.ps1` for the short release gate and generated
  logs under `data\tmp\release-verify\`. Use `-RequireSignature` for any
  artifact that will leave the development machine.
- For distributable artifacts, run release verification with the selected
  profile and signing requirement, for example
  `.\scripts\release_verify.ps1 -BuildProfiles Lite -RequireSignature`.
- Run `.\.venv\Scripts\python.exe .\scripts\compare_performance_presets.py --language vi`
  to review preset latency/quality tradeoffs before changing release defaults.
- Run `.\.venv\Scripts\python.exe .\scripts\workflow_smoke_check.py --output data\tmp\workflow-smoke-current.json`
  to verify committed smoke fixtures still match the ASR/translation/TTS/export
  baseline expectations in `docs\workflow_smoke_baseline.json`.
- Run `.\.venv\Scripts\python.exe .\scripts\workflow_benchmark.py --check-baselines --baseline docs\workflow_benchmark_baselines.json`
  to validate benchmark baseline metadata.
- Run `.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py`.
- Review `docs\test_coverage_map.md` and note any workflow gaps that must be
  covered by manual smoke for this release.
- Leave `AI_PLAYER_INCLUDE_EXTRA_YTDLP_PLUGINS` unset for public release builds.
  Use `scripts\build_internal.ps1` only for internal builds that install private
  yt-dlp plugin packages.
- Leave `AI_PLAYER_INCLUDE_PRIVATE_TELEGRAM_PLUGIN` unset for public release
  builds. Use the Internal profile when authenticated client plugins are bundled.
- Run `.\scripts\audit_dependencies.ps1` and triage any unresolved advisories. If audit tools are not installed yet, run it once with `-InstallTools`.
- `.\scripts\release_verify.ps1 -BuildProfiles OfflineCpu` and
  `.\scripts\release_verify.ps1 -BuildProfiles Gpu` run
  `.\scripts\audit_dependencies.ps1 -ReviewAcceptedVulnerabilities`
  automatically before building the portable artifact.
- Run `.\scripts\audit_dependencies.ps1 -ReviewAcceptedVulnerabilities`
  before release approval to verify the only remaining findings are explicitly
  accepted in `docs\dependency_audit.md`.

## Runtime Smoke Test

- Start the app with `.\.venv\Scripts\python.exe main.py`.
- Open a short local video and confirm playback starts.
- Open a transcript file and confirm transcript mode can be selected.
- Open a small text/PDF document and confirm segments are created.
- Enter text in the document editor source and confirm a transcript timeline is created.
- If an online provider API key is configured, restart the app and confirm the key
  remains configured without plaintext in `data\config\settings.json` or
  `data\config\online_providers.local.json`.
- If the selected profile hides advanced online providers, confirm existing
  provider-specific keys survive save/restart without being shown in the active
  Lite/offline combo.

## AI Pipeline Smoke Test

- Run one short ASR pass when a Whisper model exists.
- Run `.\.venv\Scripts\python.exe .\scripts\workflow_benchmark.py --output data\tmp\workflow-benchmark-current.json --baseline-workflow video_short`
  for a short-video regression check, or use `--baseline-workflow transcript` / `document`
  for text-first workflows.
- Run `.\.venv\Scripts\python.exe .\scripts\asr_regression.py --max-wer 0.35` when the local Vietnamese sample set is present.
- Run one translation with the selected translator.
- Run one TTS voice test with the selected provider.
- Start dubbing briefly, then stop/reset and confirm the app remains responsive.

## Export Smoke Test

- Export a short dubbed media file.
- Run the release smoke coverage with `.\.venv\Scripts\python.exe -m pytest tests\test_release_smoke.py`.
- Re-open exported files with a normal media player and confirm duration is plausible.

## Portable Build

- Build with `.\scripts\build_portable.ps1`. The script runs
  `.\scripts\check_release_worktree.ps1 -FailOnModified` by default and should
  fail if source/plugin files are untracked or tracked files are modified.
- For ordered local verification builds, run
  `.\scripts\release_verify.ps1 -BuildProfiles Lite` first, then rerun with
  `-BuildProfiles OfflineCpu` or `-BuildProfiles Gpu` only after the Lite
  artifact passes smoke. Passing multiple profiles builds them in Lite,
  Offline CPU, then GPU order.
- Use `.\scripts\build_portable.ps1 -SkipReleaseWorktreeCheck` only for local
  development builds that will not be shared.
- List available signing certificates with `.\scripts\build_portable.ps1 -ListCodeSigningCerts`.
- For private, public, enterprise, or any other off-machine distribution, build
  with `.\scripts\build_portable.ps1 -RequireSignature`.
- If multiple signing certificates are available, add `-CodeSigningCertThumbprint "<real-thumbprint>"`.
- If the signing certificate is provided as a `.pfx` or `.p12` file, use `-CodeSigningPfxPath` and pass the password as a `SecureString`.
- Launch the app from `dist\portable`.
- Run `.\scripts\smoke_launch_app.ps1 -AppPath "dist\portable\AI Player Lite\AI Player\AI Player.exe"` and confirm it stays running for the smoke window.
- Run Runtime Doctor from the portable app.
- Record the completed smoke results in `docs\manual_smoke_results.md`.

## Final Smoke Record

Add one dated entry to `docs\manual_smoke_results.md` before sharing the build:

- Release profile and command used, including whether `-RequireSignature` was
  set.
- `data\tmp\release-verify\<stamp>\summary.json` path and status.
- Artifact path and portable executable path.
- Signing result: certificate thumbprint/PFX source for signed builds, or an
  explicit note that the artifact is local-only and unsigned.
- Manual smoke coverage completed for the selected profile.
- Any accepted advisories, optional missing libraries, unavailable hardware, or
  skipped checks with the reason.
