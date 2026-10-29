"""One player: a second start hands its files to the first.

The pipe is named after the settings folder, so a self-test (its own folder) never talks
to the copy the owner has open, and two Windows users never share one.
"""
import ctypes
import hashlib
import json

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .log import home, log


def name():
    return "OYPlayer-" + hashlib.sha1(str(home()).lower().encode()).hexdigest()[:12]


def send(files):
    """True if a running player took the files (the caller then simply exits)."""
    sock = QLocalSocket()
    sock.connectToServer(name())
    if not sock.waitForConnected(500):
        return False
    # The running copy may bring its window forward: this process is the one the person
    # just started, so Windows lets it pass that right on.
    ctypes.windll.user32.AllowSetForegroundWindow(-1)    # ASFW_ANY
    sock.write(json.dumps({"files": files}).encode() + b"\n")
    sock.waitForBytesWritten(1000)
    ok = sock.waitForReadyRead(3000) and sock.readAll().data().startswith(b"ok")
    sock.disconnectFromServer()
    return ok


class Server(QObject):
    filesReceived = Signal(list)

    def __init__(self):
        super().__init__()
        self._server = QLocalServer(self)
        QLocalServer.removeServer(name())    # a pipe left by a copy that crashed
        if not self._server.listen(name()):
            log.warning("single instance: cannot listen: %s", self._server.errorString())
        self._server.newConnection.connect(self._accept)

    def _accept(self):
        sock = self._server.nextPendingConnection()
        buf = bytearray()

        def read():
            buf.extend(sock.readAll().data())
            if not buf.endswith(b"\n"):
                return
            try:
                files = json.loads(buf.decode())["files"]
            except (ValueError, KeyError):
                files = []
            log.info("second start handed over %d file(s)", len(files))
            sock.write(b"ok\n")
            sock.flush()
            self.filesReceived.emit(files)
        sock.readyRead.connect(read)
