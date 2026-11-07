"""Video from web pages (YouTube and the many sites yt-dlp knows): mpv hands such an address
to yt-dlp, and yt-dlp needs a JavaScript engine (Deno) to read YouTube. Neither ships with the
player: they change every few weeks, while the player's installer would freeze them. They are
fetched from their own GitHub releases on the person's word, the first time a page is opened,
each checked against the SHA-256 its release publishes, into <home>/tools; yt-dlp then updates
itself once a week (its own -U, which checks its release's signature).
"""
import hashlib
import io
import re
import subprocess
import threading
import time
import zipfile
from urllib.parse import urlparse

from PySide6.QtCore import Property, QObject, Signal, Slot

from .log import home, log
from .update import CHUNK, _open

YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
YTDLP_SUMS = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/SHA2-256SUMS"
DENO_URL = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
DENO_SUM = DENO_URL + ".sha256sum"
MAX_BYTES = 200 * 1024 * 1024
UPDATE_EVERY_S = 7 * 24 * 3600
_NO_WINDOW = subprocess.CREATE_NO_WINDOW


def folder():
    return home() / "tools"


def ytdlp():
    return folder() / "yt-dlp.exe"


def deno():
    return folder() / "deno.exe"


def ready():
    return ytdlp().is_file() and deno().is_file()


# The sites whose pages are worth asking for yt-dlp. Any other address is opened by mpv itself
# as before: a radio station's /stream has no file ending either, and must not ask.
SITES = ("youtube.com", "youtu.be", "youtube-nocookie.com", "vimeo.com", "twitch.tv", "tiktok.com",
         "dailymotion.com", "x.com", "twitter.com", "instagram.com", "facebook.com", "fb.watch",
         "reddit.com", "soundcloud.com", "bilibili.com", "rumble.com", "streamable.com", "kick.com")


def is_page(url):
    """A page of a video site, which only yt-dlp can turn into a picture."""
    where = urlparse(url)
    host = (where.hostname or "").lower()
    return where.scheme in ("http", "https") and any(host == s or host.endswith("." + s) for s in SITES)


def mpv_options(core):
    """Where mpv finds yt-dlp, and yt-dlp finds Deno; set once, before anything is opened."""
    core["script-opts"] = f"ytdl_hook-ytdl_path={ytdlp()}"
    core["ytdl-raw-options"] = f"js-runtimes=deno:{deno()}"
    # a picture no larger than a big screen: 8K AV1 would only cost the processor
    core["ytdl-format"] = "bv*[height<=?2160]+ba/b"


def _fetch(url, limit=MAX_BYTES, progress=None):
    with _open(url) as answer:
        total = int(answer.headers.get("Content-Length") or 0)
        if total > limit:
            raise ValueError(f"{url} is {total} bytes")
        data = bytearray()
        while block := answer.read(CHUNK):
            data += block
            if len(data) > limit:
                raise ValueError(f"{url} outgrew {limit} bytes")
            if progress:
                progress(len(data), total)
    return bytes(data)


def _sum_for(text, name=None):
    """The SHA-256 a release lists (for name, when it lists several)."""
    for line in text.splitlines():
        if name is None or line.strip().endswith(name):
            found = re.search(r"\b[0-9a-fA-F]{64}\b", line)
            if found:
                return found.group(0).lower()
    raise ValueError(f"no SHA-256 for {name or 'the file'}")


def _check(data, expected, what):
    got = hashlib.sha256(data).hexdigest()
    if got != expected:
        raise ValueError(f"{what}: SHA-256 {got} is not the published {expected}")


def _write(path, data):
    part = path.with_suffix(".part")
    part.write_bytes(data)
    part.replace(path)


class WebVideo(QObject):
    """The state QML shows: idle, asking (an address waits for the person's yes), fetching
    (with progress), failed (with the reason)."""
    changed = Signal()
    readyToPlay = Signal(str)       # the address that waited, once the tools are in place
    _done = Signal(str)             # from the fetching thread: "" or why it failed

    def __init__(self):
        super().__init__()
        self._state, self._progress, self._reason, self._waiting = "idle", 0.0, "", ""
        self._done.connect(self._finish)    # queued: the rest happens on the window's thread

    @Property(str, notify=changed)
    def state(self):
        return self._state

    @Property(float, notify=changed)
    def progress(self):
        return self._progress

    @Property(str, notify=changed)
    def reason(self):
        return self._reason

    @Property(bool, notify=changed)
    def installed(self):
        return ready()

    def _set(self, state, reason=""):
        self._state, self._reason = state, reason
        self.changed.emit()

    def needs(self, url):
        """True when this address must wait for the tools: the question is then asked."""
        if ready() or not is_page(url):
            return False
        self._waiting = url
        if self._state != "fetching":
            self._set("asking")
        return True

    @Slot()
    def dismiss(self):
        self._waiting = ""
        if self._state != "fetching":
            self._set("idle")

    @Slot()
    def fetch(self):
        if self._state == "fetching":
            return
        self._progress = 0.0
        self._set("fetching")
        threading.Thread(target=self._fetch_all, daemon=True).start()

    def _fetch_all(self):
        try:
            folder().mkdir(parents=True, exist_ok=True)
            sizes = {"yt": 0, "deno": 0}

            def share(key):
                def on(got, total):
                    sizes[key] = got
                    self._progress = min(0.99, (sizes["yt"] + sizes["deno"]) / 66e6)
                    self.changed.emit()
                return on

            expected = _sum_for(_fetch(YTDLP_SUMS, 1 << 20).decode("utf-8", "replace"), "yt-dlp.exe")
            exe = _fetch(YTDLP_URL, progress=share("yt"))
            _check(exe, expected, "yt-dlp.exe")
            expected = _sum_for(_fetch(DENO_SUM, 1 << 20).decode("utf-8", "replace"))
            pack = _fetch(DENO_URL, progress=share("deno"))
            _check(pack, expected, "deno.zip")
            with zipfile.ZipFile(io.BytesIO(pack)) as z:
                inner = z.read("deno.exe")
            _write(deno(), inner)
            _write(ytdlp(), exe)        # last: ready() is true only with both in place
            log.info("web video: yt-dlp %d bytes and Deno %d bytes in %s", len(exe), len(inner), folder())
        except Exception as e:      # noqa: BLE001 - the reason is shown, whatever it is
            log.warning("web video: the tools were not fetched: %s", e)
            self._done.emit(str(e) or type(e).__name__)
            return
        self._done.emit("")

    @Slot(str)
    def _finish(self, reason):
        if reason:
            self._set("failed", reason)
            return
        self._progress = 1.0
        url, self._waiting = self._waiting, ""
        self._set("idle")
        if url:
            self.readyToPlay.emit(url)

    def update_later(self):
        """yt-dlp keeps up with the sites by updating itself: once a week, quietly, aside."""
        exe = ytdlp()
        if not exe.is_file() or time.time() - exe.stat().st_mtime < UPDATE_EVERY_S:
            return

        def run():
            try:
                r = subprocess.run([str(exe), "-U"], capture_output=True, text=True, timeout=300,
                                   creationflags=_NO_WINDOW)
                exe.touch()     # tried: not again for a week, whatever the answer
                log.info("web video: yt-dlp -U: %s", (r.stdout or r.stderr).strip().splitlines()[-1:])
            except (OSError, subprocess.TimeoutExpired) as e:
                log.warning("web video: yt-dlp -U failed: %s", e)
        threading.Thread(target=run, daemon=True).start()
