# AI Player v0.1 MVP

This document defines the minimum useful product for `v0.1`.

## Release Baseline

- Version target: `v0.1.0`.
- Required automated checks:
  - `.\.venv\Scripts\python.exe -m ruff check .`
  - `.\.venv\Scripts\python.exe -m pytest`
  - `.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py`

## Required MVP Flows

1. Open a local video file or supported video URL.
2. Extract speech with Faster Whisper when a local model is available.
3. Translate with offline/local backends or pass text through unchanged.
4. Synthesize speech with VieNeu-TTS or Edge TTS.
5. Import transcript files and read supported documents.
6. Export reviewable dubbed audio/video outputs.
7. Report runtime readiness from the Runtime Doctor CLI/UI.

## Definition of Done

`v0.1` is complete when automated checks pass, a Windows smoke-test machine can run the required flows, and known limitations are documented.
