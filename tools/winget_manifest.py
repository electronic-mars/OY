"""Write the winget manifests in winget/ for a published release.

    python tools/winget_manifest.py <version>        e.g. 0.15.0

Reads the release v<version> from GitHub (one unauthenticated API request) and takes the
installer's address, SHA-256 and date from it, so the manifests describe the very file the
release page offers. winget/ holds one version at a time: the one to submit to winget-pkgs
(docs/RELEASING.md, «winget»).
"""
import json
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "electronic-mars/OY"
ID = "ElectronicMars.OYPlayer"
SCHEMA = "1.12.0"
# Inno Setup writes its uninstall entry under the installer's AppId (tools/installer.iss) + "_is1"
PRODUCT_CODE = "{D675D294-D145-4198-8922-8952E87FD305}_is1"
HEAD = "# yaml-language-server: $schema=https://aka.ms/winget-manifest.{kind}.{schema}.schema.json\n\n"


def release(version):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/tags/v{version}",
                                 headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": "oyplayer-winget-manifest"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    name = f"OYPlayer-{version}-setup.exe"
    asset = next((a for a in data["assets"] if a["name"] == name), None)
    if asset is None:
        raise SystemExit(f"release v{version} has no {name}")
    digest = asset.get("digest") or ""
    if not digest.startswith("sha256:"):
        raise SystemExit(f"GitHub gives no SHA-256 for {name}")
    return asset["browser_download_url"], digest[7:].upper(), data["published_at"][:10]


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    version = sys.argv[1].lstrip("v")
    url, sha, date = release(version)
    files = {
        "version": f"""PackageIdentifier: {ID}
PackageVersion: {version}
DefaultLocale: en-US
ManifestType: version
ManifestVersion: {SCHEMA}
""",
        "installer": f"""PackageIdentifier: {ID}
PackageVersion: {version}
InstallerType: inno
Scope: user
InstallModes:
- interactive
- silent
- silentWithProgress
UpgradeBehavior: install
MinimumOSVersion: 10.0.17763.0
ReleaseDate: {date}
ProductCode: '{PRODUCT_CODE}'
AppsAndFeaturesEntries:
- DisplayName: OY Player
  Publisher: Oleksandr Kyrychenko
  ProductCode: '{PRODUCT_CODE}'
Installers:
- Architecture: x64
  InstallerUrl: {url}
  InstallerSha256: {sha}
ManifestType: installer
ManifestVersion: {SCHEMA}
""",
        "locale.en-US": f"""PackageIdentifier: {ID}
PackageVersion: {version}
PackageLocale: en-US
Publisher: Oleksandr Kyrychenko
PublisherUrl: https://github.com/electronic-mars
PublisherSupportUrl: https://github.com/{REPO}/issues
Author: Oleksandr Kyrychenko
PackageName: OY Player
PackageUrl: https://github.com/{REPO}
License: GPL-3.0
LicenseUrl: https://github.com/{REPO}/blob/main/LICENSE
ShortDescription: A free, open-source video player for Windows that also cuts the video you are watching.
Description: |-
  OY Player plays local files and streams through libmpv, with hardware decoding, a playlist that finds the next episodes, skipping of openings and credits, and a key for every command.
  Mark a piece with I and O and save it losslessly, without re-encoding; join pieces from several files; draw text, arrows and shapes over the picture and save them into the clip.
  No ads, no telemetry, no account.
Moniker: oyplayer
Tags:
- libmpv
- media-player
- mpv
- open-source
- video
- video-cutter
- video-player
ReleaseNotesUrl: https://github.com/{REPO}/releases/tag/v{version}
ManifestType: defaultLocale
ManifestVersion: {SCHEMA}
""",
    }
    out = ROOT / "winget"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    for kind, body in files.items():
        schema_kind = "defaultLocale" if kind.startswith("locale.") else kind
        name = f"{ID}.yaml" if kind == "version" else f"{ID}.{kind}.yaml"
        (out / name).write_text(HEAD.format(kind=schema_kind, schema=SCHEMA) + body,
                                encoding="utf-8", newline="\n")
    print(f"winget/ now describes {ID} {version}: {url}\n  SHA-256 {sha}, released {date}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
