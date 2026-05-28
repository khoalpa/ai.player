# -*- mode: python ; coding: utf-8 -*-
from importlib.util import find_spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

project_root = Path(SPECPATH).resolve()
datas = [
    (str(project_root / "ai_player" / "resources"), "ai_player\\resources"),
    (
        str(project_root / "ai_player" / "vieneu_tts" / "vieneu" / "assets"),
        "ai_player\\vieneu_tts\\vieneu\\assets",
    ),
]
binaries = []
hiddenimports = []
hiddenimports += ["yt_dlp_plugins.extractor.adult_sites"]

tmp_ret = collect_all("edge_tts")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]
hiddenimports += collect_submodules("yt_dlp_plugins")

if find_spec("telethon") is not None:
    hiddenimports += collect_submodules("telethon")


def _runtime_module(module_name):
    return ".tests" not in module_name and not module_name.endswith(".tests")


for package_name in ("demucs", "dora", "julius"):
    if find_spec(package_name) is not None:
        hiddenimports += collect_submodules(package_name, filter=_runtime_module)


a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DExtras",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DRender",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtDesigner",
        "PySide6.QtGraphs",
        "PySide6.QtGraphsWidgets",
        "PySide6.QtHelp",
        "PySide6.QtLocation",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtQuick3D",
        "PySide6.QtQuickControls2",
        "PySide6.QtWebChannel",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebView",
        "PySide6.scripts",
        "dora.tests",
        "torch.fx.passes.tests",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AI Player",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AI Player',
)
