"""Sign our Windows executables before release hashes/ZIP creation.

Uses the Windows certificate store (including token-backed keys); no private
key or password is stored in the source or distribution.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

DEFAULT_TIMESTAMP_URL = 'https://timestamp.digicert.com'


def find_signtool(explicit=None):
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise FileNotFoundError('SignTool not found: ' + str(path))
        return str(path.resolve())
    found = shutil.which('signtool.exe')
    if found:
        return found
    sdk = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Windows Kits/10/bin'
    candidates = list(sdk.glob('*/x64/signtool.exe'))
    candidates = [p for p in candidates if re.fullmatch(r'\d+(?:\.\d+)+', p.parent.parent.name)]
    if candidates:
        return str(max(candidates, key=lambda p: tuple(map(int, p.parent.parent.name.split('.')))))
    raise FileNotFoundError('Install Windows SDK SignTool or set PSRTTY_SIGNTOOL.')


def sign_executables(files, thumbprint, *, signtool=None,
                     timestamp_url=DEFAULT_TIMESTAMP_URL, machine_store=False):
    thumbprint = re.sub(r'\s', '', thumbprint or '')
    if not re.fullmatch(r'[0-9a-fA-F]{40}', thumbprint):
        raise ValueError('Specify the 40-digit certificate thumbprint (PSRTTY_SIGN_CERT_THUMBPRINT).')
    if not re.fullmatch(r'https?://[^\s]+', timestamp_url or ''):
        raise ValueError('Specify the RFC 3161 timestamp server URL.')
    paths = [Path(p).resolve() for p in files]
    if not paths:
        raise ValueError('No executable to sign.')
    for path in paths:
        if not path.is_file() or path.suffix.lower() != '.exe':
            raise FileNotFoundError('Executable not found: ' + str(path))
    tool = find_signtool(signtool)
    for path in paths:
        args = [tool, 'sign', '/sha1', thumbprint, '/fd', 'SHA256',
                '/tr', timestamp_url, '/td', 'SHA256',
                '/d', 'PSRTTY', '/du', 'https://2jp.org/ps/psrtty/']
        if machine_store:
            args.append('/sm')
        subprocess.run([*args, str(path)], check=True)
        # /tw also rejects a missing timestamp: SignTool warning exits nonzero.
        subprocess.run([tool, 'verify', '/pa', '/all', '/tw', '/v', str(path)], check=True)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+')
    parser.add_argument('--certificate-thumbprint', default=os.environ.get('PSRTTY_SIGN_CERT_THUMBPRINT'))
    parser.add_argument('--signtool', default=os.environ.get('PSRTTY_SIGNTOOL'))
    parser.add_argument('--timestamp-url', default=os.environ.get('PSRTTY_TIMESTAMP_URL') or DEFAULT_TIMESTAMP_URL)
    parser.add_argument('--machine-store', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('Authenticode signing requires Windows and the signing certificate.')
    sign_executables(args.files, args.certificate_thumbprint, signtool=args.signtool,
                     timestamp_url=args.timestamp_url, machine_store=args.machine_store)


if __name__ == '__main__':
    main()
