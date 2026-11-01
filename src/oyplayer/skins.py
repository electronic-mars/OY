"""Skins: the panel's look in a sealed file, for sale one day.

A skin is the panel's colours (Theme.qml's tokens, for the dark body, the light one or both)
and a few of its parts drawn another way (the play key, the volume, the LCD, the settings key's
side, the drawing tools' place), with a picture of its panel for the list. Every skin is the
player's own: the default is no file (it is Theme.qml), the others come with the player.

The file (.oyskin) is sealed twice:
- signed with the skin key (ECDSA P-256, checked by Windows as the updates are, update.py):
  a skin nobody signed, or one changed after signing, is not loaded at all. That is what
  stops a paid skin from being passed round with its «paid» mark edited away;
- its contents encrypted with a key derived from a secret that is not in the repository
  (_skinkey.py, written by tools/skin_pack.py and, for a release, by the build from the
  repository secret SKIN_KEY): the colours and parts cannot be read or copied off the file.

Neither survives a person who takes the player itself apart: the program has to hold what
opens its own skins. The seal keeps honest people honest and the casual copy out; a paid skin
also needs a licence, a small file signed with the same key for one buyer.

Layout: MAGIC, header length (2 bytes), header (JSON, plain: what the list shows), nonce
(16 bytes), the encrypted body (JSON: the look, and "preview", the panel as a base64 PNG), and
the signature over all that (64 bytes, r||s).
"""
import hashlib
import json
import re
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal

from . import update
from .log import home, log

MAGIC = b"OYSKIN\x00\x01"
NONCE = 16
SIGNATURE = 64
BUILTIN = Path(__file__).resolve().parent / "skins"     # the skins the player comes with
DEFAULT = "default"
DEFAULT_PREVIEW = BUILTIN / "default.png"       # the default's panel, for the list

# The public half of the skin key (tools/skin_pack.py made the pair; the private half stays with
# the author, outside the repository). Only what it signed loads.
PUBLIC_KEY = bytes.fromhex(
    "eafef31168896d9c1f21fb6436c01cea8686757a742ea0e4bf8593dc63a596d9"
    "012b79ae94976be93f2ee56f431b2e75630ed7e2bbbcf38e75cfe2877f878dd7")

try:
    from ._skinkey import secret
    SECRET = secret()
except ImportError:                       # a clone of the repository: no skin opens, the default stays
    SECRET = None


def content_key(skin_id, master):
    return hashlib.blake2b(skin_id.encode("utf-8"), key=master, person=b"oyskin.key",
                           digest_size=32).digest()


def crypt(data, key, nonce):
    """XOR with a keystream of keyed BLAKE2b blocks over the nonce and a counter: the same call
    seals and opens. The signature, not this, is what tells a changed file."""
    stream = bytearray()
    for i in range((len(data) + 63) // 64):
        stream += hashlib.blake2b(nonce + i.to_bytes(8, "little"), key=key, digest_size=64).digest()
    n = len(data)
    return (int.from_bytes(data, "little") ^ int.from_bytes(stream[:n], "little")).to_bytes(n, "little")


def signed_part(raw):
    """The bytes the signature covers, and the signature; ValueError if the shape is wrong."""
    if len(raw) < len(MAGIC) + 2 + NONCE + SIGNATURE or not raw.startswith(MAGIC):
        raise ValueError("not a skin file")
    return raw[:-SIGNATURE], raw[-SIGNATURE:]


def read_header(raw):
    body, _ = signed_part(raw)
    n = int.from_bytes(body[len(MAGIC):len(MAGIC) + 2], "little")
    start = len(MAGIC) + 2
    try:
        header = json.loads(body[start:start + n].decode("utf-8"))
    except RecursionError:
        raise ValueError("the header is not one we write")
    # the id names its file in <home>/skins: letters, digits and dashes only
    if not isinstance(header, dict) or not re.fullmatch(r"[a-z0-9-]{1,40}", str(header.get("id"))) or header["id"] == DEFAULT:
        raise ValueError("the skin has no name of its own")
    return header, body[start + n:]


def is_signed(data, signature):
    return update.verify_digest(hashlib.sha256(data).digest(), signature, PUBLIC_KEY)


def version(header):
    """The skin's version as numbers, for comparing copies: "1.2" -> (1, 2)."""
    try:
        return tuple(int(n) for n in str(header.get("version", "0")).split("."))
    except ValueError:
        return (0,)


def open_skin(raw, master):
    """The header and the look of a skin file; ValueError when it is not one we signed or the
    secret does not open it. The signature is checked before anything in the file is read."""
    signed, signature = signed_part(raw)
    if not is_signed(signed, signature):
        raise ValueError("the skin is not signed by the player's key")
    header, rest = read_header(raw)
    nonce, sealed = rest[:NONCE], rest[NONCE:]
    try:
        look = json.loads(crypt(sealed, content_key(header["id"], master), nonce).decode("utf-8"))
    except (UnicodeDecodeError, RecursionError):
        raise ValueError("the content secret does not open it")
    if not isinstance(look, dict):
        raise ValueError("the content secret does not open it")
    return header, look


def licensed(skin_id):
    """A paid skin opens for a licence beside it: {"skin", "holder", "sig"}, signed for this skin."""
    try:
        lic = json.loads((home() / "skins" / "licenses" / f"{skin_id}.json").read_text(encoding="utf-8"))
        text = json.dumps({"skin": lic["skin"], "holder": lic["holder"]}, sort_keys=True).encode("utf-8")
        return lic["skin"] == skin_id and is_signed(text, bytes.fromhex(lic["sig"]))
    except (OSError, ValueError, KeyError, TypeError):
        return False


class Skins(QObject):
    """The skins found (those the player comes with, and paid ones put into <home>/skins with
    their licences), each with its panel's picture, and the chosen one's look for Theme.qml:
    {dark: {token: value}, light: {…}, parts: {part: value}}; the default's is {}. Only skins
    that open are listed: without the content secret (a clone of the repository) the list is the
    default alone."""
    changed = Signal()          # the look and the skin worn
    itemsChanged = Signal()     # the list, on a scan only (a choice does not rebuild the cards)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.folder = home() / "skins"
        self._items, self._looks = [], {}
        self._look, self._current = {}, DEFAULT
        self.scan()
        settings.changed.connect(lambda key: key == "skin" and self._choose())

    def scan(self):
        items = [{"id": DEFAULT, "name": {"en": "Default", "uk": "Стандартний"}, "author": "OY",
                  "tier": "free", "locked": False,
                  "preview": DEFAULT_PREVIEW.as_uri() if DEFAULT_PREVIEW.exists() else ""}]
        self._looks, versions = {}, {}
        if SECRET is None:
            log.warning("no content secret (_skinkey.py): only the default skin")
        for folder in (BUILTIN, self.folder) if SECRET is not None else ():
            for path in sorted(folder.glob("*.oyskin")) if folder.is_dir() else []:
                try:
                    header, look = open_skin(path.read_bytes(), SECRET)
                except (OSError, ValueError) as e:
                    log.warning("skin %s skipped: %s", path.name, e)
                    continue
                sid = header["id"]
                if sid in versions and version(header) <= versions[sid]:    # the newer copy wins
                    continue
                versions[sid] = version(header)
                # the picture is in the sealed body: a locked (paid, unlicensed) skin shows it too
                preview = look.pop("preview", "")
                self._looks[sid] = look
                items = [i for i in items if i["id"] != sid]
                items.append({"id": sid, "name": header.get("name") or {"en": sid},
                              "author": header.get("author", ""), "tier": header.get("tier", "free"),
                              "locked": header.get("tier") == "paid" and not licensed(sid),
                              "preview": "data:image/png;base64," + preview if preview else ""})
        self._items = items
        self.itemsChanged.emit()
        self._choose()

    def _choose(self):
        wanted = self.settings["skin"]
        item = next((i for i in self._items if i["id"] == wanted), None)
        look, current = {}, DEFAULT
        if item and not item["locked"] and wanted in self._looks:
            look, current = self._looks[wanted], wanted
        elif wanted != DEFAULT:
            log.info("skin %s is not here or locked: the default", wanted)
        self._look, self._current = look, current
        self.changed.emit()

    @Property("QVariantList", notify=itemsChanged)
    def items(self):
        return self._items

    @Property(str, notify=changed)
    def current(self):
        """The skin actually worn: the chosen one, or the default when that one does not open."""
        return self._current

    @Property("QVariantMap", notify=changed)
    def look(self):
        return self._look
