"""Per-installation activation IPC. The existing QLockFile remains authoritative."""
import hashlib
import os
import time
from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def endpoint(root):
    canonical=os.path.normcase(str(root.resolve()))
    return 'psrtty-'+hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:32]


def request_activation(root):
    client=QLocalSocket()
    try:
        client.connectToServer(endpoint(root))
        if not client.waitForConnected(700): return False
        client.write(b'ACTIVATE\n'); client.flush()
        deadline=time.monotonic()+1.0
        reply=bytearray()
        while True:
            # A reply may already be buffered during connect/write, or arrive
            # in separate chunks. waitForReadyRead alone misses buffered data.
            reply.extend(bytes(client.readAll()))
            if b'\n' in reply: return bytes(reply)==b'OK\n'
            remaining=int((deadline-time.monotonic())*1000)
            if remaining<=0 or client.state()==QLocalSocket.UnconnectedState: return False
            client.waitForReadyRead(remaining)
    finally:
        client.abort()


class ActivationServer(QObject):
    def __init__(self,root,window):
        super().__init__(window); self.window=window; self.clients=set()
        self.server=QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        # Only construct after successfully obtaining the installation lock.
        QLocalServer.removeServer(endpoint(root))
        self.listening=self.server.listen(endpoint(root))
        self.server.newConnection.connect(self.accept_clients)

    def accept_clients(self):
        while self.server.hasPendingConnections():
            client=self.server.nextPendingConnection(); self.clients.add(client)
            client.readyRead.connect(lambda c=client:self.receive(c))
            client.disconnected.connect(lambda c=client:self.release(c))
            if client.bytesAvailable(): self.receive(client)

    def release(self, client):
        self.clients.discard(client); client.deleteLater()

    def receive(self,client):
        if not client.canReadLine(): return
        line=bytes(client.readLine(64))
        if line==b'ACTIVATE\n':
            self.window.showNormal()
            screen=self.window.screen(); area=screen.availableGeometry()
            frame=self.window.frameGeometry()
            frame.moveLeft(max(area.left(),min(frame.left(),area.right()-frame.width()+1)))
            frame.moveTop(max(area.top(),min(frame.top(),area.bottom()-frame.height()+1)))
            self.window.move(frame.topLeft()); self.window.raise_(); self.window.activateWindow()
            self.window.statusBar().showMessage('PSRTTYはすでに起動しています。起動済みの画面を表示しました。',6000)
            client.write(b'OK\n'); client.flush()
        client.disconnectFromServer()
