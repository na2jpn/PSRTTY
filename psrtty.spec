# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hidden = collect_submodules('sounddevice') + collect_submodules('serial')

a = Analysis(
    ['psrtty.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/psrtty.png', 'assets')] + collect_data_files('sounddevice'),
    hiddenimports=hidden,
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
    a.binaries,
    a.datas,
    [],
    name='psrtty',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='assets/psrtty.ico',
)
