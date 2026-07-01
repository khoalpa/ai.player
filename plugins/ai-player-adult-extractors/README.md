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
   When upstream `yt-dlp` already has a matching native extractor, the probe
   marks the draft with `"delegate_to_ytdlp": true`; otherwise it creates a
   generic extractor draft with `iframe_depth`, `media_patterns`, and
   `iframe_patterns`.
3. Copy the registry entry into either:
   - `yt_dlp_plugins/extractor/adult_sites_registry.json` for committed/shared sites.
   - `data/config/private/adult_sites.local.json` for private local-only sites.
4. Add `media_patterns` or `iframe_patterns` when the generic parser does not find
   media automatically.

The generic parser already checks common HTML5 and player patterns such as
`contentUrl`, `streamUrl`, `hlsUrl`, `mp4Url`, `videoSrc`, media attributes, and
`data-player-url` iframe embeds. It also handles common `jwplayer().setup(...)`
and `videojs().src(...)` payloads, quality keys such as `quality_720p`, and
iframe attributes like `data-iframe`, `data-embed-url`, and `data-player-src`.

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

For hosts already supported by upstream `yt-dlp`, add the domains to the registry
with `"delegate_to_ytdlp": true`. This lets AI Player accept the URL and pass it
to the native `yt-dlp` extractor instead of the generic adult parser.
Current delegated host groups include mainstream tube/creator sites such as
Eporner, ManyVids, ThisVid, Tube8, YouJizz, PornTube, Nuvid, PornoXO,
Rule34Video, FC2, AlphaPorno, HellPorno, LoveHomePorn, NubilesPorn, PeekVids,
PlayVids, Pornbox, PornerBros, PornFlip, Pornotube, PornTop, Txxx-family hosts,
XXXYMovies, ZenPorn, MyVidster, Murrtube, Toypics, and the previously added major
tube/live hosts. JAV/Asia hosts without a native extractor should start as
generic registry entries and graduate to a site-specific extractor only when
probing shows token or multi-step player requirements.

Run the source/dev app with the private host list:

```bat
D:\project\ai-player-adult-extractors\run_ai_player_internal.bat
```
