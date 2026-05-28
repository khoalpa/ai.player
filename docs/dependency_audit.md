# Dependency Audit

Run this before sharing a release build or refreshing `constraints/windows-release-py310.txt`.

## Scope

- Audit the resolved local Python environment, because optional extras pull large runtime packages that are not all present in `requirements.txt`.
- Audit `requirements.txt` as the lightweight offline/runtime install path.
- Keep generated reports under `data/tmp/dependency-audit/` so they stay out of source control.
- Review model and external tool licenses separately. `pip-audit` only covers Python package vulnerability advisories.

## Release Audit

Install the release dependency set first:

```powershell
.\.venv\Scripts\python.exe -m pip install -c constraints\windows-release-py310.txt -e ".[dev,packaging,offline-ai,gpu,audio-separation,audit]"
```

Run the audit script:

```powershell
.\scripts\audit_dependencies.ps1
```

If the audit extra has not been installed in the current environment yet:

```powershell
.\scripts\audit_dependencies.ps1 -InstallTools
```

The script writes:

- `data\tmp\dependency-audit\pip-audit-local.json`
- `data\tmp\dependency-audit\pip-audit-requirements.json`

By default the script ignores the accepted advisory `CVE-2025-69872`, which is a
`diskcache` finding pulled in by `llama-cpp-python`. AI Player depends on
`llama-cpp-python` for offline VieNeu-TTS GGUF models and optional local GGUF
transcript cleanup. The application does not configure or read shared
user-writable `diskcache` cache directories through `llama-cpp-python`; keep
model and runtime cache folders under the per-user project/runtime directories.
Remove the ignore once an upstream fixed `diskcache` release is available.

To review accepted advisories explicitly before release approval:

```powershell
.\scripts\audit_dependencies.ps1 -ReviewAcceptedVulnerabilities
```

This command audits without ignoring advisories and passes only when every
reported vulnerability is listed in `-AcceptedVulnerabilities`.

## Accepted Advisory Tracking

- Re-run the accepted-advisory review command above before every release approval.
- Keep each accepted advisory listed in this document with the affected package,
  why the current app usage is mitigated, and what upstream change should remove
  the exception.
- Remove an advisory from the default ignore list in `scripts\audit_dependencies.ps1`
  as soon as the resolved dependency set no longer reports it.

## Triage

- Fail the release on high or critical vulnerabilities unless a documented mitigation exists.
- Prefer upgrading the direct dependency and regenerating the release constraint file.
- If a finding only affects an unused optional feature, record the affected extra, the advisory id, and why the release can proceed.
- Re-run `ruff`, `pytest`, `runtime_doctor.py`, and the manual smoke checklist after dependency changes.

## Record

Add a short note to `docs/manual_smoke_results.md` or the release notes with:

- audit date
- dependency profile audited
- report paths
- unresolved advisories and mitigations
