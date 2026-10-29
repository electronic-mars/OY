"""Make the pair of keys that decides who may publish an update.

Run once, on a machine you trust, and never again unless the private half is
lost or leaked. The private half signs releases and lives only in the
repository's secrets; the public half is compiled into the player, and it is
what makes an update from anybody else impossible to install.

    .venv\\Scripts\\python tools\\make_update_key.py

It prints the lines to paste into PUBLIC_KEY in src/oyplayer/update.py and
writes the private key to a file the repository ignores. Put that file's
contents into the repository secret named below (GitHub: Settings > Secrets and
variables > Actions > New repository secret), then delete the file.

Losing the private key is not fatal: a new pair goes out with the next release
and everyone updates once by hand. Leaking it is: whoever has it can hand a
running player on someone else's machine any executable they like.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_NAME = "UPDATE_SIGNING_KEY"
PRIVATE_FILE = ROOT / ".update-signing-key.pem"

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
except ImportError:
    raise SystemExit("pip install -r requirements-build.txt")

if PRIVATE_FILE.exists():
    raise SystemExit(f"{PRIVATE_FILE.name} is already here. Delete it on purpose "
                     "if you really mean to replace the release key.")

private = ec.generate_private_key(ec.SECP256R1())
numbers = private.public_key().public_numbers()
public = numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big")

PRIVATE_FILE.write_bytes(private.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption()))

hexed = public.hex()
print("Paste this into PUBLIC_KEY in src/oyplayer/update.py:\n")
print(f'    "{hexed[:64]}"')
print(f'    "{hexed[64:]}")')
print(f"\nThe private key is in {PRIVATE_FILE.name} (the repository ignores it).")
print(f"Put its whole contents into the repository secret {SECRET_NAME}, then delete the file.")
sys.exit(0)
