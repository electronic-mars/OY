"""Sign the installer and write latest.json, the description the player reads.

Runs on the build server after the installer is built and before the release is
created. The private key arrives through the environment from the repository secret
and is never written to disk.

    python tools/sign_release.py <installer> <version> <download-url>

Writes latest.json next to the installer; it goes onto the release under exactly
that name (src/oyplayer/update.py asks for it at releases/latest/download/latest.json).
"""
import json
import os
import sys
from pathlib import Path

SECRET_NAME = "UPDATE_SIGNING_KEY"

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, utils
except ImportError:
    raise SystemExit("pip install -r requirements-build.txt")


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    installer, version, url = Path(sys.argv[1]), sys.argv[2], sys.argv[3]

    pem = os.environ.get(SECRET_NAME, "").strip()
    if not pem:
        raise SystemExit(f"{SECRET_NAME} is not set: nothing would be signed, and a release "
                         "nobody can update to is worse than no release")
    lines = pem.splitlines()
    try:
        private = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    except (ValueError, TypeError) as e:
        # what is wrong with it, never what is in it
        begins = lines[0].strip() == "-----BEGIN PRIVATE KEY-----"
        ends = lines[-1].strip() == "-----END PRIVATE KEY-----"
        raise SystemExit(f"{SECRET_NAME} is not a readable PEM private key: {len(lines)} lines, "
                         f"BEGIN line {'present' if begins else 'missing'}, END line "
                         f"{'present' if ends else 'missing'} ({type(e).__name__})")
    if not isinstance(private, ec.EllipticCurvePrivateKey):
        raise SystemExit("the release key is not an elliptic curve key")

    der = private.sign(installer.read_bytes(), ec.ECDSA(hashes.SHA256()))
    # Windows wants the two halves end to end (r||s, 32 bytes each), not DER.
    r, s = utils.decode_dss_signature(der)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")

    # Check our own work with the player's own code against the key the player carries:
    # a private key that drifted from PUBLIC_KEY would ship an update nobody can install.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from oyplayer import update
    if not update.verify(installer, raw):
        raise SystemExit(f"the signature does not match the key inside the player: the key in "
                         f"{SECRET_NAME} is not the pair of PUBLIC_KEY in src/oyplayer/update.py")

    feed = {"version": version.lstrip("v"),
            "platforms": {"windows-x86_64": {"url": url, "signature": raw.hex()}}}
    out = installer.parent / "latest.json"
    out.write_text(json.dumps(feed, indent=2) + "\n", encoding="utf-8")
    print(f"signed {installer.name} -> {out}, and the player's own check accepts it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
