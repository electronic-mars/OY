"""One log file per run under %LOCALAPPDATA%\\OYPlayer (or OY_HOME for tests)."""
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def home():
    p = Path(os.environ.get("OY_HOME") or Path(os.environ["LOCALAPPDATA"]) / "OYPlayer")
    p.mkdir(parents=True, exist_ok=True)
    return p


def setup():
    path = home() / "oyplayer.log"
    logging.basicConfig(filename=path, filemode="w", encoding="utf-8", level=logging.INFO,
                        format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    levels = {QtMsgType.QtDebugMsg: logging.DEBUG, QtMsgType.QtInfoMsg: logging.INFO,
              QtMsgType.QtWarningMsg: logging.WARNING, QtMsgType.QtCriticalMsg: logging.ERROR,
              QtMsgType.QtFatalMsg: logging.CRITICAL}
    qt = logging.getLogger("qt")
    # QML load errors and binding warnings arrive here; without this they are lost.
    qInstallMessageHandler(lambda mode, _ctx, msg: qt.log(levels.get(mode, logging.WARNING), msg))
    return path


log = logging.getLogger("oy")

# Small files (settings, positions, history, the playlist) are written by one thread of their
# own: the GUI thread also draws the picture, and a slow disk or an antivirus scan of the
# write must not hold it. The newest text of a file wins; files are written in order.
_writer = ThreadPoolExecutor(max_workers=1)
_waiting = {}
_lock = threading.Lock()


def write_later(path, text):
    with _lock:
        first = path not in _waiting
        _waiting[path] = text
    if first:
        _writer.submit(_write, path)


def _write(path):
    with _lock:
        text = _waiting.pop(path)
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    except OSError:
        log.exception("cannot write %s", path)


def flush_writes():
    """On exit: what is waiting is written before the process goes."""
    _writer.submit(lambda: None).result(10)
