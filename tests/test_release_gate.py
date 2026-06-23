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
