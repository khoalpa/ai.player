# Manual Smoke Results

Use this file to keep a short, build-specific record before sharing a Windows build.

## 2026-06-25 Offline CPU And GPU Release Verification

- Source baseline: current working tree after release verification profile
  automation, deterministic workflow smoke checks, typed video-source errors,
  and worker lifecycle state extraction were added.
- Offline CPU profile: `.\scripts\release_verify.ps1 -BuildProfiles OfflineCpu`
  passed. Summary:
  `data\tmp\release-verify\20260625-141712\summary.json`.
- GPU profile: `.\scripts\release_verify.ps1 -BuildProfiles Gpu` passed.
  Summary: `data\tmp\release-verify\20260625-142411\summary.json`.
- Both profile runs passed the short gate: release worktree check, `ruff`,
  full `pytest`, `pip check`, Runtime Doctor, deterministic workflow smoke,
  release smoke tests, portable build, and 8-second portable launch smoke.
- Unit/integration tests: `.\.venv\Scripts\python.exe -m pytest -q` passed,
  729 tests in each profile run.
- Workflow smoke verified `samples\demo-video.mp4` duration, size, audio/video
  stream presence, and `samples\demo-transcript.srt` segment count.
- Portable build output: `dist\portable\AI Player Lite`.
- Code signing: no certificate was provided, so the portable bundle remains
  unsigned. Prepare a code-signing certificate and rerun with `-RequireSignature`
  before broad public distribution.
- Note: PyInstaller reported optional missing TensorRT/TBB libraries during the
  build. The build completed and launch smoke passed.

## 2026-06-23 UI And Portable Refactor Smoke

- Source baseline: current working tree after provider preview UI helpers,
  provider preview mixin, download task detail helper, and TTS error parsing
  extraction were added.
- Lint: `.\.venv\Scripts\python.exe -m ruff check .` passed.
- Dependency consistency: `.\.venv\Scripts\python.exe -m pip check` passed.
- Unit/integration tests: `.\.venv\Scripts\python.exe -m pytest` passed, 788 tests.
- Runtime Doctor: `.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py --ci`
  passed with required package, FFmpeg/ffplay, Tesseract, LibreOffice, local
  model folders, and tessdata checks available.
- Source UI launch smoke: `.\.venv\Scripts\python.exe main.py` stayed running
  for 12 seconds and was stopped after verification.
- Release smoke coverage: `.\.venv\Scripts\python.exe -m pytest tests\test_release_smoke.py`
  passed, 4 tests.
- Workflow benchmark: `.\.venv\Scripts\python.exe .\scripts\workflow_benchmark.py --audio samples\demo-video.mp4 --output data\tmp\workflow-benchmark-current.json --source-language en`
  passed and wrote `data\tmp\workflow-benchmark-current.json`; ASR returned 0
  speech segments for the short demo sample, while translation and TTS completed.
- Portable build: `.\scripts\build_portable.ps1` passed and created
  `dist\portable\AI Player Lite`.
- Portable launch smoke: `.\scripts\smoke_launch_app.ps1 -AppPath "dist\portable\AI Player Lite\AI Player\AI Player.exe" -Seconds 12`
  passed after the final rebuild.
- Note: no code-signing certificate was provided, so 689 PE files remain
  unsigned. PyInstaller also reported optional missing TensorRT/TBB libraries;
  the build completed and launch smoke passed.

## 2026-06-21 Online Provider Config And Portable Rebuild

- Source baseline: current working tree after online provider/API credential
  settings were split into user-local configuration.
- Online provider config: provider choices, API bases/regions/models/timeouts,
  and encrypted API key payloads now save to
  `data\config\online_providers.local.json`; legacy `secrets.json`,
  `settings.json`, and `runtime.local.json` provider values remain readable.
- Credential hygiene: plaintext API keys remain excluded from `settings.json`
  and `runtime.local.json`; saved key payloads are protected through the existing
  Windows DPAPI secret store.
- Lint: `.\.venv\Scripts\python.exe -m ruff check .` passed.
- Dependency consistency: `.\.venv\Scripts\python.exe -m pip check` passed.
- Unit/integration tests: `.\.venv\Scripts\python.exe -m pytest` passed, 733 tests.
- Release smoke coverage: `.\.venv\Scripts\python.exe -m pytest tests\test_release_smoke.py`
  passed, 4 tests.
- Runtime Doctor: `.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py --ci`
  passed with required package, FFmpeg/ffplay, Tesseract, LibreOffice, local
  model folders, and tessdata checks available.
- Accepted advisory review: `.\scripts\audit_dependencies.ps1 -ReviewAcceptedVulnerabilities`
  reports only `CVE-2025-69872` for transitive `diskcache` via
  `llama-cpp-python`; see `docs\dependency_audit.md`.
- Portable build: `.\scripts\build_portable.ps1` passed and created
  `dist\portable\AI Player Lite`.
- Portable launch smoke: `dist\portable\AI Player Lite\AI Player\AI Player.exe`
  stayed running for 8 seconds and was stopped after verification.
- Code signing check: `.\scripts\build_portable.ps1 -ListCodeSigningCerts`
  found no code-signing certificates in `CurrentUser\My` or `LocalMachine\My`;
  this portable artifact is unsigned.
- Note: PyInstaller reported optional missing libraries for TensorRT/TBB and
  optional hook imports; the build completed and launch smoke passed.

## 2026-06-21 Release Hygiene Verification

- Source baseline: current working tree after release hygiene cleanup, lint fixes,
  and dependency constraint refresh.
- Credential hygiene: untracked provider/API-key PDFs were moved out of the
  source root into `data\tmp\private-credentials`; root `.gitignore` now ignores
  matching local credential PDF exports.
- Release dependency install: `.\.venv\Scripts\python.exe -m pip install -c constraints\windows-release-py310.txt -e ".[dev,packaging,offline-ai,gpu,audio-separation,audit]"` passed.
- Dependency consistency: `.\.venv\Scripts\python.exe -m pip check` passed.
- Lint: `.\.venv\Scripts\python.exe -m ruff check .` passed.
- Unit/integration tests: `.\.venv\Scripts\python.exe -m pytest` passed, 732 tests.
- Runtime Doctor: `.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py --ci`
  passed with required package, FFmpeg/ffplay, Tesseract, LibreOffice, local
  model folders, and tessdata checks available.
- Accepted advisory review: `.\scripts\audit_dependencies.ps1 -ReviewAcceptedVulnerabilities`
  reports only `CVE-2025-69872` for transitive `diskcache` via
  `llama-cpp-python`; see `docs\dependency_audit.md`.
- Portable launch smoke: `dist\portable\AI Player Lite\AI Player\AI Player.exe`
  stayed running for 8 seconds and was stopped after verification.
- Note: this pass did not rebuild the portable artifact; it smoke-launched the
  existing artifact after source/runtime hygiene checks.

## 2026-06-03 URL Flow Refactor Verification

- Source baseline: current working tree after URL retry/fallback helper
  extraction and local-video source button GUI smoke were added.
- Lint: `.\.venv\Scripts\python.exe -m ruff check .` passed.
- Unit/integration tests: `.\.venv\Scripts\python.exe -m pytest` passed, 689 tests.
- Runtime Doctor: `.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py --profile lite --ci` passed with package, FFmpeg/ffplay, Tesseract, LibreOffice, local model folders, and tessdata checks available.
- Dependency audit: `.\scripts\audit_dependencies.ps1` passed and wrote reports under `data\tmp\dependency-audit`.
- Accepted advisory review: `.\scripts\audit_dependencies.ps1 -ReviewAcceptedVulnerabilities` reports only `CVE-2025-69872` for transitive `diskcache` via `llama-cpp-python`; see `docs\dependency_audit.md`.
- Plugin policy check: `git ls-files -o --exclude-standard plugins` did not list individual untracked plugin files in this pass.
- PyInstaller smoke build: `.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --distpath data\tmp\ci-dist --workpath data\tmp\ci-build "AI Player.spec"` passed.
- Built app launch smoke: `data\tmp\ci-dist\AI Player\AI Player.exe` stayed running for 8 seconds and was stopped after verification.
- Portable launch smoke: not run in this verification pass.

## 2026-06-03 Channel Browser Refactor Verification

- Source baseline: current working tree after channel-browser helper extraction,
  plugin policy documentation, and channel-browser coverage were added.
- Lint: `.\.venv\Scripts\python.exe -m ruff check .` passed.
- Unit/integration tests: `.\.venv\Scripts\python.exe -m pytest` passed, 685 tests.
- Runtime Doctor: `.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py --profile lite --ci` passed with package, FFmpeg/ffplay, Tesseract, LibreOffice, local model folders, and tessdata checks available.
- Dependency audit: `.\scripts\audit_dependencies.ps1` passed and wrote reports under `data\tmp\dependency-audit`.
- Accepted advisory review: `.\scripts\audit_dependencies.ps1 -ReviewAcceptedVulnerabilities` reports only `CVE-2025-69872` for transitive `diskcache` via `llama-cpp-python`; see `docs\dependency_audit.md`.
- PyInstaller smoke build: `.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --distpath data\tmp\ci-dist --workpath data\tmp\ci-build "AI Player.spec"` passed.
- Built app launch smoke: `data\tmp\ci-dist\AI Player\AI Player.exe` stayed running for 8 seconds and was stopped after verification.
- Portable launch smoke: not run in this verification pass.

## 2026-05-30 Priority Follow-up Verification

- Source baseline: current working tree after User Guide render helper coverage and Telegram channel state extraction were added.
- Lint: `.\.venv\Scripts\python.exe -m ruff check .` passed.
- Unit/integration tests: `.\.venv\Scripts\python.exe -m pytest` passed, 600 tests.
- Runtime Doctor: `.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py --ci` passed with package, FFmpeg/ffplay, Tesseract, LibreOffice, local model folders, and tessdata checks available.
- Dependency audit: `.\scripts\audit_dependencies.ps1` passed and wrote reports under `data\tmp\dependency-audit`.
- Accepted advisory review: `.\scripts\audit_dependencies.ps1 -ReviewAcceptedVulnerabilities` reports only `CVE-2025-69872` for transitive `diskcache` via `llama-cpp-python`; see `docs\dependency_audit.md`.
- PyInstaller smoke build: `.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --distpath data\tmp\ci-dist --workpath data\tmp\ci-build "AI Player.spec"` passed.
- Built app launch smoke: `data\tmp\ci-dist\AI Player\AI Player.exe` stayed running for 8 seconds and was stopped after verification.

## 2026-05-30 User Guide Regression Verification

- Source baseline: clean worktree before changes; current change fixes User Guide Vietnamese text and adds helper/test coverage.
- Lint: `.\.venv\Scripts\python.exe -m ruff check .` passed.
- Unit/integration tests: `.\.venv\Scripts\python.exe -m pytest` passed, 578 tests.
- Runtime Doctor: `.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py --ci` passed with package, FFmpeg/ffplay, Tesseract, LibreOffice, local model folders, and tessdata checks available.
- Dependency audit: `.\scripts\audit_dependencies.ps1` passed and wrote reports under `data\tmp\dependency-audit`.
- Accepted advisory review: `.\scripts\audit_dependencies.ps1 -ReviewAcceptedVulnerabilities` reports only `CVE-2025-69872` for transitive `diskcache` via `llama-cpp-python`; see `docs\dependency_audit.md`.
- Portable launch smoke: not run in this verification pass.

## 2026-05-25 Release Hardening

- Dependency audit: `.\scripts\audit_dependencies.ps1` passed after upgrading `setuptools` to 78.1.1 and `idna` to 3.15.
- Accepted advisory: `CVE-2025-69872` remains for transitive `diskcache` via `llama-cpp-python`; see `docs\dependency_audit.md` for the mitigation note.
- Accepted advisory review: `.\scripts\audit_dependencies.ps1 -ReviewAcceptedVulnerabilities` reports only the accepted `diskcache` advisory.
- Sample fixture: regenerated `samples\demo-video.mp4` as a 4-second 640x360 H.264/AAC smoke video, 74,936 bytes.

## 2026-05-25 Manual Pipeline Smoke

- Machine: local Windows workspace, Python virtual environment at `D:\project\ai.player\.venv\Scripts\python.exe`.
- OS: Windows-10-10.0.26200-SP0.
- Output record: `data\tmp\manual-smoke-2026-05-25\manual-smoke-results.json`.
- Artifacts: `data\tmp\manual-smoke-2026-05-25\manual-smoke-export.wav`, `data\tmp\manual-smoke-2026-05-25\manual-smoke-export.mp4`, `data\tmp\manual-smoke-2026-05-25\manual-smoke-vieneu.wav`.
- Video smoke: probed `samples\demo-video.mp4`, duration 4.000 seconds, and extracted `sample-video-0-4s.wav`, duration 4.000 seconds.
- Transcript smoke: parsed `samples\demo-transcript.srt`, 2 entries, first cue `Hello AI Player.`.
- Document smoke: created `manual-smoke-document.md`, converted it with `create_document_transcript`, 3 pages and 3 transcript segments.
- ASR smoke: Faster Whisper base CPU/int8 transcribed the extracted 5-second video audio, language `en`, probability 1.000, 3 segments, preview `Everyone is Carve Whoa`.
- Translation smoke: NLLB CTranslate2 int8 CPU translated the ASR preview to Vietnamese, preview `Mọi người đều là Carve Whoa`.
- VieNeu-TTS smoke: turbo CPU/subprocess synthesized `manual-smoke-vieneu.wav`, duration 1.440 seconds.
- Export smoke: `DubbingExportWorker` exported transcript-driven audio to `manual-smoke-export.wav`, duration 4.281 seconds.
- Export smoke: `DubbingExportWorker` exported transcript-driven video to `manual-smoke-export.mp4`, duration 3.908 seconds.
- Result: video, transcript, document, ASR, translation, TTS, audio export, and video export all passed.
- Note: this run used the current worktree copy of `samples\demo-video.mp4`.

## 2026-05-21 Local Baseline

- Machine: local Windows workspace, Python 3.10.6 virtual environment.
- OS: Windows-10-10.0.26200-SP0.
- CPU: Intel64 Family 6 Model 151 Stepping 2, GenuineIntel.
- GPU: NVIDIA RTX A4500 Laptop GPU; CUDA available from Torch.
- Source baseline: commit created from this run.
- Release dependency install: `python -m pip install -c constraints\windows-release-py310.txt -e ".[dev,packaging]"` passed.
- Lint: `python -m ruff check .` passed.
- Unit/integration tests: `python -m pytest` passed, 300 tests.
- Runtime Doctor: `python scripts\runtime_doctor.py` passed, including packages, FFmpeg/ffplay, Tesseract, LibreOffice, local model folders, tessdata, and audio capture devices.
- App launch: `python main.py` stayed running after startup smoke and was stopped manually by the smoke script.
- ASR smoke: Faster Whisper base CPU/int8 transcribed `data\tmp\manual-smoke-vieneu.wav`, language `vi`, 6 segments.
- NLLB translation smoke: CTranslate2 int8 CPU translated a short English release smoke sentence to Vietnamese.
- VieNeu-TTS smoke: turbo CPU/subprocess generated `data\tmp\manual-smoke-vieneu.wav`, duration about 38.7 seconds.
- Transcript export MP4 smoke: `python -m pytest tests\test_release_smoke.py` passed, 2 tests.
- Portable build: `scripts\build_portable.ps1` passed and created `dist\portable\AI Player Lite`.
- Portable launch: `dist\portable\AI Player Lite\AI Player\AI Player.exe` stayed running after startup smoke and was stopped manually by the smoke script.
- Portable artifact size: 12,533 files, about 6.18 GB.
- Portable Runtime Doctor UI: not automated from terminal; source Runtime Doctor passed and portable launch passed.

## Notes

- Record CPU/GPU details when a smoke run uses real AI models.
- Mark unavailable hardware explicitly instead of treating it as a failure.
- Keep generated media paths in `data/tmp` or another ignored location.
