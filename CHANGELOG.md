# Changelog

All notable changes to OY Player. Versions follow [Semantic Versioning](https://semver.org/).
Each version is a git tag `vX.Y.Z`; the installer for it is attached to the GitHub release of the same name.

## [Unreleased]

## [0.10.0] - 2026-10-29

First public preview.

### Player
- Plays local files and streams through libmpv with hardware decoding; a compact window in a Braun style with a key for every command.
- Playlist with next episodes found automatically, thumbnails, history, A-B repeat, frame preview over the seek bar, audio track, subtitles and volume remembered per file.
- Skipping openings and credits, a scheduler (pause, close, sleep, shut down), internet radio from `.lau` station files with stream recording, one instance, tray icon, media keys, file types registered on request.
- Picture card (aspect, zoom, rotation, colour), subtitle and sound menus, file information, settings in six sections with a key editor, a dark theme and a warm cream light theme.

### Look
- Sharp line icons (Lucide) drawn for the exact size and screen scaling.
- Every key is a raised cap with soft light along its edge and a soft shadow; keys grow with the window in three sizes; groups are split by thin rules.
- The time display shows seven-segment digits, with hundredths on the edit strip.
- The time scale reads in IBM Plex Mono with labels above the ticks; the volume and position sliders have brushed caps.
- Rounded window corners in Windows 11; menus, the settings window and other cards are rounded with soft shadows.

### Language
- English and Ukrainian: Ukrainian when Windows speaks Ukrainian, English otherwise, and a Language switch in Settings › Window that changes every text at once.
- The default audio and subtitle languages follow the interface language.
- The installer speaks English and Ukrainian.

### Editor
- Lossless cut and join of the file being watched (I, O, X), fragments from several files, preview, undo and redo.
- The timeline in edit mode has named tracks: a clip track with the fragments as blocks and a track for each drawing, in its ink; Ctrl+Shift+← and Ctrl+Shift+→ move the chosen fragment earlier or later.
- Text, arrows, rectangles and pencil over the picture, each with its own time range on the timeline.
- Saves beside the source at once; «Save as…» on the right button. The source file is never overwritten.

### Reliability and feel
- Nothing slow runs on the interface thread: file probing, folder reading, settings writes and the encoder check happen in the background.
- Failures are said in words with what to do: a file that does not open is passed over with its reason, a save onto a file another program holds says so on the edit strip, a dropped radio station is reconnected instead of ending the list.
- Keyboard areas and a screen reader tree for lists, menus and the edit strip.
- Snap Layouts on the maximize key in Windows 11.

### Distribution
- Per-user installer without administrator rights, with a version resource, Windows 10 1809 or later, and a clean update over an older version.
- GPL v3 licence, third-party notices and FFmpeg's licence beside the program.
- Not code-signed: Windows SmartScreen will warn on first start.
