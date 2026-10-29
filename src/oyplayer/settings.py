"""User settings: one JSON file, sensible defaults, applied live.

Everything with a sensible default stays a
default; what remains is what changes how the player behaves for a person. Actions that
are done on the spot (aspect, tracks, colour) live in menus and keys, not here.
"""
import json

from PySide6.QtCore import Property, QObject, Signal, Slot

from .i18n import system_lang
from .log import home, log, write_later

DEFAULTS = {
    # Playback
    "resume": False,
    "fileMemory": True,          # each file comes back with its own sound and subtitle tracks and volume
    "openAdds": True,
    "series": True,              # the next episodes come with an opened one
    "autoskip": True,            # skip marked openings and credits
    "history": True,
    "onListEnd": "stop",         # stop | close | sleep | shutdown
    "hwdec": True,
    # Window
    "lang": "",                  # "" = as Windows shows (Ukrainian or English) | en | uk
    "theme": "system",           # system | dark | light
    "accent": "#F26A21",         # the one colour of the panel (Braun orange); yellow is the editor's
    "onTop": "never",            # never | always | playing
    "fitWindow": True,
    "singleInstance": True,
    "tray": "off",               # off | on | minimize
    "globalMedia": False,        # media keys reach the player from any program
    "updateCheck": True,         # once a day ask the release page whether a newer version is out
    # Radio
    "radioDir": "",              # "" = <home>\\Radio, the .lau stations
    "radioRecDir": "",           # "" = Music\\OY Player
    # Sound
    "volume": 100,               # remembered from the last run
    "audioMode": "off",
    "audioDevice": "auto",
    "maxVolume": 200,
    "channels": "auto-safe",     # auto-safe | stereo | 5.1 | 7.1
    "audioLang": "eng,en",       # until set, follows the interface language (TRACK_LANGS)
    "passthrough": False,
    # Subtitles
    "subsOn": True,
    "subLang": "eng,en",
    "subScale": 1.0,
    "subFolders": "subs;Subs;subtitles",
    # Controls
    "wheel": "volume",           # volume | seek
    "doubleClick": "fullscreen",  # fullscreen | pause | none
    "preview": True,             # frame over the seek bar under the pointer
    "seekStep": 5,
    "jumpStep": 30,
    "keys": {},                  # overrides: key -> action ("" removes a default)
    # Screenshots
    "shotFormat": "png",         # png | jpg
    "shotQuality": 90,
    "shotDir": "",               # "" = Pictures\\OY Player
    # Editing
    "exportCodec": "copy",       # copy (without re-encoding where it can) | h264 | h265
    # Advanced: raw mpv options, one "name=value" per line
    "mpvOptions": "",
}
# the audio and subtitle languages looked for first, by the interface language
TRACK_LANGS = {"en": "eng,en", "uk": "ukr,uk,eng,en"}


class Settings(QObject):
    changed = Signal(str)

    def __init__(self):
        super().__init__()
        self._file = home() / "settings.json"
        self._v = dict(DEFAULTS)
        saved = {}
        try:
            saved = json.loads(self._file.read_text(encoding="utf-8"))
            self._v.update({k: v for k, v in saved.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass
        langs = TRACK_LANGS.get(self._v["lang"] or system_lang(), DEFAULTS["audioLang"])
        for k in ("audioLang", "subLang"):
            if k not in saved:
                self._v[k] = langs

    @Property("QVariantMap", notify=changed)
    def values(self):
        return self._v

    def __getitem__(self, key):
        return self._v[key]

    @Slot(str, "QVariant")
    def set(self, key, value):
        if key not in DEFAULTS:
            log.warning("unknown setting %s", key)
            return
        if isinstance(DEFAULTS[key], int) and not isinstance(DEFAULTS[key], bool):
            value = int(value)
        elif isinstance(DEFAULTS[key], float):
            value = float(value)
        if self._v.get(key) == value:
            return
        self._v[key] = value
        write_later(self._file, json.dumps(self._v, ensure_ascii=False, indent=1))
        log.info("setting %s = %r", key, value)
        self.changed.emit(key)

    @Slot(str)
    def reset(self, key):
        self.set(key, DEFAULTS[key])


def apply(settings, key, core, actions):
    """Push one setting (or all, key=None) into mpv and the action table."""
    v = settings.values
    keys = DEFAULTS if key is None else {key: None}
    for k in keys:
        if k == "volume":
            core["volume"] = v["volume"]
        elif k == "audioDevice":
            core["audio-device"] = v["audioDevice"]
        elif k == "hwdec":
            core["hwdec"] = "auto-safe" if v["hwdec"] else "no"
        elif k == "maxVolume":
            core["volume-max"] = v["maxVolume"]
        elif k == "channels":
            core["audio-channels"] = v["channels"]
        elif k == "audioLang":
            core["alang"] = v["audioLang"]
        elif k == "passthrough":
            core["audio-spdif"] = "ac3,eac3,dts,dts-hd,truehd" if v["passthrough"] else ""
        elif k == "subsOn":
            core["sub-visibility"] = v["subsOn"]
        elif k == "subLang":
            core["slang"] = v["subLang"]
        elif k == "subScale":
            core["sub-scale"] = v["subScale"]
        elif k == "subFolders":
            core["sub-file-paths"] = v["subFolders"]
        elif k in ("shotFormat", "shotQuality"):
            core["screenshot-format"] = v["shotFormat"]
            core["screenshot-jpeg-quality"] = v["shotQuality"]
        elif k in ("keys", "seekStep", "jumpStep"):
            actions.configure(v["keys"], v["seekStep"], v["jumpStep"])
        elif k == "mpvOptions":
            for line in v["mpvOptions"].splitlines():
                name, sep, val = line.strip().partition("=")
                if sep and name and not name.startswith("#"):
                    try:
                        core[name.strip()] = val.strip()
                    except (AttributeError, TypeError, ValueError) as e:
                        log.warning("mpv option %s rejected: %s", name, e)
