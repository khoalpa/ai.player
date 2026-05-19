# AI Player v0.1.0 Release Notes

## Status

This workspace has been partially reconstructed from a wheel artifact. Treat it as a recovery baseline, not a complete copy of the pre-cleanup working tree.

## Verification Snapshot

- `.\.venv\Scripts\python.exe -m ruff check .` passes.
- `.\.venv\Scripts\python.exe -m pytest` passes with the reconstructed smoke suite.
- `.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py --ci` runs.
- Runtime Doctor reports required package/tool checks as available on this machine.
- OCR tessdata packs restored: `eng`, `vie`, `osd`.

## Known Limitations

- The previous Git history and full test suite were not recoverable locally.
- Offline model folders need to be downloaded again.
- NLLB and full VieNeu/Whisper model payloads still need verification or re-download before offline AI workflows.
- Manual Windows smoke testing is required before sharing a build.
