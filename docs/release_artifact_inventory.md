# Release Artifact Inventory

Use this inventory for tracked binary or document artifacts that are easy to
forget during public release review. `scripts/check_release_worktree.ps1` fails
when a tracked root-level artifact or bundled tool binary is not listed here.

## Tracked Artifacts

- `App configuration.pdf`
  - Scope: root-level reference document.
  - Release decision: review before public release and move under `docs/` or
    an ignored private path if it contains local configuration, credentials, or
    machine-specific setup.

- `tools/ffmpeg/bin/ffmpeg.exe`
  - Scope: bundled FFmpeg runtime tool for Windows portable builds.
  - Source/license: tracked with `tools/ffmpeg/LICENSE`.
  - Release decision: keep only when the selected release profile intentionally
    bundles FFmpeg.

- `tools/ffmpeg/bin/ffplay.exe`
  - Scope: bundled FFmpeg playback helper for Windows portable builds.
  - Source/license: tracked with `tools/ffmpeg/LICENSE`.
  - Release decision: keep only when the selected release profile intentionally
    bundles ffplay.

- `tools/ffmpeg/bin/ffprobe.exe`
  - Scope: bundled FFmpeg probing helper for runtime diagnostics and exports.
  - Source/license: tracked with `tools/ffmpeg/LICENSE`.
  - Release decision: keep only when the selected release profile intentionally
    bundles ffprobe.
