from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("layer", ["domain", "application"])
def test_inner_layers_do_not_import_platform_or_provider_implementations(layer):
    prohibited = ("PySide6", "torch", "transformers", "ai_player.adapters", "ai_player.ui", "ai_player.workers")
    violations = []
    for path in (ROOT / "ai_player" / layer).rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            modules = []
            if isinstance(node, ast.ImportFrom):
                modules.append(node.module or "")
            elif isinstance(node, ast.Import):
                modules.extend(item.name for item in node.names)
            if any(name == prefix or name.startswith(prefix + ".") for name in modules for prefix in prohibited):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, violations


def test_workflow_modules_load_without_qt_or_inference_frameworks():
    code = (
        "import sys; from ai_player.application.workflows import realtime, export, document, meeting, sources; "
        "assert not {'PySide6', 'torch', 'transformers', 'ctranslate2'} & set(sys.modules)"
    )
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True, capture_output=True, timeout=20)


def test_main_window_only_inherits_the_qt_shell():
    tree = ast.parse((ROOT / "ai_player/ui/player_window.py").read_text(encoding="utf-8"))
    window = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PlayerWindow")
    assert [ast.unparse(base) for base in window.bases] == ["QMainWindow"]


def test_config_sections_are_complete_disjoint_and_immutable():
    from dataclasses import FrozenInstanceError, fields

    from ai_player.configuration import AppConfig

    config = AppConfig()
    sections = [base for base in AppConfig.__bases__]
    names = [field.name for section in sections for field in fields(section)]
    assert len(names) == len(set(names)) == len(fields(AppConfig))
    assert config.tts.tts_voice == config.tts_voice
    with pytest.raises(FrozenInstanceError):
        config.tts.tts_voice = "changed"
