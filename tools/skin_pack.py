"""Seal the skins: sources in skins-src\\*.json -> src\\oyplayer\\skins\\<id>.oyskin.

    .venv\\Scripts\\python tools\\skin_pack.py              seal every source
    .venv\\Scripts\\python tools\\skin_pack.py license <id> <holder>
                                                          a licence for a paid skin
    python tools/skin_pack.py key-from-env                the build: _skinkey.py from SKIN_KEY,
                                                          checked on every bundled skin

The first run makes the two keys, once:
- .skin-signing-key.pem, the private half of the signature (the repository ignores it). It stays
  with the author: keep a copy somewhere safe. Lost, no new skin can be signed until a player
  carrying a new public half is out; leaked, anybody can sign a skin the player accepts.
- src\\oyplayer\\_skinkey.py, the secret the contents are encrypted with (ignored too). A release
  build writes it from the repository secret SKIN_KEY, whose value this run prints.

A source: {"id", "name": {"en", "uk"}, "author", "version", "tier": "free" | "paid",
"look": {"dark": {token: value}, "light": {…}, "parts": {part: value}}} (skins.py, Theme.qml).
Beside it, <id>.png: the skin's panel for the list in Settings (the self-test's block "skins"
shoots every panel into tests\\out\\skinprev_<id>.png; copy them over, the default's to
src\\oyplayer\\skins\\default.png).
"""
import base64
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "skins-src"
PRIVATE_FILE = ROOT / ".skin-signing-key.pem"
SECRET_FILE = ROOT / "src" / "oyplayer" / "_skinkey.py"
SECRET_NAME = "SKIN_KEY"

sys.path.insert(0, str(ROOT / "src"))


def write_secret(master):
    mask = secrets.token_bytes(len(master))
    SECRET_FILE.write_text(
        "# Written by tools/skin_pack.py (or the release build, from SKIN_KEY). Never in the repository.\n"
        f"_A = bytes.fromhex(\"{mask.hex()}\")\n"
        f"_B = bytes.fromhex(\"{bytes(a ^ b for a, b in zip(master, mask)).hex()}\")\n\n\n"
        "def secret():\n"
        "    return bytes(a ^ b for a, b in zip(_A, _B))\n", encoding="utf-8")


if sys.argv[1:] == ["key-from-env"]:
    master = os.environ.get(SECRET_NAME, "").strip()
    if len(master) != 64:
        raise SystemExit(f"{SECRET_NAME} is not set (64 hex digits): the built player would open no skin")
    write_secret(bytes.fromhex(master))
    # a value of the right length but not the one the skins were sealed with would ship a player
    # whose every skin stays shut: each bundled skin must open with it
    from oyplayer import skins
    for path in sorted((ROOT / "src" / "oyplayer" / "skins").glob("*.oyskin")):
        try:
            skins.open_skin(path.read_bytes(), bytes.fromhex(master))
        except ValueError as e:
            raise SystemExit(f"{SECRET_NAME} does not open {path.name} ({e}): it is not the secret the skins were sealed with")
    print(f"{SECRET_FILE.name} written from {SECRET_NAME}; the bundled skins open with it")
    sys.exit(0)

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, utils
except ImportError:
    raise SystemExit("pip install -r requirements-build.txt")


def keys():
    if not PRIVATE_FILE.exists():
        private = ec.generate_private_key(ec.SECP256R1())
        PRIVATE_FILE.write_bytes(private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        n = private.public_key().public_numbers()
        hexed = (n.x.to_bytes(32, "big") + n.y.to_bytes(32, "big")).hex()
        print("A new skin key. Paste this into PUBLIC_KEY in src/oyplayer/skins.py:\n")
        print(f'    "{hexed[:64]}"\n    "{hexed[64:]}")\n')
        print(f"The private half is in {PRIVATE_FILE.name}: keep a copy outside this folder.")
    if not SECRET_FILE.exists():
        master = secrets.token_bytes(32)
        write_secret(master)
        print(f"A new content secret in {SECRET_FILE.name}. Put this into the repository secret "
              f"{SECRET_NAME}:\n    {master.hex()}\n")
    return serialization.load_pem_private_key(PRIVATE_FILE.read_bytes(), password=None)


def sign(private, data):
    r, s = utils.decode_dss_signature(private.sign(data, ec.ECDSA(hashes.SHA256())))
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def seal(private, source):
    from oyplayer import skins
    from oyplayer._skinkey import secret
    look = source.pop("look")
    header = json.dumps(source, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    nonce = secrets.token_bytes(skins.NONCE)
    body = json.dumps(look, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    data = (skins.MAGIC + len(header).to_bytes(2, "little") + header + nonce
            + skins.crypt(body, skins.content_key(source["id"], secret()), nonce))
    return data + sign(private, data)


def main():
    private = keys()
    from oyplayer import skins
    from oyplayer._skinkey import secret
    if skins.PUBLIC_KEY == bytes(64):
        raise SystemExit("PUBLIC_KEY in skins.py is still empty: paste the key printed above and run again")

    if sys.argv[1:2] == ["license"] and len(sys.argv) == 4:
        lic = {"skin": sys.argv[2], "holder": sys.argv[3]}
        text = json.dumps(lic, sort_keys=True).encode("utf-8")
        lic["sig"] = sign(private, text).hex()
        out = ROOT / f"{sys.argv[2]}.license.json"
        out.write_text(json.dumps(lic, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{out.name}: the buyer puts it into %LOCALAPPDATA%\\OYPlayer\\skins\\licenses\\{sys.argv[2]}.json")
        return 0
    if sys.argv[1:]:
        raise SystemExit(__doc__)

    out_dir = ROOT / "src" / "oyplayer" / "skins"
    out_dir.mkdir(exist_ok=True)
    for path in sorted(SOURCES.glob("*.json")):
        source = json.loads(path.read_text(encoding="utf-8"))
        picture = path.with_suffix(".png")
        if picture.exists():
            source["look"]["preview"] = base64.b64encode(picture.read_bytes()).decode("ascii")
        look = source["look"]
        sealed = seal(private, source)
        # the player's own code must open what was sealed, with the key it carries
        header, opened = skins.open_skin(sealed, secret())
        if opened != look:
            raise SystemExit(f"{path.name}: the player reads back something else")
        (out_dir / f"{header['id']}.oyskin").write_bytes(sealed)
        print(f"{path.name} -> {header['id']}.oyskin ({len(sealed)} bytes, "
              f"sha256 {hashlib.sha256(sealed).hexdigest()[:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
