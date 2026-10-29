# How to release a version

1. Pick the number by [Semantic Versioning](https://semver.org/): a fix raises the last number, a feature the middle one, a break the first.
2. Set it in `src/oyplayer/__init__.py` (`__version__`). The installer and the exe's version resource read it from there.
3. In `CHANGELOG.md`, move what is under «Unreleased» into a new section `## [X.Y.Z] - date`.
4. Run the self-test: `tools\selftest.cmd` must pass in full.
5. Commit: `Release X.Y.Z`.
6. Tag and push: `git tag -a vX.Y.Z -m "OY Player X.Y.Z"`, then `git push origin main --follow-tags`.
7. Build: `tools\build.cmd`. Run the self-test of the built exe: create an empty `tests\next-run-exe`, run `tools\selftest.cmd`.
8. Publish the release on GitHub for the tag `vX.Y.Z`: the CHANGELOG section as the text, `dist\OYPlayer-X.Y.Z-setup.exe` as the asset, with its SHA-256 in the text (`certutil -hashfile dist\OYPlayer-X.Y.Z-setup.exe SHA256`). With the GitHub CLI: `gh release create vX.Y.Z dist\OYPlayer-X.Y.Z-setup.exe --title "OY Player X.Y.Z" --notes-file notes.md`.
