# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from PySide6.QtCore import QLibraryInfo
from pathlib import Path
qt_lang_dir=Path(QLibraryInfo.path(QLibraryInfo.TranslationsPath))
qt_languages=[(str(qt_lang_dir/('qtbase_'+x+'.qm')),'assets/qt-translations') for x in ('ja','ru','zh_CN','ko','id','th','es') if (qt_lang_dir/('qtbase_'+x+'.qm')).is_file()]

hidden = collect_submodules('sounddevice') + collect_submodules('serial')

a = Analysis(
    ['psrtty.py'],
    pathex=[],
    binaries=[],
    datas=qt_languages+[
           ('assets/psrtty.png', 'assets'),
           ('assets/psrtty.ico', 'assets'),
           ('assets/amateur_radio_100.png', 'assets'),
           ('psrtty/data/contest_prefixes.json','psrtty/data'),
           ('psrtty/data/contest_prefixes_LICENSE.txt','psrtty/data'),
           ('psrtty/data/club_db.csv','psrtty/data'),
           ('psrtty/data/club_db_meta.json','psrtty/data')] + collect_data_files('sounddevice'),
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
