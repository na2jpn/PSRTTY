"""Build the only ZIP layout accepted by the in-app updater."""
from pathlib import Path
import sys
import os
import shutil
import tempfile
import zipfile
from psrtty import __version__
from psrtty.updater import MANIFEST, create_manifest, inspect_zip, release_files


def package_release(root: Path):
    if __version__ in ('1.02', '1.03', '1.04', '1.05', '1.06', '1.07', '1.08') and (root / 'docs' / 'DISTRIBUTION_TERMS.txt').is_file():
        # The already-distributed 1.01 EXE expects this exact root path.
        # The new EXE removes this identical copy on first launch.
        shutil.copy2(root / 'docs' / 'DISTRIBUTION_TERMS.txt', root / 'DISTRIBUTION_TERMS.txt')
    create_manifest(root, __version__)
    archive = Path(str(root) + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for folder in ('config', 'logdata', 'var'):
            z.writestr(f'{root.name}/{folder}/', b'')
        for name in (*release_files(root), MANIFEST):
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
        source = Path('lib/hamlib')
        if source.is_dir():
            if Path('docs/DISTRIBUTION_TERMS.txt').is_file():
                (root / 'docs').mkdir(parents=True, exist_ok=True)
                shutil.copy2('docs/DISTRIBUTION_TERMS.txt', root / 'docs/DISTRIBUTION_TERMS.txt')
            (root / source).mkdir(parents=True)
            for item in source.iterdir():
                if item.is_file(): shutil.copy2(item, root / source / item.name)
        for pattern in ('INTEGRATION_107_*.html', 'ZLOG_SAMPLE*.adi', 'ZLOG_SAMPLES_README.txt'):
            for item in Path('docs').glob(pattern):
                (root / 'docs').mkdir(exist_ok=True)
                shutil.copy2(item, root / 'docs' / item.name)
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
