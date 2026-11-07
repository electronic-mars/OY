"""Write the text of a release page: the version's CHANGELOG section, how to install, how to check.

    python tools/release_notes.py <version> <installer> <out.md>
"""
import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    version, installer, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    log = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    found = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", log, re.S | re.M)
    if not found or not found.group(1).strip():
        raise SystemExit(f"CHANGELOG.md has no section for {version}")
    sha = hashlib.sha256(installer.read_bytes()).hexdigest()
    # on GitHub Actions the page names the run that built the file; elsewhere it says nothing
    run = os.environ.get("GITHUB_RUN_ID")
    built = (f"\nBuilt from this tag's source by [this GitHub Actions run]"
             f"({os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{run}).\n"
             if run else "")
    out.write_text(f"""{found.group(1).strip()}

### Install
Download `{installer.name}` below and run it. It installs for the current user without administrator rights; Windows 10 1809 or later. A player that is already installed updates itself: About › Update and restart.

The installer is not code-signed, so Windows SmartScreen will warn on first start: choose «More info», then «Run anyway».

### Check the download
SHA-256 of `{installer.name}`: `{sha}`

In PowerShell, `Get-FileHash .\\{installer.name} -Algorithm SHA256` must print the same hash.
{built}""", encoding="utf-8")
    print(f"notes for {version} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
