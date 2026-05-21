# Manual Smoke Results

Use this file to keep a short, build-specific record before sharing a Windows build.

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
