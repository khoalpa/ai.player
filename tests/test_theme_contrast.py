import json
from pathlib import Path

import pytest

TOKENS_PATH = Path(__file__).parents[1] / "ai_player" / "resources" / "themes" / "tokens.json"


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def test_all_theme_text_roles_have_accessible_contrast() -> None:
    tokens = json.loads(TOKENS_PATH.read_text(encoding="utf-8"))

    for theme_name, theme in tokens["themes"].items():
        for mode, colors in theme.items():
            pairs = {
                "text/panel": (colors["text"], colors["panel"]),
                "muted/panel": (colors["muted"], colors["panel"]),
                "disabled/panel": (colors["disabled"], colors["panel"]),
                "text/surface-button-hover": (colors["text"], colors["surface"]),
                "text/accent-soft": (colors["text"], colors["accent-soft"]),
                "accent-ink/accent": (colors["accent-ink"], colors["accent"]),
                "accent-ink/accent-hover": (colors["accent-ink"], colors["accent-hover"]),
            }
            for pair_name, (foreground, background) in pairs.items():
                ratio = _contrast_ratio(foreground, background)
                assert ratio >= 4.5, f"{theme_name}/{mode} {pair_name} contrast is only {ratio:.2f}:1"


def test_qt_theme_explicitly_colours_native_dialog_children(monkeypatch: pytest.MonkeyPatch) -> None:
    """Native dark palettes must not leak white text into light styled dialogs."""
    from ai_player.resources.themes import python_theme

    monkeypatch.setattr(
        python_theme,
        "values",
        lambda: {
            **json.loads(TOKENS_PATH.read_text(encoding="utf-8"))["themes"]["neutral"]["light"],
            **json.loads(TOKENS_PATH.read_text(encoding="utf-8"))["status"]["light"],
            **json.loads(TOKENS_PATH.read_text(encoding="utf-8"))["styles"]["minimal"],
            **json.loads(TOKENS_PATH.read_text(encoding="utf-8"))["density"]["comfortable"],
        },
    )

    stylesheet = python_theme.qt_stylesheet()

    assert "QMessageBox, QMessageBox QLabel { color:#172033; background-color:#ffffff; }" in stylesheet
    assert "QLabel, QStatusBar, QTabBar, QToolButton, QAbstractButton { color:#172033; }" in stylesheet
    assert "color:#172033; background:#ffffff; border:1px solid #c7ced9;" in stylesheet
    assert "QLabel:disabled, QLineEdit:disabled" in stylesheet


@pytest.mark.parametrize("theme_name", ["neutral", "player", "paper"])
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_qt_legacy_palette_maps_to_semantic_theme_roles(
    monkeypatch: pytest.MonkeyPatch,
    theme_name: str,
    mode: str,
) -> None:
    from ai_player.resources.themes import python_theme

    tokens = json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
    selected = {
        **tokens["themes"][theme_name][mode],
        **tokens["status"][mode],
        **tokens["styles"]["minimal"],
        **tokens["density"]["comfortable"],
    }
    monkeypatch.setattr(python_theme, "values", lambda: selected)

    stylesheet = python_theme.qt_stylesheet(
        """
        QPushButton#primary { background:#146c63; color:#ffffff; }
        QLabel#warning { background:#fff7e8; color:#7a4b00; }
        QLabel#error { background:#fff1f2; color:#9f1239; }
        QFrame#card { background:#ffffff; border:1px solid #d8dee7; }
        """
    )

    assert f"background:{selected['accent']}; color:{selected['accent-ink']};" in stylesheet
    assert f"background:{selected['warning-soft']}; color:{selected['warning']};" in stylesheet
    assert f"background:{selected['danger-soft']}; color:{selected['danger']};" in stylesheet
    assert f"background:{selected['panel']}; border:1px solid {selected['border']};" in stylesheet
    assert "#146c63" not in stylesheet
    assert "#fff7e8" not in stylesheet


def test_qt_theme_exposes_focus_for_keyboard_operated_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_player.resources.themes import python_theme

    stylesheet = python_theme.qt_stylesheet()

    assert "QTextEdit:focus" in stylesheet
    assert "QComboBox:focus" in stylesheet
    assert "QAbstractItemView:focus" in stylesheet
