from __future__ import annotations

from ai_player.core import config


def test_project_root_env_override(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AI_PLAYER_PROJECT_ROOT", str(tmp_path))

    assert config._resolve_project_root() == tmp_path.resolve()


def test_frozen_project_root_uses_portable_launcher_root(monkeypatch, tmp_path) -> None:
    portable_root = tmp_path / "AI Player Lite"
    app_dir = portable_root / "AI Player"
    app_dir.mkdir(parents=True)
    (portable_root / "Run AI Player.bat").write_text("", encoding="utf-8")
    executable = app_dir / "AI Player.exe"
    executable.write_text("", encoding="utf-8")
    monkeypatch.delenv("AI_PLAYER_PROJECT_ROOT", raising=False)
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config.sys, "executable", str(executable))

    assert config._resolve_project_root() == portable_root.resolve()


def test_frozen_project_root_falls_back_to_executable_dir(monkeypatch, tmp_path) -> None:
    app_dir = tmp_path / "AI Player"
    app_dir.mkdir()
    executable = app_dir / "AI Player.exe"
    executable.write_text("", encoding="utf-8")
    monkeypatch.delenv("AI_PLAYER_PROJECT_ROOT", raising=False)
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config.sys, "executable", str(executable))

    assert config._resolve_project_root() == app_dir.resolve()
