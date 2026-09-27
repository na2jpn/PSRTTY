"""Pin official Hamlib 4.7.2 Windows x64 assets for a PSRTTY source build.

Accept local copies with --binary/--source in disconnected environments. The
release hashes are published at https://github.com/Hamlib/Hamlib/releases/tag/4.7.2
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import tempfile
from urllib.request import urlopen
import zipfile

ASSETS = {
    'hamlib-w64-4.7.2.zip': '8553bc6c5c6032e8debf99c017e98f58fed7e07e7c25d04815dc3e8bbe3304c7',
    'hamlib-4.7.2.tar.gz': 'ae1fcf2dbc80ea0786ea8f047b09399c3f7737d1930442f61a031708ed33e88f',
}
BASE='https://github.com/Hamlib/Hamlib/releases/download/4.7.2/'
RUNTIME_DLLS={'libhamlib-4.dll','libusb-1.0.dll','libwinpthread-1.dll'}


def acquire(name, local, folder):
    target=folder/name
    if local:
        shutil.copy2(local,target)
    else:
        with urlopen(BASE+name,timeout=60) as src, target.open('wb') as dest:
            shutil.copyfileobj(src,dest)
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    if digest!=ASSETS[name]:
        raise ValueError(f'{name}：公式発表のSHA-256と一致しません。{digest}')
    return target


def prepare(binary=None,source=None,root=None):
    root=Path(root or Path(__file__).resolve().parent)
    destination=root/'lib/hamlib';destination.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='hamlib-verified-') as td:
        cache=Path(td)
        archive=acquire('hamlib-w64-4.7.2.zip',binary,cache)
        tarball=acquire('hamlib-4.7.2.tar.gz',source,cache)
        with zipfile.ZipFile(archive) as z:
            names={Path(name).name:name for name in z.namelist() if not name.endswith('/')}
            for name in names:
                if name in RUNTIME_DLLS and '/bin/' in '/'+names[name].replace('\\','/'):
                    pass
                elif name in ('LICENSE.txt','COPYING.LIB.txt','COPYING.txt','README.w64-bin.txt'):
                    pass
                else:
                    continue
                if '..' in Path(names[name]).parts:raise ValueError('危険なHamlibアーカイブです')
                (destination/name).write_bytes(z.read(names[name]))
        if not all((destination/name).is_file() for name in RUNTIME_DLLS) or not (destination/'COPYING.LIB.txt').is_file():
            raise ValueError('HamlibのDLL・依存DLLまたはLGPL本文を確認できません。')
        # libgcc is not imported by the three runtime DLLs in this release.
        (destination/'libgcc_s_seh-1.dll').unlink(missing_ok=True)
        shutil.copy2(tarball,destination/tarball.name)
    (destination/'VERSION.txt').write_text('4.7.2\n',encoding='ascii')
    (destination/'THIRD_PARTY_NOTICES.txt').write_text(
        'Hamlib 4.7.2 - https://github.com/Hamlib/Hamlib/releases/tag/4.7.2\n'
        'libhamlib-4.dll: LGPL-2.1-or-later. LICENSE.txt / COPYING.LIB.txt を参照。\n'
        '対応するHamlibソース: hamlib-4.7.2.tar.gz（このフォルダー内）。\n'
        'libusb-1.0.dll: LGPL-2.1-or-later. COPYING.LIB.txt を参照。'
        'ソース: https://github.com/libusb/libusb\n'
        'libwinpthread-1.dll: MinGW-w64 winpthreads。MIT方式とLockless Inc.のBSD方式の通知は'
        ' WINPTHREADS_NOTICE.txt を参照。ソース: https://www.mingw-w64.org/source/\n'
        'DLLは同じフォルダー内の互換版と交換できます。\n',encoding='utf-8')
    return destination


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--binary');parser.add_argument('--source')
    args=parser.parse_args();print(prepare(args.binary,args.source))
