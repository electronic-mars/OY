# Changelog

All notable changes to OY Player. Versions follow [Semantic Versioning](https://semver.org/).
Each version is a git tag `vX.Y.Z`; the installer for it is attached to the GitHub release of the same name.

## [Unreleased]

### Fixed
- After the window changed size the first frame of the video was drawn at the old size in the lower left corner; a paused video stayed so, shifted and small, in full screen. The picture is now drawn at the window's real size from the first frame.
- Going full screen, the panel flashed across the bottom of the grown window: it faded out instead of going at once. It now goes at once.
- In and out of full screen the panels and the title bar step aside at the click and stay away until the window has finished changing: Windows grows it in more than one step, and the panel rode up the middle of the screen. Leaving, they come back at once in the very frame the window is small again. The picture follows the window's real size. Esc and the title bar key leave the same way.
- No Windows animation when the window changes: going full screen and back it blended the old and new window over what lay under it and held a dark frame. The window now changes at once.
- For two seconds after the middle button even a real move of the mouse does not bring the panels back.
- Going full screen the window seemed to jump into the upper left corner first, and leaving it the big picture showed cut by the small window for a moment: Windows shows a window that changed size once with its old picture until the new one is drawn. The screen is now held still for that moment (about 40 ms), so only the window before and after is ever seen. The taskbar and other always-on-top bars step back under it instead of standing over the picture for a frame.

### Changed
- The window is drawn with Direct3D 11, as Windows' own programs are, instead of OpenGL: full screen in and out is quicker, never blacks the screen out, and screen recorders see it. A computer whose video driver cannot hand mpv's picture to Direct3D keeps the OpenGL window; there a full-screen window is 1 px taller than its monitor, which keeps the video card's OpenGL driver from taking the picture past the desktop (a black screen for a moment on each switch, black in screen recorders), and has no Windows outline or rounded corners.
- A picture smaller than the window's least width grows to it when a file opens: edge to edge with the panel, no black bars at the sides.

## [0.12.0] - 2026-10-30

### Fixed
- The picture card's brightness, contrast and saturation sliders set nothing: each read its own empty name instead of the picture's setting.
- A key pressed in (the open list, a key held down) looked cut off along its top; it now sinks into its own outline.

### Changed
- Keys that are on show their sign in the accent instead of a lamp dot; the playlist tabs and menus lost their dots too (menus mark the choice with a tick).
- Text is drawn with Windows' own hinting: sharper at small sizes.
- The playlist's frames have rounder, smooth corners.
- Settings: the language is a list (Windows' own, or each language by its name); the close key is in the upper right corner beside the section's name; «Defaults» puts the open section back (a second press confirms); About moved from the title bar into the settings as their last section, lit while an update waits.
- Settings › Window › Default player: video files, and with «Sound files too» music as well.
- The mouse: a click on the picture hides the panels (or pauses, as set), the middle button goes full screen, the back and forward buttons seek (or change the file); all in Settings › Controls.
- The editor's cut key shows scissors; «Cancel» is now «Close», with a cross.

### Panel (UI/UX council)
- Fewer keys: Open, Next frame, Fast forward and Video properties left the panel. Play opens a file when nothing is loaded and opens the speed menu on its right button; a click on the empty window opens a file; Ctrl+→, Ctrl+X and Shift+V still work.
- The subtitles key shows only for a file with subtitles; previous and next only with more than one file in the list.
- A right click on the picture opens a menu: open, speed, subtitles, sound, video properties, screenshot, file information.
- A speed other than 1× shows on the time display («×1,5»); a click on it goes back to 1×.
- Groups are set apart by space instead of rules; the time display stands in the middle of the panel.
- The wheel over the seek bar works as the arrows: 5 s, with Shift 30 s, with Ctrl one frame.

### Editor (UI/UX council)
- A new model: the edit holds the whole file from the start. I cuts off what is before here, O what is after, the scissors split the piece, Delete takes the chosen piece out. Pressing again only moves the border. The keys read as a ruler: |← ✂ →| and a bin (right click: start over).
- Without loss, a border moves to the keyframe before it as soon as that is known, and the cursor with it: what the timeline shows is what gets saved.
- «Result» plays the finished video from its start, with a bar of where in it you are; a click on the bar goes there.
- Drawing pauses the video; a new drawing on a frame that already shows drawings comes and goes together with them, so two arrows in a row stay together. Esc first puts the drawing tool down.
- The «EDITING» badge in the title bar closes the editor; Save stays off until something was cut or drawn.

### After the owner's look at the council's panel
- The fast-forward key is back with all it did (a click cycles the speed, the right button opens the speed menu). Settings stand first on the left; the time, the screenshot and the editor follow the sound, as in the concept.
- The Play key's right button opens a file; with nothing loaded a click on it opens one too.
- A click on the picture pauses again by default (hiding the panels is a choice in Settings › Controls).
- The middle button and a double click go full screen on the bare picture; the panels come back only when the pointer really moves.
- The list holds only the file you opened, by default; Settings › Playback › The list › Every opened file keeps them all. The list has a Clear key (press twice; Shift+Delete at once).
- No subtitles key on the panel: S turns them on and off, Alt+S and the picture's menu open their menu.
- Menus have taller rows, a sign on the left and the matching key on the right.
- One step between every two things on the panel.
- Full screen from the mouse stays on the bare picture: the panels vanish at once, a resting hand does not bring them back, the window's keys show only at the top edge.

### Editor, second part
- Turn the picture a quarter clockwise (Ctrl+R, or the key on the drawing card).
- The frame: as it is, 16:9 over a blurred copy of the picture, or 16:9 cut to fill — a phone video becomes a widescreen one. What the editor shows is what gets saved.
- A logo or any picture over the video: the picture key on the drawing card, or drop the file on the frame. It goes to the upper right, can be moved, sized by its corner, made 60 % or 30 % opaque, and has its own track on the timeline.
- These re-encode on saving; the strip says why.

## [0.11.1] - 2026-10-29

### Updates
- The player updates itself. Once a day it asks this project's GitHub page whether a newer version is out and puts a dot on the About key; About › Update and restart downloads the installer, checks its signature and starts the new version. Settings › Window › Look for updates turns the daily look off.
- It installs only what the release key signed: Windows checks the signature, and an installer that fails the check is deleted, not run.
- Releases are built on GitHub from the tagged source, with libmpv and ffmpeg at pinned versions.

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
