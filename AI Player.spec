# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from importlib.util import find_spec

from PyInstaller.utils.hooks import collect_all

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
tmp_ret = collect_all('PySide6')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('edge_tts')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
for package_name in ('demucs', 'dora', 'julius', 'lameenc'):
    if find_spec(package_name) is not None:
        tmp_ret = collect_all(package_name)
        datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    [str(project_root / 'main.py')],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AI Player',
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
