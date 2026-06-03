# AI Player Plugin Policy

Use this policy before adding, committing, or packaging optional plugin code.

## Public Releases

- Public builds must not bundle private extractor or authenticated-client
  plugins by default.
- Keep `AI_PLAYER_INCLUDE_EXTRA_YTDLP_PLUGINS` and
  `AI_PLAYER_INCLUDE_PRIVATE_TELEGRAM_PLUGIN` unset for public builds.
- Before publishing, review untracked files under `plugins\` with
  `git ls-files -o --exclude-standard plugins` and either commit only intended
  public plugin packages or move private packages outside the repository.
- Public docs may mention optional plugin support, but must not include private
  host lists, private credentials, session files, or internal package paths.

## Internal Releases

- Internal builds may use `scripts\build_internal.ps1` and explicit plugin
  package paths.
- Internal builds must set private plugin environment flags only for the build
  command that needs them.
- Each included private plugin needs one smoke check against a representative
  source before distribution.
- Internal artifacts must not be uploaded or renamed as public release artifacts.

## Repository Hygiene

- Treat `plugins\` packages as source, not generated output. If a plugin belongs
  in the repository, commit its tests/docs/package metadata deliberately.
- Keep private runtime data such as Telegram sessions, API credentials, cookies,
  downloaded media, and generated caches under ignored runtime directories.
- Review plugin license and site policy separately from the Python dependency
  audit; `pip-audit` does not cover extractor behavior or website terms.
