# How to release a version

Releases are built on GitHub, not on a developer's machine: pushing a version tag is the whole act of publishing.

1. Pick the number by [Semantic Versioning](https://semver.org/): a fix raises the last number, a feature the middle one, a break the first.
2. Set it in `src/oyplayer/__init__.py` (`__version__`). The installer and the exe's version resource read it from there; the build refuses a tag that says otherwise.
3. In `CHANGELOG.md`, move what is under «Unreleased» into a new section `## [X.Y.Z] - date`. That section becomes the text of the release page.
4. Run the self-test: `tools\selftest.cmd` must pass in full. Then build (`tools\build.cmd`) and run the self-test of the built exe: create an empty `tests\next-run-exe`, run `tools\selftest.cmd` again.
5. Commit `Release X.Y.Z`, tag and push: `git tag -a vX.Y.Z -m "OY Player X.Y.Z"`, then `git push origin main --follow-tags`.

The tag starts `.github/workflows/release.yml` on a clean Windows machine. It takes libmpv and ffmpeg at pinned hashes, builds the player and the installer, starts the built player once, signs the installer and publishes the release with two files: `OYPlayer-X.Y.Z-setup.exe` and `latest.json`. Every push to a branch runs the same build without publishing, so a broken build shows up before a tag does.

Installed players ask for `latest.json` once a day, put a dot on the About key when a newer version is out, and install it with About › Update and restart.

## The release key

The player installs only an installer signed by the release key (`src/oyplayer/update.py`, checked by Windows' own CNG). The public half is `PUBLIC_KEY` in that file; the private half lives only in the repository secret `UPDATE_SIGNING_KEY` (Settings › Secrets and variables › Actions). A tag build without the secret stops before publishing, and the build checks its own signature with the player's code before it publishes.

`tools/make_update_key.py` makes a new pair. Losing the private half is not fatal: a new pair goes out with the next release, and everyone updates once by hand. Leaking it is: whoever holds it can make an installed player run anything.

## The release page and trust

`tools/release_notes.py` writes the release page from the CHANGELOG section and adds how to check the download: the installer's SHA-256, the `Get-FileHash` command and a link to the Actions run that built it. Every run, a branch run too, shows that text in its summary, so the page can be read before a tag publishes it.

## winget

The package is `ElectronicMars.OYPlayer` (free in winget-pkgs as of 2026-11-07). Its manifests are in `winget/`, in the multi-file 1.12 schema, for one version at a time. They describe the Inno installer as winget sees it: per-user (`Scope: user`), silent install by winget's own Inno switches, the uninstall entry `{D675D294-D145-4198-8922-8952E87FD305}_is1` with publisher «Oleksandr Kyrychenko» (as `tools/installer.iss` writes it).

After a release is published:

1. `python tools/winget_manifest.py X.Y.Z` rewrites `winget/` from the release on GitHub: version, installer address, SHA-256 and date. Commit it.
2. `winget validate --manifest winget` must say «Manifest validation succeeded».
3. Optional, an install test on a machine where installing it is fine: `winget settings --enable LocalManifestFiles` (administrator), then `winget install --manifest winget`.
4. Submit it from the electronic-mars account, either way:
   - **wingetcreate** (`winget install Microsoft.WingetCreate`): `wingetcreate submit --token <a GitHub token with public_repo> winget`. It forks microsoft/winget-pkgs into the account and opens the pull request.
   - **by hand:** fork <https://github.com/microsoft/winget-pkgs>, copy the three files to `manifests/e/ElectronicMars/OYPlayer/X.Y.Z/`, commit, open a pull request and agree to the CLA when the bot asks (once).

   The first pull request is reviewed by people and may take days; the validation bot also installs the package in a sandbox and scans it. Later versions: the same two commands with the new number, or `wingetcreate update ElectronicMars.OYPlayer --version X.Y.Z --urls <installer address> --submit --token <token>`.

The player updates itself, so winget's own upgrades matter only to people who install with it.

## Code signing through SignPath Foundation

SignPath Foundation signs open-source projects for free with a certificate issued to «SignPath Foundation» (it, not the author, is the publisher Windows shows). Its conditions (<https://signpath.org/terms>), as they apply here:

- [x] OSI-approved licence for all components, no commercial dual licence: GPL v3.
- [ ] **No proprietary component.** The skins' content is encrypted with the secret `SKIN_KEY`, and a build without it opens no skin: settle with SignPath whether that counts as proprietary content before applying, or leave the encrypted skins out of the signed installer.
- [x] Built from public source on CI in a verifiable way: GitHub Actions, `.github/workflows/release.yml`. Signing adds a SignPath step to that workflow (their GitHub action), and every signing request is approved by hand.
- [x] Released and documented: releases on GitHub, functionality described in README.
- [ ] Reputation: SignPath checks that the program is known before signing an executable people download (stars, downloads, mentions, the winget package help).
- [ ] Multi-factor authentication on the GitHub account and the SignPath account.
- [ ] A «Code signing policy» section in README and on the release pages: «Free code signing provided by SignPath.io, certificate by SignPath Foundation», the team roles (committers and reviewers, approvers: here one person) and a privacy statement. The player sends nothing about the user; it only fetches `latest.json` from GitHub once a day, which the statement should say.
- [x] Uninstallation provided, no hidden system changes, no malware or bundled offers.
- [ ] Binaries signed by the project must carry product name «OY Player» and one version in their metadata; libmpv, ffmpeg and Qt stay unsigned upstream files inside the signed installer, which is allowed.

Apply at <https://signpath.org/apply> when the unchecked items are done.
