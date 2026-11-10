# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Afterburner.
Build: pyinstaller main.spec
"""

import os
from pathlib import Path

block_cipher = None

# Project root
project_dir = Path.cwd()

# Collect all skins
skin_dir = project_dir / "Skins" / "MSICyborgRed"
skin_files = []
if skin_dir.exists():
    for f in skin_dir.rglob("*"):
        if f.is_file():
            skin_files.append((str(f), str(skin_dir.relative_to(project_dir))))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        (str(skin_dir), 'Skins/MSICyborgRed'),
    ],
    hiddenimports=[
        'lh_monitor',
        'collector',
        'config',
        'pynvml',
        'psutil',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'email',
        'http',
        'xml',
        'pydoc',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Afterburner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
