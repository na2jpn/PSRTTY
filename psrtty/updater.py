"""Versioned one-file Windows releases. Never execute code from an update ZIP.

The running (trusted) executable is copied as the update helper. It validates
again after exit, backs up user data, and replaces only exe + release manifest.
SHA256 detects corruption; it is not a publisher signature.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
import zipfile

MANIFEST = "var/psrtty-release.json"
LEGACY_MANIFEST = "psrtty-release.json"
MAX_BYTES = 512 * 1024 * 1024


def version_key(value: str) -> tuple[int, ...]:
    # PSRTTY's decimal-style versions: 0.02 < 0.021 < 0.03.
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,4}\.\d{1,6}", value):
        raise ValueError("バージョン形式が不正です")
    major, fraction = value.split(".")
    return int(major), int(fraction.ljust(6, "0"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_manifest(root: Path, version: str):
    version_key(version)
    data = dict(product="PSRTTY", format=1, platform="windows", version=version,
                config_schema=1, files={"psrtty.exe": sha256(root / "psrtty.exe")})
    (root / MANIFEST).parent.mkdir(parents=True, exist_ok=True)
    (root / MANIFEST).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def _safe_name(name: str):
    parts = PurePosixPath(name).parts
    reserved = {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}
    if (not parts or name.startswith("/") or "\\" in name or ":" in name or "\x00" in name
        or any(x in (".", "..") or x.endswith((" ", ".")) or x.split(".")[0].upper() in reserved for x in name.rstrip("/").split("/"))):
        raise ValueError("危険なZIPパスです")


def inspect_zip(path: Path, current_version: str, installed_root: Path | None = None) -> dict:
    version_key(current_version)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("更新ZIPが大きすぎます")
    try:
        with zipfile.ZipFile(path) as archive:
            items = archive.infolist()
            if len(items) > 64 or sum(i.file_size for i in items) > MAX_BYTES:
                raise ValueError("更新ZIPの展開サイズ／件数が上限を超えています")
            seen = set()
            for item in items:
                _safe_name(item.filename)
                canonical = item.filename.rstrip("/").casefold()
                if canonical in seen:
                    raise ValueError("ZIP内に重複パスがあります")
                seen.add(canonical)
                if stat.S_ISLNK(item.external_attr >> 16) or item.flag_bits & 1:
                    raise ValueError("リンク／暗号化ZIPは使用できません")
            manifests = [i for i in items if i.filename == MANIFEST or i.filename.endswith("/" + MANIFEST)]
            if len(manifests) != 1 or manifests[0].file_size > 16384:
                raise ValueError("PSRTTY配布ZIPではありません（マニフェストがありません）")
            m = manifests[0]
            prefix = m.filename[:-len(MANIFEST)]
            if len(PurePosixPath(prefix).parts) > 1:
                raise ValueError("配布ZIPの階層が不正です")
            data = json.loads(archive.read(m))
            if not isinstance(data, dict) or data.get("product") != "PSRTTY" or data.get("format") != 1 or data.get("platform") != "windows":
                raise ValueError("PSRTTY Windows配布ZIPではありません")
            if data.get("config_schema") != 1:
                raise ValueError("この更新機構では扱えない設定形式です")
            comparison = version_key(data.get("version"))
            same_version = comparison == version_key(current_version)
            if comparison < version_key(current_version):
                raise ValueError("旧版への更新はできません")
            if same_version and installed_root is None:
                raise ValueError("同版の検証には現在のインストール先が必要です")
            files = data.get("files")
            if not isinstance(files, dict) or set(files) != {"psrtty.exe"}:
                raise ValueError("更新対象ファイルが不正です")
            expected = {prefix + MANIFEST, prefix + "psrtty.exe"}
            permitted_dirs = {prefix, prefix + "config/", prefix + "logdata/", prefix + "var/"}
            for item in items:
                if item.is_dir() and item.filename in permitted_dirs:
                    continue
                if item.filename not in expected:
                    raise ValueError("配布ZIPに想定外のファイルがあります")
            exe_info = archive.getinfo(prefix + "psrtty.exe")
            if exe_info.file_size < 2:
                raise ValueError("EXEが空です")
            digest = hashlib.sha256()
            with archive.open(exe_info) as stream:
                first = stream.read(2)
                if first != b"MZ":
                    raise ValueError("Windows EXEではありません")
                digest.update(first)
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != files["psrtty.exe"]:
                raise ValueError("EXEのハッシュが一致しません")
            if same_version:
                current_exe = installed_root / 'psrtty.exe'
                if not current_exe.is_file(): raise ValueError('現在のEXEを確認できません')
                if sha256(current_exe) == digest.hexdigest():
                    raise ValueError('現在と同じ内容のZIPです。再インストールは不要です')
            return dict(data, prefix=prefix, repair=same_version)
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError(f"更新ZIPを検証できません: {exc}") from exc


def prepare_update(path: Path, root: Path, current_version: str) -> Path:
    for path_part in (root / "var", root / "var" / "updates", root / "var" / "backups"):
        if path_part.is_symlink() or (hasattr(path_part, "is_junction") and path_part.is_junction()):
            raise ValueError("更新作業フォルダーにリンクは使用できません")
    stage = root / "var" / "updates" / uuid.uuid4().hex
    stage.mkdir(parents=True)
    try:
        snapshot = stage / "release.zip"
        shutil.copy2(path, snapshot)
        info = inspect_zip(snapshot, current_version, root)
        (stage / "request.json").write_text(json.dumps(dict(root=str(root.resolve()), current_version=current_version, version=info["version"])), encoding="utf-8")
        return stage
    except Exception:
        shutil.rmtree(stage)
        raise


def _atomic_copy(source: Path, target: Path):
    temporary = target.with_name(target.name + ".update-tmp")
    try:
        shutil.copy2(source, temporary)
        # Windows bootloader may retain its executable briefly after the child exits.
        for attempt in range(50):
            try:
                os.replace(temporary, target)
                break
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(0.1)
    finally:
        temporary.unlink(missing_ok=True)


def migrate_settings(root: Path, old_version: str, new_version: str):
    """Migration extension point. Schema 1 requires no on-disk changes.

    Future migrations must preserve unknown settings and run inside rollback.
    Defaults/F9 are filled non-destructively by ConfigStore on load.
    """
    return


def apply_update(stage: Path, root: Path, current_version: str) -> Path:
    root = root.resolve()
    info = inspect_zip(stage / "release.zip", current_version, root)
    installed = root / MANIFEST
    if not installed.is_file() or not (root / "psrtty.exe").is_file():
        raise ValueError("更新先にPSRTTY配布ファイルがありません")
    old = json.loads(installed.read_text(encoding="utf-8"))
    if old.get("product") != "PSRTTY" or old.get("version") != current_version:
        raise ValueError("更新先のバージョンが変わっています")
    # Reject junctions/symlinks: backup and update must stay within this install.
    for name in ("config", "logdata", "var", "psrtty.exe", MANIFEST):
        target = root / name
        if target.is_symlink() or (hasattr(target, "is_junction") and target.is_junction()):
            raise ValueError("リンクされた更新先は使用できません")
    payload = stage / "payload"
    payload.mkdir(exist_ok=True)
    (payload / "var").mkdir(exist_ok=True)
    with zipfile.ZipFile(stage / "release.zip") as archive:
        for name in ("psrtty.exe", MANIFEST):
            with archive.open(info["prefix"] + name) as src, (payload / name).open("wb") as dest:
                shutil.copyfileobj(src, dest)
    backup = root / "var" / "backups" / (time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8])
    backup.mkdir(parents=True)
    shutil.copy2(root / "psrtty.exe", backup / "psrtty.exe")
    for name in ("config", "logdata", "var"):
        source = root / name
        if source.exists():
            def ignore(directory, names):
                return [x for x in names if Path(directory) == root / "var" and x in ("updates", "backups", "psrtty.lock")]
            shutil.copytree(source, backup / name, ignore=ignore, symlinks=True)
    journal = stage / "result.json"
    def record(status, error=""):
        journal.write_text(json.dumps(dict(status=status, backup=str(backup), version=info["version"], error=error), ensure_ascii=False, indent=2), encoding="utf-8")
    record("backed_up")
    replaced = []
    migration_started = False
    try:
        for name in ("psrtty.exe", MANIFEST):
            _atomic_copy(payload / name, root / name)
            replaced.append(name)
        migration_started = True
        migrate_settings(root, current_version, info["version"])
        record("succeeded")
        return backup
    except Exception as exc:
        rollback_errors = []
        # Future migrations are restricted to config; restore that snapshot too.
        try:
            if migration_started and (backup / "config").exists():
                restored = stage / "config-restore"
                shutil.copytree(backup / "config", restored, symlinks=True)
                failed = stage / "config-before-rollback"
                if (root / "config").exists():
                    os.replace(root / "config", failed)
                try:
                    os.replace(restored, root / "config")
                except Exception:
                    if failed.exists(): os.replace(failed, root / "config")
                    raise
        except Exception as restore_error:
            rollback_errors.append(str(restore_error))
        for name in reversed(replaced):
            try:
                _atomic_copy(backup / name, root / name)
            except Exception as restore_error:
                rollback_errors.append(str(restore_error))
        record("rollback_failed" if rollback_errors else "rolled_back", str(exc) + "; ".join(rollback_errors))
        raise RuntimeError(f"更新に失敗しました。バックアップ: {backup} / {exc}" + (" / 復元失敗: " + "; ".join(rollback_errors) if rollback_errors else " / 旧版へ復元済み")) from exc


def launch_updater(stage: Path, root: Path):
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        raise RuntimeError("Windows EXE版から更新してください")
    helper = stage / "psrtty-updater.exe"
    shutil.copy2(sys.executable, helper)
    env = os.environ.copy()
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen([str(helper), "--apply-update", str(stage), str(root), str(os.getpid())], cwd=stage, env=env,
                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)


def wait_for_parent(pid: int, timeout_ms=60000):
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.OpenProcess(0x00100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:  # already exited
            return
        raise OSError("PSRTTYの終了を確認できません")
    try:
        if api.WaitForSingleObject(handle, timeout_ms) != 0:
            raise TimeoutError("PSRTTYの終了待ちがタイムアウトしました。更新していません")
    finally:
        api.CloseHandle(handle)


def restart_application(root: Path):
    """Run the installed EXE only, after releasing the installation lock."""
    env = os.environ.copy()
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    token = uuid.uuid4().hex
    env['PSRTTY_RESTART_TOKEN'] = token
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    process = subprocess.Popen([str((root / 'psrtty.exe').resolve())], cwd=root, env=env,
                               creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    process.psrtty_restart_token = token
    return process


def confirm_restart(root: Path, process, timeout=45):
    """The one-file bootloader PID differs from the GUI PID: use a nonce receipt."""
    deadline = time.monotonic() + timeout
    receipt = root / 'var' / 'restart-ready.json'
    while time.monotonic() < deadline:
        try:
            data = json.loads(receipt.read_text(encoding='utf-8'))
            if data.get('token') == process.psrtty_restart_token:
                return data
        except (OSError, ValueError):
            pass
        if process.poll() is not None:
            raise RuntimeError('再起動したプロセスが画面表示前に終了しました。')
        time.sleep(.1)
    raise TimeoutError('再起動の画面表示を確認できませんでした。起動済みか確認してください。')


def report_startup(root: Path):
    token = os.environ.pop('PSRTTY_RESTART_TOKEN', '')
    if not re.fullmatch(r'[0-9a-f]{32}', token): return
    from . import __version__
    receipt = root / 'var' / 'restart-ready.json'
    temp = receipt.with_suffix('.tmp')
    temp.write_text(json.dumps(dict(token=token, version=__version__, pid=os.getpid())), encoding='utf-8')
    os.replace(temp, receipt)


def helper_main(args):
    import ctypes
    from PySide6.QtCore import QLockFile
    stage, root, pid = Path(args[0]).resolve(), Path(args[1]).resolve(), int(args[2])
    lock = None
    try:
        request = json.loads((stage / "request.json").read_text(encoding="utf-8"))
        if Path(request["root"]).resolve() != root or stage.parent != root / "var" / "updates":
            raise ValueError("更新先が一致しません")
        wait_for_parent(pid)
        lock = QLockFile(str(root / "var" / "psrtty.lock"))
        lock.setStaleLockTime(0)
        if not lock.tryLock(3000):
            raise RuntimeError("別のPSRTTYが実行中です。更新していません")
        backup = apply_update(stage, root, request["current_version"])
        message = f"Ver{request['version']}への更新が完了しました。\\nバックアップ: {backup}\\npsrtty.exeを起動してください。"
        code = 0
    except Exception as exc:
        message = str(exc)
        (stage / "helper-error.txt").write_text(message, encoding="utf-8")
        code = 1
    finally:
        if lock: lock.unlock()
    if code == 0:
        try:
            process = restart_application(root)
            receipt = confirm_restart(root, process)
            (stage / 'restart-result.json').write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            return 0
        except Exception as exc:
            message = f'更新は完了しましたが、自動再起動に失敗しました。\n{root / "psrtty.exe"} を起動してください。\nバックアップ: {backup}\n{exc}'
            (stage / 'restart-error.txt').write_text(message, encoding='utf-8')
            code = 2
    ctypes.windll.user32.MessageBoxW(None, message.replace("\\n", "\n"), "PSRTTY 更新", 0x10)
    return code


def retire_legacy_manifest(root: Path, current_version: str):
    """After a manual 0.02 upgrade, archive the obsolete root manifest."""
    legacy = root / LEGACY_MANIFEST
    if not legacy.exists():
        return
    for target in (legacy, root / "var", root / "var/backups", root / MANIFEST):
        if target.is_symlink() or (hasattr(target, "is_junction") and target.is_junction()):
            raise ValueError("旧版情報の移動先にリンクは使用できません")
    old = json.loads(legacy.read_text(encoding="utf-8"))
    new = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    if (old.get("product") != "PSRTTY" or new.get("product") != "PSRTTY"
        or new.get("version") != current_version
        or version_key(old.get("version")) >= version_key(current_version)
        or new.get("files", {}).get("psrtty.exe") != sha256(root / "psrtty.exe")):
        raise ValueError("旧版JSONと現在のEXEを確認できません。旧JSONを保持しました")
    backup = root / "var/backups" / ("legacy_manifest_" + uuid.uuid4().hex)
    backup.mkdir(parents=True)
    shutil.move(str(legacy), str(backup / LEGACY_MANIFEST))
