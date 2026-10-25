"""Portable adapters. Copy together with tokens.json and project.json.

AI_THEME, AI_THEME_MODE, AI_THEME_STYLE and AI_THEME_DENSITY override defaults.
Streamlit users can also select preferences in the sidebar.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


# The desktop UI predates the token system and still passes a light-theme QSS
# string into ``qt_stylesheet``.  Keep this translation table explicit: hue and
# lightness guesses cannot distinguish a brand accent from success, or a pale
# warning surface from a generic panel.
_LEGACY_QT_COLOR_ROLES = {
    "101828": "text",
    "172033": "text",
    "0b514b": "text",
    "56657a": "muted",
    "667085": "muted",
    "64748b": "disabled",
    "ffffff": "panel",
    "fbfefd": "panel",
    "f7f9fb": "surface",
    "f8fafc": "surface",
    "f6f8fb": "surface",
    "eef2f6": "raised",
    "f1f4f8": "raised",
    "d8dee7": "border",
    "c6d0dc": "border",
    "d5dde8": "border",
    "dbe2ea": "border",
    "cbd5e1": "border",
    "e1e7ef": "border-subtle",
    "e7ecf2": "border-subtle",
    "8c99aa": "border-strong",
    "91a2b4": "border-strong",
    "146c63": "accent",
    "2459c4": "accent",
    "0b76d1": "accent",
    "0f5f57": "accent-hover",
    "19479f": "accent-hover",
    "e6f3f1": "accent-soft",
    "e6edff": "accent-soft",
    "eef6f4": "success-soft",
    "e8f4ee": "success-soft",
    "237a57": "success",
    "145338": "success",
    "fff7e8": "warning-soft",
    "fff8e6": "warning-soft",
    "e9b75d": "warning",
    "e9c46a": "warning",
    "7a4b00": "warning",
    "604300": "warning",
    "fff1f2": "danger-soft",
    "f0a5af": "danger",
    "e26d7a": "danger",
    "9f1239": "danger",
}


def config() -> dict:
    result = json.loads((ROOT / "project.json").read_text(encoding="utf-8"))
    data = json.loads((ROOT / "tokens.json").read_text(encoding="utf-8"))
    options = {
        "theme": data["themes"],
        "mode": ("light", "dark", "system"),
        "style": data["styles"],
        "density": data["density"],
    }
    for key, allowed in options.items():
        value = os.getenv("AI_THEME" if key == "theme" else "AI_THEME_" + key.upper(), result[key])
        if value in allowed:
            result[key] = value
    return result


def values(settings: dict | None = None) -> dict:
    settings = settings or config()
    data = json.loads((ROOT / "tokens.json").read_text(encoding="utf-8"))
    mode = settings["mode"]
    if mode == "system":
        # Native Windows preference; other hosts default to light.
        mode = "light"
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            ) as key:
                mode = "light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "dark"
        except (ImportError, OSError):
            pass
    return (
        data["themes"][settings["theme"]][mode]
        | data["status"][mode]
        | data["styles"][settings["style"]]
        | data["density"][settings["density"]]
    )


def theme_html(html: str) -> str:
    """Embed local theme assets in the FastAPI streaming client response."""
    import re

    settings = config()
    attrs = " ".join(f'data-{k}="{settings[k]}"' for k in ("theme", "mode", "style", "density"))
    html = re.sub(
        r"<html\b([^>]*)>", lambda m: "<html" + m[1] + " " + attrs + ' data-theme-app="vieneu-stream">', html, count=1
    )
    js = (ROOT / "theme.js").read_text(encoding="utf-8")
    css = (ROOT / "theme.css").read_text(encoding="utf-8")
    css += (
        ":root[data-theme] { --bg-0:var(--ui-bg); --bg-1:var(--ui-panel); --bg-2:var(--ui-surface);"
        " --surface:var(--ui-panel); --surface-2:var(--ui-surface); --border:var(--ui-border);"
        " --text-1:var(--ui-text); --text-2:var(--ui-muted); --accent-1:var(--ui-accent);"
        " --accent-2:var(--ui-warning); --accent-3:var(--ui-danger); --placeholder:var(--ui-muted); }"
    )
    css += (
        ":root[data-theme] body { font-family:var(--ui-font-sans); }"
        " :root[data-theme] .surface-card { background:var(--ui-panel);"
        " border-color:var(--ui-border); border-radius:var(--ui-radius-lg); }"
    )
    html = html.replace("<head>", "<head><script>" + js + "</script>", 1)
    return html.replace("</head>", "<style>" + css + "</style></head>", 1)


def render_streamlit() -> None:
    import streamlit as st

    settings = config()
    labels = {
        "theme": {"neutral": "Trung tính", "player": "Player", "paper": "Giấy"},
        "mode": {"system": "Theo hệ thống", "light": "Sáng", "dark": "Tối"},
        "style": {"minimal": "Tối giản", "soft": "Mềm mại", "editorial": "Biên tập"},
        "density": {"comfortable": "Thoải mái", "compact": "Gọn"},
    }
    with st.sidebar.expander("Giao diện", expanded=False):
        for key, label in (
            ("theme", "Bảng màu"),
            ("mode", "Chế độ"),
            ("style", "Phong cách"),
            ("density", "Khoảng cách"),
        ):
            opts = list(labels[key])
            settings[key] = st.selectbox(
                label, opts, index=opts.index(settings[key]), format_func=labels[key].get, key="ai_theme_" + key
            )

    # System mode follows the browser, including changes while the page is open.
    def rule(v: dict) -> str:
        return ":root {" + ";".join(f"--ui-{k}:{value}" for k, value in v.items()) + "}"

    if settings["mode"] == "system":
        css = (
            rule(values(settings | {"mode": "light"}))
            + "@media(prefers-color-scheme:dark){"
            + rule(values(settings | {"mode": "dark"}))
            + "}"
        )
    else:
        css = rule(values(settings))
    css += """
    :root {
        --studio-primary:var(--ui-accent); --studio-primary-strong:var(--ui-accent-hover);
        --studio-primary-soft:var(--ui-accent-soft); --studio-focus:var(--ui-accent);
        --studio-surface:var(--ui-panel); --studio-surface-raised:var(--ui-surface);
        --studio-text-muted:var(--ui-muted); --studio-border:var(--ui-border);
        --studio-border-soft:var(--ui-border-subtle); --studio-radius-control:var(--ui-radius-md);
        --studio-radius-surface:var(--ui-radius-lg); --studio-control-min-height:var(--ui-control-height);
        --studio-success:var(--ui-success); --studio-warning:var(--ui-warning);
        --studio-error:var(--ui-danger); --studio-info:var(--ui-info);
    }
    .stApp, [data-testid="stAppViewContainer"] { background:var(--ui-bg); color:var(--ui-text); }
    [data-testid="stHeader"], [data-testid="stSidebar"] { background:var(--ui-panel); color:var(--ui-text); }
    [data-testid="stBaseButton-primary"] {
        background:var(--ui-accent); color:var(--ui-accent-ink); border-color:var(--ui-accent);
    }
    [data-testid="stBaseButton-secondary"], [data-baseweb="input"],
    [data-baseweb="select"] > div, [data-baseweb="textarea"] {
        background:var(--ui-panel); color:var(--ui-text);
        border-color:var(--ui-border); border-radius:var(--ui-radius-md);
    }
    [data-baseweb="input"] input, textarea, [data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"] {
        color:var(--ui-text);
    }
    .stButton button { min-height:var(--ui-control-height); border-radius:var(--ui-radius-md); }
    .stApp :focus-visible { outline:2px solid var(--ui-accent); outline-offset:2px; }
    @media(prefers-reduced-motion:reduce) { .stApp * { transition:none!important; animation:none!important; } }
    """
    if settings["style"] == "editorial":
        css += '.stApp h1, .stApp h2, .stApp h3 { font-family:Georgia,"Times New Roman",serif; }'
    st.html("<style>" + css + "</style>")


def qt_stylesheet(legacy: str = "") -> str:
    """Preserve local layout rules while replacing their literal palette."""
    import colorsys
    import re

    v = values()

    def replace(match):
        color = match.group(0)[1:]
        if len(color) == 3:
            color = "".join(c * 2 for c in color)
        color = color.lower()
        rgb = [int(color[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        h, lightness, saturation = colorsys.rgb_to_hls(*rgb)
        before = match.string[max(0, match.start() - 80) : match.start()]
        prop = before.rsplit(";", 1)[-1].rsplit("{", 1)[-1].strip().split(":", 1)[0]
        if color == "ffffff" and prop in {"color", "selection-color"}:
            return v["accent-ink"]
        if role := _LEGACY_QT_COLOR_ROLES.get(color):
            return v[role]
        if prop in {"color", "selection-color"}:
            return v["accent-ink"] if lightness > 0.94 else v["text"] if lightness < 0.28 else v["muted"]
        if "border" in prop:
            return v["border"]
        if saturation > 0.45 and 0.12 < lightness < 0.9:
            role = "danger" if h < 0.045 or h > 0.93 else "warning" if h < 0.17 else "success" if h < 0.48 else "accent"
            if lightness > 0.82:
                role += "-soft"
        else:
            role = (
                "panel"
                if lightness > 0.96
                else "surface"
                if lightness > 0.89
                else "border"
                if lightness > 0.72
                else "muted"
                if lightness > 0.3
                else "text"
            )
        return v[role]

    legacy = re.sub(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", replace, legacy)
    radius = v["radius-md"]
    legacy = re.sub(r"border-radius:\s*(?!0\b)\d+px", "border-radius:" + radius, legacy)
    return (
        f"""
    QMainWindow, QWidget#root, QDialog, QMenu {{ color:{v["text"]}; background-color:{v["bg"]}; }}
    /*
       Do not rely on the native palette to propagate foreground colours.  In
       particular, Windows can keep a dark-system-palette QLabel foreground
       after a light application stylesheet has painted the dialog background.
       That produced white message-box text on a near-white background.
    */
    QLabel, QStatusBar, QTabBar, QToolButton, QAbstractButton {{ color:{v["text"]}; }}
    QMessageBox, QMessageBox QLabel {{ color:{v["text"]}; background-color:{v["panel"]}; }}
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        color:{v["text"]}; background:{v["panel"]}; border:1px solid {v["border"]}; border-radius:{radius}; padding:5px;
        placeholder-text-color:{v["muted"]};
        selection-background-color:{v["accent"]}; selection-color:{v["accent-ink"]};
    }}
    QAbstractItemView {{
        color:{v["text"]}; background:{v["panel"]}; alternate-background-color:{v["surface"]};
        border:1px solid {v["border"]}; selection-background-color:{v["accent-soft"]};
        selection-color:{v["text"]}; outline:0;
    }}
    QAbstractItemView::item {{ color:{v["text"]}; background:{v["panel"]}; padding:5px; }}
    QAbstractItemView::item:selected {{ color:{v["text"]}; background:{v["accent-soft"]}; }}
    QComboBox QAbstractItemView {{ color:{v["text"]}; background:{v["panel"]}; }}
    QCheckBox, QRadioButton, QGroupBox {{ color:{v["text"]}; }}
    QMenu::item {{ color:{v["text"]}; background:{v["panel"]}; padding:6px 18px; }}
    QMenu::item:selected {{ color:{v["text"]}; background:{v["accent-soft"]}; }}
    QPushButton {{
        color:{v["text"]}; background:{v["panel"]}; border:1px solid {v["border"]};
        border-radius:{radius}; padding:5px 10px;
    }}
    QPushButton:hover {{ background:{v["surface"]}; border-color:{v["accent"]}; }}
    QPushButton:focus, QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
    QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QAbstractItemView:focus {{
        border:2px solid {v["accent"]};
    }}
    QLabel:disabled, QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
    QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QToolButton:disabled,
    QPushButton:disabled, QCheckBox:disabled, QRadioButton:disabled {{ color:{v["disabled"]}; }}
    QToolTip {{ color:{v["text"]}; background:{v["panel"]}; border:1px solid {v["border"]}; }}
    """
        + legacy
    )


def gradio_theme(gr):
    """Use the installed Gradio theme interface with local system fonts."""
    v = values()
    return gr.themes.Base(font=["Segoe UI", "system-ui", "sans-serif"], font_mono=["Consolas", "monospace"]).set(
        body_background_fill=v["bg"],
        body_background_fill_dark=v["bg"],
        body_text_color=v["text"],
        body_text_color_dark=v["text"],
        body_text_color_subdued=v["muted"],
        body_text_color_subdued_dark=v["muted"],
        block_background_fill=v["panel"],
        block_background_fill_dark=v["panel"],
        block_border_color=v["border"],
        block_border_color_dark=v["border"],
        input_background_fill=v["panel"],
        input_background_fill_dark=v["panel"],
        input_border_color=v["border"],
        input_border_color_dark=v["border"],
        input_placeholder_color=v["muted"],
        input_placeholder_color_dark=v["muted"],
        block_radius=v["radius-lg"],
        input_radius=v["radius-md"],
        input_padding=v["control-padding"],
        block_padding=v["panel-padding"],
        button_large_radius=v["radius-md"],
        button_medium_radius=v["radius-md"],
        button_small_radius=v["radius-sm"],
        button_large_padding=v["control-padding"],
        button_medium_padding=v["control-padding"],
        button_secondary_background_fill=v["surface"],
        button_secondary_background_fill_dark=v["surface"],
        button_secondary_background_fill_hover=v["raised"],
        button_secondary_background_fill_hover_dark=v["raised"],
        button_secondary_text_color=v["text"],
        button_secondary_text_color_dark=v["text"],
        button_secondary_border_color=v["border"],
        button_secondary_border_color_dark=v["border"],
        button_primary_background_fill=v["accent"],
        button_primary_background_fill_dark=v["accent"],
        button_primary_background_fill_hover=v["accent-hover"],
        button_primary_background_fill_hover_dark=v["accent-hover"],
        button_primary_text_color=v["accent-ink"],
        button_primary_text_color_dark=v["accent-ink"],
    )
