# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from PySide6.QtCore import QLibraryInfo
from pathlib import Path
qt_lang_dir=Path(QLibraryInfo.path(QLibraryInfo.TranslationsPath))
qt_languages=[(str(qt_lang_dir/('qtbase_'+x+'.qm')),'assets/qt-translations') for x in ('ja','ru','zh_CN','ko','id','th','es') if (qt_lang_dir/('qtbase_'+x+'.qm')).is_file()]

hidden = collect_submodules('sounddevice') + collect_submodules('serial')
import sys
if sys.platform == 'win32':
    hidden += collect_submodules('pycaw') + collect_submodules('comtypes')

a = Analysis(
    ['psrtty.py'],
    pathex=[],
    binaries=[],
    datas=qt_languages+[
           ('assets/psrtty.png', 'assets'),
           ('assets/psrtty.ico', 'assets'),
           ('assets/amateur_radio_100.png', 'assets'),
           ('assets/audio_usb_examples.png', 'assets'),
           ('assets/hamlog_rst599.png', 'assets'),
           ('assets/ry_skimmer.png', 'assets'),
           ('psrtty/data/ry_radar_sources.json','psrtty/data'),
           ('psrtty/data/entity_names.json','psrtty/data'),
           ('psrtty/data/entity_names_LICENSE.txt','psrtty/data'),
           ('psrtty/data/contest_prefixes.json','psrtty/data'),
           ('psrtty/data/contest_prefixes_LICENSE.txt','psrtty/data'),
           ('psrtty/data/club_db.csv','psrtty/data'),
           ('psrtty/data/club_db_meta.json','psrtty/data')] + collect_data_files('sounddevice'),
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # PSRTTY imports Widgets/Gui/Core/Network/PrintSupport; no web engine or QML.
    # Keep unittest: NumPy testing is imported by SciPy array_api_compat at runtime.
    excludes=['PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets',
              'PySide6.QtWebEngineQuick','PySide6.QtQml','PySide6.QtQuick',
              'PySide6.QtQuickWidgets','tkinter'],
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
