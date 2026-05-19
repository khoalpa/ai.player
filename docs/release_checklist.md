# AI Player Release Checklist

Use this checklist before sharing a build.

## Source Baseline

- Confirm the working tree contains only intended changes.
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
- Run one translation with the selected translator.
- Run one TTS voice test with the selected provider.
- Start dubbing briefly, then stop/reset and confirm the app remains responsive.

## Export Smoke Test

- Export a short dubbed media file.
- Re-open exported files with a normal media player and confirm duration is plausible.

## Portable Build

- Build with `.\scripts\build_portable.ps1`.
- Launch the app from `dist\portable`.
- Run Runtime Doctor from the portable app.
