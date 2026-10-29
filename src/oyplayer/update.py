"""Updating from the release page, checked against a key inside the player.

The player downloads an executable and runs it. That is only defensible if the file
can be proved to be ours. A checksum published next to the file proves nothing:
whoever can serve a false installer serves a false checksum with it. So the release
carries a signature made by a key that exists in one place - the build server's
secrets - and the player carries only the public half, compiled into it.

The checking is done by Windows, through its own CNG (bcrypt.dll): no dependency to
ship and no cryptography written here.

The release workflow (.github/workflows/release.yml, tools/sign_release.py) publishes
latest.json beside the installer; the player asks for it by a fixed address that
always points at the newest release.
"""
import ctypes
import hashlib
import json
import re
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from .log import home, log

bcrypt = ctypes.WinDLL("bcrypt")

# The public half of the release key; the private half lives only in the repository
# secret UPDATE_SIGNING_KEY. Replacing this constant changes who may publish an update
# (tools/make_update_key.py).
PUBLIC_KEY = bytes.fromhex(
    "133208e38cf072672c1058568b756580890cf81ca910b31fed371ffb0291c214"
    "85142fc8d94220b4c322b3b3b10f36be6f83adb622a5307f917e32eb5c6e51a8")

FEED = "https://github.com/electronic-mars/OY/releases/latest/download/latest.json"
# GitHub answers a release download with a redirect to its file store, which is why
# that store is on the list; nothing is fetched from anywhere else.
ALLOWED_HOSTS = ("github.com", "objects.githubusercontent.com",
                 "release-assets.githubusercontent.com")
TIMEOUT_S = 30
CHUNK = 64 * 1024
# The installer is about 120 MB; a feed promising more than this is not describing ours.
MAX_BYTES = 400 * 1024 * 1024

BCRYPT_ECDSA_P256_ALGORITHM = "ECDSA_P256"
BCRYPT_ECCPUBLIC_BLOB = "ECCPUBLICBLOB"     # the macro has underscores, the string has not
BCRYPT_ECDSA_PUBLIC_P256_MAGIC = 0x31534345
STATUS_SUCCESS = 0


def as_numbers(version):
    """"1.2.10" -> (1, 2, 10); a leading v and anything after the numbers go."""
    found = re.findall(r"\d+", version or "")
    return tuple(int(x) for x in found[:3]) or (0,)


def is_newer(offered, current):
    return as_numbers(offered) > as_numbers(current)


def _allow(url):
    where = urlparse(url)
    if where.scheme != "https":
        raise ValueError("updates are only fetched over https")
    if where.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"{where.hostname} is not a host updates come from")
    return url


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    """Every redirect hop gets the same test as the first address."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _allow(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_fetch = urllib.request.build_opener(_CheckedRedirects)


def _open(url):
    return _fetch.open(_allow(url), timeout=TIMEOUT_S)


def latest():
    """What the release page offers: {version, url, signature}. Raises when it cannot be read."""
    with _open(FEED) as answer:
        feed = json.loads(answer.read(256 * 1024).decode("utf-8"))
    windows = (feed.get("platforms") or {}).get("windows-x86_64") or {}
    url, signature = windows.get("url", ""), windows.get("signature", "")
    if not feed.get("version") or not url or not signature:
        raise ValueError("the release description is incomplete")
    _allow(url)
    return {"version": str(feed["version"]), "url": url, "signature": signature}


def verify(path, signature):
    """Is this file the one our key signed? Windows answers, not us."""
    if len(signature) != 64:
        log.warning("update: the signature is %d bytes, not 64", len(signature))
        return False
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            digest.update(block)
    digest = digest.digest()

    alg = ctypes.c_void_p()
    if bcrypt.BCryptOpenAlgorithmProvider(
            ctypes.byref(alg), BCRYPT_ECDSA_P256_ALGORITHM, None, 0) != STATUS_SUCCESS:
        log.error("update: this Windows has no ECDSA P-256 to check the signature with")
        return False
    try:
        blob = (BCRYPT_ECDSA_PUBLIC_P256_MAGIC.to_bytes(4, "little")
                + (32).to_bytes(4, "little") + PUBLIC_KEY)
        key = ctypes.c_void_p()
        status = bcrypt.BCryptImportKeyPair(
            alg, None, BCRYPT_ECCPUBLIC_BLOB, ctypes.byref(key),
            ctypes.create_string_buffer(blob), len(blob), 0)
        if status != STATUS_SUCCESS:
            log.error("update: the release key was refused: 0x%08X", status & 0xFFFFFFFF)
            return False
        try:
            return bcrypt.BCryptVerifySignature(
                key, None, ctypes.create_string_buffer(digest), len(digest),
                ctypes.create_string_buffer(signature), len(signature), 0) == STATUS_SUCCESS
        finally:
            bcrypt.BCryptDestroyKey(key)
    finally:
        bcrypt.BCryptCloseAlgorithmProvider(alg, 0)


def download(url, on_progress=None):
    """Fetch the installer beside the settings (the program's own folder is what the
    installer replaces), under a fixed name, written as .part and renamed at the end so
    a cut-off download never looks like a finished one."""
    folder = home() / "update"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "update-setup.exe"
    part = target.with_suffix(".exe.part")
    with _open(url) as answer:
        total = int(answer.headers.get("Content-Length") or 0)
        if total > MAX_BYTES:
            raise ValueError(f"the installer is {total} bytes, which is not credible")
        got = 0
        with open(part, "wb") as f:
            while block := answer.read(CHUNK):
                got += len(block)
                if got > MAX_BYTES:
                    raise ValueError("the download outgrew what was promised")
                f.write(block)
                if on_progress:
                    on_progress(got, total)
    part.replace(target)
    log.info("update: downloaded %s, %d bytes", target, got)
    return target


def install(path):
    """Start the installer silently and leave it to replace the player. /RELAUNCH=1 is
    ours: the installer starts the player again only when it was started this way."""
    subprocess.Popen([str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOCANCEL",
                      "/RELAUNCH=1"], close_fds=True)
    log.info("update: the installer %s is running, the player has stepped aside", path)
