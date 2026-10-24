from __future__ import annotations

import ast
import json
from pathlib import Path

from ai_player.configuration import AppConfig
from ai_player.ui import player_window_utils as utils
from ai_player.ui.user_guide_text import GUIDE_TEXT


def test_repair_mojibake_repairs_common_vietnamese_text() -> None:
    assert utils.repair_mojibake("KhÃ´ng") == "Không"


def test_user_guide_text_has_no_repairable_mojibake() -> None:
    changed = [
        (path, value)
        for path, value in _walk_strings("GUIDE_TEXT", GUIDE_TEXT)
        if utils.repair_mojibake(value) != value
    ]

    assert changed == []


def test_ai_player_python_strings_have_no_repairable_mojibake() -> None:
    changed = [
        (path.as_posix(), location, value)
        for path in sorted(Path("ai_player").rglob("*.py"))
        for location, value in _python_string_literals(path)
        if not _is_mojibake_repair_helper_marker(path, location) and utils.repair_mojibake(value) != value
    ]

    assert changed == []


def test_html_with_breaks_escapes_and_preserves_lines() -> None:
    assert utils.html_with_breaks("<a>\nb") == "&lt;a&gt;<br>b"


def test_format_bitrate_for_mbps() -> None:
    assert utils.format_bitrate(2_500_000) == "2.50 Mbps"
    assert utils.format_bitrate(float("inf"), unknown="unknown") == "unknown"
    assert utils.format_bitrate(float("nan"), unknown="unknown") == "unknown"


def test_format_rate_fraction() -> None:
    assert utils.format_rate("30000/1001") == "29.97"
    assert utils.format_rate("inf/1", unknown="unknown") == "unknown"
    assert utils.format_rate("1/inf", unknown="unknown") == "unknown"


def test_safe_native_dubbing_config_forces_cpu_when_cuda_is_disabled(monkeypatch) -> None:
    monkeypatch.setenv("AI_PLAYER_DISABLE_CUDA", "1")
    config = AppConfig(local_translation_device="cuda", whisper_device="cuda", vieneu_tts_device="cuda")

    safe = utils.safe_native_dubbing_config(config)

    assert safe.local_translation_device == "cpu"
    assert safe.whisper_compute_type == "int8"


def test_safe_native_dubbing_config_keeps_cuda_when_runtime_is_ready(monkeypatch) -> None:
    monkeypatch.delenv("AI_PLAYER_DISABLE_CUDA", raising=False)
    monkeypatch.setattr(utils, "ctranslate2_cuda_available", lambda: True)
    monkeypatch.setattr(utils, "torch_cuda_available", lambda: True)
    config = AppConfig(local_translation_device="cuda", whisper_device="cuda", vieneu_tts_device="cuda")

    assert utils.safe_native_dubbing_config(config) == config


def test_safe_native_dubbing_config_falls_back_per_runtime(monkeypatch) -> None:
    monkeypatch.delenv("AI_PLAYER_DISABLE_CUDA", raising=False)
    monkeypatch.setattr(utils, "ctranslate2_cuda_available", lambda: False)
    monkeypatch.setattr(utils, "torch_cuda_available", lambda: True)
    config = AppConfig(
        local_translation_device="cuda",
        whisper_device="cuda",
        whisper_compute_type="float16",
        vieneu_tts_device="cuda",
    )

    safe = utils.safe_native_dubbing_config(config)

    assert safe.whisper_device == "cpu"
    assert safe.whisper_compute_type == "int8"
    assert safe.local_translation_device == "cuda"
    assert safe.vieneu_tts_device == "cuda"


def test_safe_native_dubbing_config_auto_prefers_each_available_gpu_runtime(monkeypatch) -> None:
    monkeypatch.delenv("AI_PLAYER_DISABLE_CUDA", raising=False)
    monkeypatch.setattr(utils, "ctranslate2_cuda_available", lambda: True)
    monkeypatch.setattr(utils, "torch_cuda_available", lambda: False)

    safe = utils.safe_native_dubbing_config(AppConfig())

    assert safe.whisper_device == "auto"
    assert safe.local_translation_device == "cpu"
    assert safe.vieneu_tts_device == "cpu"


def test_gui_language_packs_have_matching_keys() -> None:
    root = Path("ai_player/resources/languages")
    vi = json.loads((root / "vietnamese/language.json").read_text(encoding="utf-8-sig"))["strings"]
    en = json.loads((root / "english/language.json").read_text(encoding="utf-8-sig"))["strings"]

    assert set(vi) == set(en)


def test_dropdown_language_packs_have_matching_values() -> None:
    root = Path("ai_player/resources/languages")
    vi_files = {path.name for path in (root / "vietnamese").glob("*.json")}
    en_files = {path.name for path in (root / "english").glob("*.json")}

    ignored = {"language.json", "aliases.json"}
    assert vi_files - ignored == en_files - ignored

    for name in sorted(vi_files - ignored):
        vi_values = _dropdown_values(root / "vietnamese" / name)
        en_values = _dropdown_values(root / "english" / name)
        assert vi_values == en_values, name


def _dropdown_values(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    options = data.get("options", data) if isinstance(data, dict) else data
    values = []
    for item in options:
        if isinstance(item, dict):
            values.append(str(item.get("value") or item.get("id") or item.get("code")))
        else:
            values.append(str(item))
    return values


def _walk_strings(path: str, value: object) -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(path, value)]
    if isinstance(value, dict):
        return [item for key, child in value.items() for item in _walk_strings(f"{path}.{key}", child)]
    if isinstance(value, list | tuple):
        return [item for index, child in enumerate(value) for item in _walk_strings(f"{path}[{index}]", child)]
    return []


def _python_string_literals(path: Path) -> list[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    strings: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.append((f"{path}:{node.lineno}", node.value))
    return strings


def _is_mojibake_repair_helper_marker(path: Path, location: str) -> bool:
    return path.as_posix() == "ai_player/ui/player_window_utils.py" and location.startswith(
        "ai_player/ui/player_window_utils.py:28"
    )
