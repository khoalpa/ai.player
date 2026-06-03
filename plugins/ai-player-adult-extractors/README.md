# AI Player Adult Extractors

Private yt-dlp plugin package for internal AI Player builds.

Install locally:

```powershell
.\.venv\Scripts\python.exe -m pip install -e D:\project\ai-player-adult-extractors
```

Build AI Player internal:

```powershell
.\scripts\build_internal.ps1 `
  -PrivateYtdlpPluginPackage D:\project\ai-player-adult-extractors `
  -ExtraYtdlpHosts "missav.ai,missav.com,missav.ws,supjav.com,javmost.com,javmost.cx,javgg.net,javgg.to,r18.com,javlibrary.com,javhd.com,livejasmin.com,buomtv.*,*.buomtv.*"
```

Run the source/dev app with the private host list:

```bat
D:\project\ai-player-adult-extractors\run_ai_player_internal.bat
```
