"""One player: a second start hands its files to the first.

The pipe is named after the settings folder, so a self-test (its own folder) never talks
to the copy the owner has open, and two Windows users never share one.

Several files opened together in Explorer start a process each, at the same moment, and the
first one listens only once it is up. So the first one also holds a mutex of the same name
from its first moment: a start that finds the mutex taken waits for the pipe instead of
opening a window of its own.
"""
import ctypes
import hashlib
import json
import time
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .log import home, log

ERROR_ALREADY_EXISTS, WAIT_OBJECT_0, WAIT_ABANDONED = 183, 0, 0x80
WAIT_FOR_FIRST = 10.0        # seconds a start waits for a player still starting to listen
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateMutexW.restype = wintypes.HANDLE
_k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
_k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_k32.GetCurrentProcess.restype = wintypes.HANDLE
_k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
_mutex = None


def _started():
    """When this process was made, in time.time()'s seconds: a start older than the running
    player's window was made together with it (Explorer starts one for each file chosen)."""
    made, *_rest = times = [wintypes.FILETIME() for _ in range(4)]
    _k32.GetProcessTimes(_k32.GetCurrentProcess(), *(ctypes.byref(t) for t in times))
    return ((made.dwHighDateTime << 32 | made.dwLowDateTime) - 116444736000000000) / 1e7


def name():
    return "OYPlayer-" + hashlib.sha1(str(home()).lower().encode()).hexdigest()[:12]


def first():
    """Whether no other player of this settings folder runs or is starting. The first one
    owns the mutex as long as it runs; Windows lets go of it when the process ends, a crash too."""
    global _mutex
    _mutex = _k32.CreateMutexW(None, True, name())
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def _became_first():
    """The player that held the mutex has gone (it was quitting): this one owns it now."""
    return _k32.WaitForSingleObject(_mutex, 0) in (WAIT_OBJECT_0, WAIT_ABANDONED)


def send(files, is_first):
    """True if a running player took the files (the caller then simply exits). With no other
    player holding the mutex one try is enough: only an older version can be listening."""
    deadline = time.monotonic() + (0 if is_first else WAIT_FOR_FIRST)
    while True:
        sock = QLocalSocket()
        sock.connectToServer(name())
        if sock.waitForConnected(500):
            break
        if time.monotonic() > deadline or _became_first():
            return False
        time.sleep(0.05)
    # The running copy may bring its window forward: this process is the one the person
    # just started, so Windows lets it pass that right on.
    ctypes.windll.user32.AllowSetForegroundWindow(-1)    # ASFW_ANY
    sock.write(json.dumps({"files": files, "started": _started()}).encode() + b"\n")
    sock.waitForBytesWritten(1000)
    # a player still starting answers once its window is up
    ok = sock.waitForReadyRead(int(WAIT_FOR_FIRST * 1000)) and sock.readAll().data().startswith(b"ok")
    sock.disconnectFromServer()
    return ok


class Server(QObject):
    filesReceived = Signal(list, float)     # the files, when the start that sent them was made

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
                msg = json.loads(buf.decode())
                files, started = msg["files"], float(msg.get("started", time.time()))
            except (ValueError, KeyError, TypeError):
                files, started = [], time.time()
            log.info("second start handed over %d file(s)", len(files))
            sock.write(b"ok\n")
            sock.flush()
            self.filesReceived.emit(files, started)
        sock.readyRead.connect(read)
