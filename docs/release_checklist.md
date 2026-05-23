# AI Player Release Checklist

Use this checklist before sharing a build.

## Source Baseline

- Confirm the working tree contains only intended changes.
- Install the release dependency set with `.\.venv\Scripts\python.exe -m pip install -c constraints\windows-release-py310.txt -e ".[dev,packaging]"`.
- Run `.\.venv\Scripts\python.exe -m ruff check .`.
- Run `.\.venv\Scripts\python.exe -m pytest`.
- Run `.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py`.

## Runtime Smoke Test

- Start the app with `.\.venv\Scripts\python.exe main.py`.
- Open a short local video and confirm playback starts.
- Open a transcript file and confirm transcript mode can be selected.
- Open a small text/PDF document and confirm segments are created.

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
- Run Runtime Doctor from the portable app.
- Record the completed smoke results in `docs\manual_smoke_results.md`.
