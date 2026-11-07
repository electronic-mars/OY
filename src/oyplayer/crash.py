"""What is left behind when the player goes down, and the calm word about it on the next start.

Each running player keeps two files of its own in the log folder (several players may run at
once): running-<pid>.txt, there from the start to a clean way out and holding the last Python
error, and crash-<pid>.log, where faulthandler writes a native crash. A start that finds the
file of a process no longer running knows that player did not end cleanly: the summary of what
it left becomes the card's line and the report's, the native trace is kept as last-crash.log
and the log of that run as oyplayer.previous.log.

The line that goes into a report carries no paths, no user name and nothing quoted (a file's
name is quoted in most error messages): only the kind of error and where in the code.
"""
import ctypes
import faulthandler
import logging
import os
import re
import sys
import threading
import traceback
from pathlib import Path
from urllib.parse import urlencode

from . import __version__

ISSUES = "https://github.com/electronic-mars/OY/issues/new"
log = logging.getLogger("oy")
_state = {"marker": None, "native": None}


def _alive(pid):
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)      # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(h)
    return code.value == 259                                         # STILL_ACTIVE


def scrub(text):
    """One line fit for a public report: no paths, addresses, user name or quoted names."""
    line = " ".join(text.split())
    line = re.sub(r"'[^']*'|\"[^\"]*\"", "'…'", line)
    line = re.sub(r"\b\w+://\S+", "<url>", line)
    # a full path runs to the end of the line: a file's name may hold spaces
    line = re.sub(r"\b[A-Za-z]:[\\/].*|\\\\.*", "<path>", line)
    line = re.sub(r"\S*[\\/]\S*", "<path>", line)
    user = os.environ.get("USERNAME", "")
    if len(user) > 1:
        line = re.sub(re.escape(user), "<user>", line, flags=re.IGNORECASE)
    return line[:240]


def native_line(text):
    """faulthandler's report as one line: the last fatal exception and the frame it hit in."""
    # LuaJIT's own exceptions (0xe24c4aXX) are thrown and caught inside mpv: never the crash
    blocks = [b for b in text.split("Windows fatal exception:") if not b.lstrip().startswith("code 0xe24c4a")]
    if len(blocks) < 2 and "Fatal Python error:" not in text:
        return ""
    if len(blocks) >= 2:
        head, rest = "Windows fatal exception:", blocks[-1]
    else:
        head, rest = "Fatal Python error:", text.split("Fatal Python error:")[-1]
    first, _, frames = rest.partition("\n")
    where = re.search(r'File "([^"]*)", line (\d+) in (\S+)', frames)
    line = scrub(head + first)
    if where:
        line += f" ({where.group(3)}, {re.split(r'[\\/]', where.group(1))[-1]}:{where.group(2)})"
    return line


def _hook(kind, value, tb):
    log.error("uncaught %s", kind.__name__, exc_info=(kind, value, tb))
    frames = traceback.extract_tb(tb) if tb else []
    line = scrub(traceback.format_exception_only(kind, value)[-1])
    if frames:
        f = frames[-1]
        line += f" ({f.name}, {Path(f.filename).name}:{f.lineno})"
    if _state["marker"]:
        try:
            _state["marker"].write_text(line, encoding="utf-8")
        except OSError:
            pass


def start(home):
    """Before the log is opened: what the last unclean exit left (a line, or ""), then this
    run's own files and hooks."""
    line = ""
    for marker in home.glob("running-*.txt"):
        pid = marker.stem.split("-", 1)[1]
        if not pid.isdigit() or _alive(int(pid)):
            continue
        native = home / f"crash-{pid}.log"
        try:
            text = native.read_text(encoding="utf-8", errors="replace") if native.exists() else ""
            line = native_line(text) or marker.read_text(encoding="utf-8").strip() or "no error recorded"
            if text:
                native.replace(home / "last-crash.log")
            marker.unlink()
            if (home / "oyplayer.log").exists():
                (home / "oyplayer.log").replace(home / "oyplayer.previous.log")
        except OSError:
            continue
    for old in home.glob("crash-*.log"):                 # a clean run's, or one read above
        pid = old.stem.split("-", 1)[1]
        if pid.isdigit() and not _alive(int(pid)):
            old.unlink(missing_ok=True)
    pid = os.getpid()
    _state["marker"] = home / f"running-{pid}.txt"
    _state["marker"].write_text("", encoding="utf-8")
    _state["native"] = open(home / f"crash-{pid}.log", "w", encoding="utf-8")
    # Only the thread that faults. On Windows faulthandler answers every error-class exception,
    # caught ones too, and mpv's Lua scripts throw and catch LuaJIT's (0xe24c4a02) many times a
    # second; walking the other threads' frames while they run, each time, itself crashed the
    # player (measured: an access violation in the middle of such a dump, 1 run of the built exe in 3).
    faulthandler.enable(_state["native"], all_threads=False)
    sys.excepthook = _hook
    threading.excepthook = lambda a: _hook(a.exc_type, a.exc_value, a.exc_traceback)
    return line


def clean_exit():
    """Every way out the player chose (and Windows ending the session): no crash to tell of."""
    if _state["marker"] is None:
        return
    faulthandler.disable()
    _state["native"].close()
    Path(_state["native"].name).unlink(missing_ok=True)
    _state["marker"].unlink(missing_ok=True)
    _state["marker"] = None


def windows():
    v = sys.getwindowsversion()
    return f"Windows {11 if v.build >= 22000 else 10} ({v.major}.{v.minor}.{v.build})"


def report_url(line):
    """A new issue on GitHub, its form filled with the version, Windows and the line."""
    return ISSUES + "?" + urlencode({"template": "bug_report.yml", "title": "Closed unexpectedly",
                                     "version": __version__, "windows": windows(), "error": line})
