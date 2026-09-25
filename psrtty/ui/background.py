"""Run blocking I/O without touching Qt objects from worker threads."""
import queue
import threading
from PySide6.QtCore import QObject, QTimer


class BackgroundJob(QObject):
    def __init__(self, parent, work, done):
        super().__init__(parent)
        self.results = queue.Queue()
        self.done = done
        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._poll)
        results = self.results
        def run():
            try:
                results.put((work(), None))
            except Exception as exc:
                results.put((None, exc))
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        self.timer.start()

    def _poll(self):
        try:
            result, error = self.results.get_nowait()
        except queue.Empty:
            return
        self.timer.stop()
        self.done(result, error)
        self.deleteLater()
