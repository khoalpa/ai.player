# Manual Smoke Results

Use this file to keep a short, build-specific record before sharing a Windows build.

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
