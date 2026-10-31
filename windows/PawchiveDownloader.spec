# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

directory = Path(SPECPATH)
sys.path.insert(0, str(directory))
from build_support import without_system_icu

a = Analysis(
    [str(directory / 'download_pawchive_images.py')],
    pathex=[str(directory)],
    binaries=[],
    datas=[(str(directory / '1.ico'), '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(directory / 'runtime_windows_icu.py')],
    excludes=['PyQt5', 'PyQt6', 'PySide2'],
    noarchive=False,
)
a.binaries = without_system_icu(a.binaries)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='PawchiveDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(directory / '1.ico'),
)
