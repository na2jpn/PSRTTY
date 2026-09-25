"""Keep fixture files and mocks alive until asynchronous shutdown completes."""
import time
from PySide6.QtCore import QCoreApplication, QEvent
from psrtty.ui.background import BackgroundJob


def close_and_wait(window, app, timeout=5.0):
    window.close()
    deadline=time.monotonic()+timeout
    while True:
        app.processEvents()
        # Completion callbacks are delivered by each job's Qt timer.
        jobs=window.findChildren(BackgroundJob)
        pending=any(job.thread.is_alive() or job.timer.isActive() for job in jobs)
        finished=(window.exit_backup_done and not window.audio_input_busy
                  and not window.audio._tx_active and not pending)
        if finished:
            QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
            return
        if time.monotonic()>=deadline:
            raise AssertionError('終了処理が5秒以内に完了しませんでした。一時ログ削除前に停止しました。')
        time.sleep(.005)
