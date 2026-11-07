"""File types: OY Player offers itself for video, audio and radio station
files, per user (HKCU), and only when the person asks for it in the settings.

Since Windows 8 a program cannot make itself the default: Windows keeps that choice and
guards it. What a program can do, and this does, is register as a handler — "Open with",
and an entry in Settings > Apps > Default apps, which is then opened for the person to
choose. Removing takes away everything written here (the uninstaller runs --unregister).
"""
import ctypes
import os
import struct
import sys
import winreg
from pathlib import Path

from .i18n import tr
from .log import home, log
from .playlist import MEDIA_EXT
from .series import VIDEO_EXT

APP = "OY Player"
MEDIA_ID, AUDIO_ID, RADIO_ID = "OYPlayer.media", "OYPlayer.audio", "OYPlayer.radio"
EXTS = sorted(MEDIA_EXT) + [".lau"]
VIDEO = sorted(VIDEO_EXT & MEDIA_EXT) + [".lau"]
# Windows' own file icons (imageres.dll, by resource id, stable across builds): a sheet with
# a film strip, a sheet with a note. Taken from the person's own Windows when registering,
# with the player's key laid in their lower right corner — nothing of Microsoft's is shipped.
SYSTEM_ICON = {MEDIA_ID: -133, AUDIO_ID: -131}
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 256)
# Where it all goes; the self-test points these at a scratch key it deletes afterwards.
CLASSES = r"Software\Classes"
APP_KEY = r"Software\OYPlayer"
REGISTERED = r"Software\RegisteredApplications"


def command():
    """How Windows starts the player with a file."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" "%1"'
    # development: the venv's windowless python, the package from this checkout
    pyw = Path(sys.executable).with_name("pythonw.exe")
    src = Path(__file__).resolve().parents[1]
    return (f'"{pyw}" -c "import sys; sys.path.insert(0, r\'{src}\'); '
            f'from oyplayer.__main__ import main; sys.exit(main(sys.argv))" "%1"')


def _prog_id(ext):
    if ext == ".lau":
        return RADIO_ID
    return MEDIA_ID if ext in VIDEO_EXT else AUDIO_ID


def icon():
    return f'"{sys.executable}",0' if getattr(sys, "frozen", False) else ""


def _system_icon(res_id, size):
    """One size of a Windows icon as a QImage, or None."""
    from ctypes import wintypes
    from PySide6.QtGui import QImage
    shell = ctypes.windll.shell32
    shell.SHDefExtractIconW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, wintypes.UINT,
                                        ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.HICON),
                                        wintypes.UINT]
    path = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "imageres.dll")
    h = wintypes.HICON()
    if shell.SHDefExtractIconW(path, res_id, 0, ctypes.byref(h), None, size) != 0 or not h:
        return None
    img = QImage.fromHICON(h.value)
    ctypes.windll.user32.DestroyIcon(h)
    return img


def badged_icon(res_id, out):
    """Windows' icon res_id with the player's key in its lower right corner, written to out as an
    .ico with a PNG for each size. False when Windows has no such icon."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize
    from PySide6.QtGui import QIcon, QPainter
    key = QIcon(str(Path(__file__).with_name("oyplayer.ico")))
    entries = []
    for size in ICON_SIZES:
        img = _system_icon(res_id, size)
        if img is None:
            return False
        img = img.scaled(size, size) if img.width() != size else img
        s = max(8, round(size * 0.5))
        p = QPainter(img)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawPixmap(size - s, size - s, key.pixmap(QSize(s, s)))
        p.end()
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        entries.append((size, bytes(data)))
    head = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    dirs, blobs = b"", b""
    for size, png in entries:
        dim = 0 if size >= 256 else size
        dirs += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset + len(blobs))
        blobs += png
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(head + dirs + blobs)
    return True


def _icons(windows_icons):
    """The DefaultIcon of each kind: the player's own, or Windows' with the player's mark."""
    own = icon()
    found = {MEDIA_ID: own, AUDIO_ID: own, RADIO_ID: own}
    if windows_icons:
        for pid, res in SYSTEM_ICON.items():
            out = home() / "icons" / f"{pid.split('.')[1]}.ico"
            try:
                if badged_icon(res, out):
                    found[pid] = f'"{out}",0'
            except OSError as e:
                log.warning("file icon %s not written: %s", out, e)
    return found


def _set(path, values):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE) as k:
        for name, value in values.items():
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)


def _delete_tree(path):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(path + "\\" + sub)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except FileNotFoundError:
        pass


def _delete_value(path, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE) as k:
            winreg.DeleteValue(k, name)
    except FileNotFoundError:
        pass


def register(notify=True, audio=False, windows_icons=False):
    """Video files and radio stations always, sound files only with `audio`. Registering again
    first takes away what an earlier choice offered. `windows_icons`: the files keep Windows'
    own look, with the player's key in the corner."""
    unregister(notify=False)
    exts = EXTS if audio else VIDEO
    cmd = command()
    icons = _icons(windows_icons)
    for pid, text in ((MEDIA_ID, tr("assoc_media")), (AUDIO_ID, tr("assoc_audio")),
                      (RADIO_ID, tr("assoc_radio"))):
        _set(rf"{CLASSES}\{pid}", {"": text})
        _set(rf"{CLASSES}\{pid}\shell\open\command", {"": cmd})
        if icons[pid]:
            _set(rf"{CLASSES}\{pid}\DefaultIcon", {"": icons[pid]})
    caps = rf"{APP_KEY}\Capabilities"
    _set(caps, {"ApplicationName": APP, "ApplicationDescription": tr("assoc_desc")})
    _set(rf"{caps}\FileAssociations", {e: _prog_id(e) for e in exts})
    for e in exts:
        _set(rf"{CLASSES}\{e}\OpenWithProgids", {_prog_id(e): ""})
    _set(REGISTERED, {APP: caps})
    if getattr(sys, "frozen", False):
        exe = rf"{CLASSES}\Applications\{Path(sys.executable).name}"
        _set(rf"{exe}\shell\open\command", {"": cmd})
        _set(rf"{exe}\SupportedTypes", {e: "" for e in exts})
    log.info("file types registered for %s", cmd)
    if notify:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)    # SHCNE_ASSOCCHANGED


def unregister(notify=True):
    for pid in (MEDIA_ID, AUDIO_ID, RADIO_ID):
        _delete_tree(rf"{CLASSES}\{pid}")
    for e in EXTS:
        # sound files went under the media id before there was an audio one
        for pid in {_prog_id(e), MEDIA_ID}:
            _delete_value(rf"{CLASSES}\{e}\OpenWithProgids", pid)
    _delete_value(REGISTERED, APP)
    _delete_tree(APP_KEY)
    if getattr(sys, "frozen", False):
        _delete_tree(rf"{CLASSES}\Applications\{Path(sys.executable).name}")
    log.info("file types unregistered")
    if notify:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)


def registered():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{CLASSES}\{MEDIA_ID}\shell\open\command") as k:
            return winreg.QueryValueEx(k, "")[0] == command()
    except FileNotFoundError:
        return False


def open_default_apps():
    """Windows' own page where the person makes OY Player the default, type by type."""
    os.startfile(f"ms-settings:defaultapps?registeredAppUser={APP}")
