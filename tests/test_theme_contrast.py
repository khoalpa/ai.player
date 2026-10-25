import json
from pathlib import Path

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
                "text/accent-soft": (colors["text"], colors["accent-soft"]),
                "accent-ink/accent": (colors["accent-ink"], colors["accent"]),
            }
            for pair_name, (foreground, background) in pairs.items():
                ratio = _contrast_ratio(foreground, background)
                assert ratio >= 4.5, f"{theme_name}/{mode} {pair_name} contrast is only {ratio:.2f}:1"
