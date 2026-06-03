# AI Player Telegram Client

Private Telethon-backed Telegram user-client integration for internal AI Player builds.

Install into the AI Player virtual environment:

```powershell
D:\project\ai.player\.venv\Scripts\python.exe -m pip install D:\project\ai-player-telegram-client
```

Build AI Player internal with Telegram support:

```powershell
cd D:\project\ai.player
.\scripts\build_internal.ps1 `
  -PrivateTelegramPackage D:\project\ai-player-telegram-client `
  -PrivateYtdlpPluginPackage D:\project\ai-player-adult-extractors `
  -ExtraYtdlpHosts "missav.ai,missav.com,missav.ws,supjav.com,javmost.com,javmost.cx,javgg.net,javgg.to,r18.com,javlibrary.com,javhd.com,livejasmin.com,buomtv.*,*.buomtv.*"
```

The plugin stores protected login metadata and the Telethon session under AI Player's private config area:

```text
data/config/private/telegram
```
