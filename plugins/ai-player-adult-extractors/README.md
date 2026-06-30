# AI Player Adult Extractors

Private yt-dlp plugin package for internal AI Player builds.

Install locally:

```powershell
.\.venv\Scripts\python.exe -m pip install -e D:\project\ai-player-adult-extractors
```

Build AI Player internal:

```powershell
.\scripts\build_internal.ps1 `
  -PrivateYtdlpPluginPackage D:\project\ai-player-adult-extractors
```

The build script reads `yt_dlp_plugins/extractor/adult_sites_registry.json` and fills
`AI_PLAYER_EXTRA_YTDLP_HOSTS` automatically. Add new mirrors there first, then add or
update the matching extractor tests.

Add a new site without code changes:

1. Run a probe against a sample URL:

   ```powershell
   .\.venv\Scripts\python.exe .\scripts\probe_adult_site.py "https://example.test/watch/demo" --site-key example
   ```

2. Review the redacted HTML fixture and generated registry draft under
   `data\tmp\adult-site-probe`.
3. Copy the registry entry into either:
   - `yt_dlp_plugins/extractor/adult_sites_registry.json` for committed/shared sites.
   - `data/config/private/adult_sites.local.json` for private local-only sites.
4. Add `media_patterns` or `iframe_patterns` when the generic parser does not find
   media automatically.

Example local registry:

```json
{
  "example": {
    "domains": ["example.test", "*.example.test"],
    "iframe_depth": 2,
    "accept_language": "en-US,en;q=0.9",
    "media_patterns": ["data-stream=[\"'](?P<url>[^\"']+)[\"']"],
    "iframe_patterns": ["data-player=[\"'](?P<url>[^\"']+)[\"']"]
  }
}
```

Use a site-specific extractor only when the generic extractor cannot handle a token
API, multi-step player, login-only flow, or anti-bot behavior.

Run the source/dev app with the private host list:

```bat
D:\project\ai-player-adult-extractors\run_ai_player_internal.bat
```
