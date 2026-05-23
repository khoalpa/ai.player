# Portable Build

The restored repository includes a minimal portable build script.

```powershell
.\scripts\build_portable.ps1
```

The output is written to `dist\portable\AI Player Lite`. The Lite package does not bundle local model folders.
When run from `Run AI Player.bat`, runtime data and optional `models\` / `tools\` folders are resolved relative to the `AI Player Lite` folder.
