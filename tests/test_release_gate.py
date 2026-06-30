from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_package_smoke_ci_launches_built_app_and_uploads_logs() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "smoke_launch_app.ps1" in workflow
    assert "Release worktree gate" in workflow
    assert r".\scripts\check_release_worktree.ps1 -FailOnModified" in workflow
    assert "tests/test_release_smoke.py" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "package-smoke-logs" in workflow
    assert "Tee-Object -FilePath data/tmp/package-smoke/pyinstaller.log" in workflow
    assert "Tee-Object -FilePath data/tmp/package-smoke/launch.log" in workflow
    assert "Tee-Object -FilePath data/tmp/package-smoke/release-smoke.log" in workflow


def test_smoke_launch_script_supports_source_and_arguments() -> None:
    script = (PROJECT_ROOT / "scripts" / "smoke_launch_app.ps1").read_text(encoding="utf-8")

    assert "[CmdletBinding()]" in script
    assert "[string[]]$ArgumentList" in script
    assert "[switch]$Source" in script
    assert '$ArgumentList = @("main.py") + $ArgumentList' in script
    assert "$StartProcessArgs.ArgumentList = $ArgumentList" in script
    assert "WorkingDirectory = $ProjectRoot" in script


def test_release_worktree_gate_checks_untracked_source_and_plugins() -> None:
    script = (PROJECT_ROOT / "scripts" / "check_release_worktree.ps1").read_text(encoding="utf-8")
    build_script = (PROJECT_ROOT / "scripts" / "build_portable.ps1").read_text(encoding="utf-8")
    checklist = (PROJECT_ROOT / "docs" / "release_checklist.md").read_text(encoding="utf-8")
    portable_build = (PROJECT_ROOT / "docs" / "portable_build.md").read_text(encoding="utf-8")

    assert "ls-files -o --exclude-standard" in script
    assert 'StartsWith("plugins/")' in script
    assert "-AllowUntrackedPath" in script
    assert "[switch]$FailOnModified" in script
    assert "[switch]$SkipReleaseWorktreeCheck" in build_script
    assert "& $ReleaseWorktreeCheck -FailOnModified" in build_script
    assert "check_release_worktree.ps1 -FailOnModified" in checklist
    assert "check_release_worktree.ps1 -FailOnModified" in portable_build
    assert "-SkipReleaseWorktreeCheck" in checklist
    assert "-SkipReleaseWorktreeCheck" in portable_build


def test_public_build_rejects_internal_plugin_environment() -> None:
    build_script = (PROJECT_ROOT / "scripts" / "build_portable.ps1").read_text(encoding="utf-8")
    internal_build_script = (PROJECT_ROOT / "scripts" / "build_internal.ps1").read_text(encoding="utf-8")
    spec = (PROJECT_ROOT / "AI Player.spec").read_text(encoding="utf-8")

    assert "[switch]$AllowInternalPlugins" in build_script
    assert "Assert-PublicBuildPluginScope" in build_script
    assert "AI_PLAYER_INCLUDE_EXTRA_YTDLP_PLUGINS" in build_script
    assert "AI_PLAYER_INCLUDE_PRIVATE_TELEGRAM_PLUGIN" in build_script
    assert "AI_PLAYER_EXTRA_YTDLP_HOSTS" in build_script
    assert "Public portable builds must not include internal/private plugin configuration." in build_script
    assert "-AllowInternalPlugins" in internal_build_script
    assert "AI_PLAYER_INCLUDE_EXTRA_YTDLP_PLUGINS" in spec
    assert "AI_PLAYER_INCLUDE_PRIVATE_TELEGRAM_PLUGIN" in spec


def test_release_verify_runs_required_short_gate_and_ordered_builds() -> None:
    script = (PROJECT_ROOT / "scripts" / "release_verify.ps1").read_text(encoding="utf-8")
    checklist = (PROJECT_ROOT / "docs" / "release_checklist.md").read_text(encoding="utf-8")

    assert "[ValidateSet(\"Lite\", \"OfflineCpu\", \"Gpu\")]" in script
    assert "data\\tmp\\release-verify" in script
    assert "profile-$StepPrefix-summary.json" in script
    assert "profile_summaries" in script
    assert "UI/document/URL/Edge TTS" in script
    assert "ASR/NLLB/VieNeu local" in script
    assert "CUDA/Demucs/source separation" in script
    assert "check_release_worktree.ps1" in script
    assert '"ruff", "check", "."' in script
    assert '"pytest", "-q"' in script
    assert '"pip", "check"' in script
    assert "runtime_doctor.py" in script
    assert "workflow_smoke_check.py" in script
    assert "tests\\test_release_smoke.py" in script
    assert '$BuildOrder = @("Lite", "OfflineCpu", "Gpu")' in script
    assert "build_portable.ps1" in script
    assert "smoke_launch_app.ps1" in script
    assert "release_verify.ps1" in checklist
    assert "workflow_smoke_baseline.json" in checklist


def test_release_signing_contract_is_documented_and_guarded() -> None:
    build_script = (PROJECT_ROOT / "scripts" / "build_portable.ps1").read_text(encoding="utf-8")
    verify_script = (PROJECT_ROOT / "scripts" / "release_verify.ps1").read_text(encoding="utf-8")
    profiles = (PROJECT_ROOT / "docs" / "release_profiles.md").read_text(encoding="utf-8")
    checklist = (PROJECT_ROOT / "docs" / "release_checklist.md").read_text(encoding="utf-8")

    assert "[switch]$RequireSignature" in build_script
    assert "[switch]$RequireSignature" in verify_script
    assert "No code-signing certificates found" in build_script
    assert "Get-AuthenticodeSignature" in build_script
    assert "Assert-ValidAuthenticodeSignatures" in build_script
    assert "Enterprise Application Control policies can block unsigned builds" in build_script
    assert '$BuildArgs += "-RequireSignature"' in verify_script
    assert "require_signature = [bool]$RequireSignature" in verify_script
    assert "Public or enterprise release: require `-RequireSignature`" in profiles
    assert '"dist\\portable\\AI Player Lite\\AI Player\\AI Player.exe"' in checklist
