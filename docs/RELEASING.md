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
