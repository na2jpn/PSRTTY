"""Build the only ZIP layout accepted by the in-app updater."""
from pathlib import Path
import sys
import os
import shutil
import tempfile
import zipfile
from psrtty import __version__
from psrtty.updater import MANIFEST, create_manifest, inspect_zip


def package_release(root: Path):
    create_manifest(root, __version__)
    archive = Path(str(root) + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for folder in ('config', 'logdata', 'var'):
            z.writestr(f'{root.name}/{folder}/', b'')
        for name in ('psrtty.exe', MANIFEST):
            z.write(root / name, f'{root.name}/{name}')
    inspect_zip(archive, '0.00')
    return archive


def build_distribution(executable: Path, output: Path):
    """Only a verified ZIP is published; private staging is always cleaned."""
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="psrtty-build-") as td:
        root = Path(td) / f"PSRTTY_{__version__}"
        root.mkdir()
        shutil.copy2(executable, root / 'psrtty.exe')
        archive = package_release(root)
        target = output / archive.name
        fd, temp_name = tempfile.mkstemp(prefix='.psrtty-', suffix='.tmp', dir=output)
        os.close(fd)
        temporary = Path(temp_name)
        try:
            shutil.copy2(archive, temporary)
            inspect_zip(temporary, '0.00')
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return target.resolve()


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--build':
        print(build_distribution(Path(sys.argv[2]), Path(sys.argv[3])))
    else:
        print(package_release(Path(sys.argv[1]).resolve()))
