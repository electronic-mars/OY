"""File types: OY Player offers itself for video, audio and radio station
files, per user (HKCU), and only when the person asks for it in the settings.

Since Windows 8 a program cannot make itself the default: Windows keeps that choice and
guards it. What a program can do, and this does, is register as a handler — "Open with",
and an entry in Settings > Apps > Default apps, which is then opened for the person to
choose. Removing takes away everything written here (the uninstaller runs --unregister).
"""
import ctypes
import os
import sys
import winreg
from pathlib import Path

from .i18n import tr
from .log import log
from .playlist import MEDIA_EXT

APP = "OY Player"
MEDIA_ID, RADIO_ID = "OYPlayer.media", "OYPlayer.radio"
EXTS = sorted(MEDIA_EXT) + [".lau"]
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


def icon():
    return f'"{sys.executable}",0' if getattr(sys, "frozen", False) else ""


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


def register(notify=True):
    cmd = command()
    for pid, text in ((MEDIA_ID, tr("assoc_media")), (RADIO_ID, tr("assoc_radio"))):
        _set(rf"{CLASSES}\{pid}", {"": text})
        _set(rf"{CLASSES}\{pid}\shell\open\command", {"": cmd})
        if icon():
            _set(rf"{CLASSES}\{pid}\DefaultIcon", {"": icon()})
    caps = rf"{APP_KEY}\Capabilities"
    _set(caps, {"ApplicationName": APP, "ApplicationDescription": tr("assoc_desc")})
    _set(rf"{caps}\FileAssociations", {e: RADIO_ID if e == ".lau" else MEDIA_ID for e in EXTS})
    for e in EXTS:
        _set(rf"{CLASSES}\{e}\OpenWithProgids", {RADIO_ID if e == ".lau" else MEDIA_ID: ""})
    _set(REGISTERED, {APP: caps})
    if getattr(sys, "frozen", False):
        exe = rf"{CLASSES}\Applications\{Path(sys.executable).name}"
        _set(rf"{exe}\shell\open\command", {"": cmd})
        _set(rf"{exe}\SupportedTypes", {e: "" for e in EXTS})
    log.info("file types registered for %s", cmd)
    if notify:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)    # SHCNE_ASSOCCHANGED


def unregister(notify=True):
    for pid in (MEDIA_ID, RADIO_ID):
        _delete_tree(rf"{CLASSES}\{pid}")
    for e in EXTS:
        _delete_value(rf"{CLASSES}\{e}\OpenWithProgids", RADIO_ID if e == ".lau" else MEDIA_ID)
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
