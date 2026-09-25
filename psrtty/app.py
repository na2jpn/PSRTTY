from __future__ import annotations

import sys
from PySide6.QtGui import QIcon
from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__
from .single_instance import ActivationServer, request_activation
from .paths import resource_path, ensure_runtime_dirs, app_root
from .backup import check_log_writable
from .ui.main_window import MainWindow


def run() -> int:
    app = QApplication(sys.argv)
    log_dir = app_root() / "logdata"
    try:
        check_log_writable(log_dir)
        paths = ensure_runtime_dirs()
    except OSError as exc:
        QMessageBox.critical(None, "PSRTTY：起動できません",
            f"ログ保存先または動作フォルダーに書き込めないため、PSRTTYを起動できません。\n"
            f"ログフォルダー：{log_dir}\n対象：{exc.filename or log_dir}\n原因：{exc}\n"
            "保存先のアクセス権や空き容量を確認してください。")
        return 1
    lock = QLockFile(str(paths["var"] / "psrtty.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        if request_activation(paths['root']): return 0
        info=lock.getLockInfo()
        updating=bool(info[0] and 'updater' in str(info[-1]).lower())
        message=('PSRTTYはバージョンアップ処理中です。完了後に自動で再起動します。' if updating else
                 'このフォルダーのPSRTTYはすでに起動しています。起動済みのウィンドウを確認してください。')
        QMessageBox.warning(None, "PSRTTY：二重起動できません", message)
        return 1
    app.setApplicationName("PSRTTY")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(resource_path("assets/psrtty.png"))))
    if getattr(sys, "frozen", False):
        from .updater import retire_legacy_manifest
        try:
            retire_legacy_manifest(paths["root"], __version__)
        except Exception as exc:
            QMessageBox.warning(None, "旧版情報の整理", f"旧JSONを移動できませんでした。データは残しています。\n{exc}")
    win = MainWindow(reset_window="--reset-window" in sys.argv)
    activation=ActivationServer(paths["root"],win)
    win.show()
    def started():
        from .updater import report_startup
        try:
            report_startup(paths['root'])
        except OSError as exc:
            win.statusBar().showMessage(f'再起動確認の記録に失敗: {exc}', 10000)
    QTimer.singleShot(0, win, started)
    result=app.exec()
    activation.server.close()
    lock.unlock()
    return result
