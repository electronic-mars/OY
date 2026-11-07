# Changelog

All notable changes to OY Player. Versions follow [Semantic Versioning](https://semver.org/).
Each version is a git tag `vX.Y.Z`; the installer for it is attached to the GitHub release of the same name.

## [Unreleased]

### Changed
- The empty window shows the player's own mark, its play key, over the name instead of a film; a click on it opens a file.

### Fixed
- 0.16.0 could close by itself now and then while a file opened: the new crash record wrote down every thread at each error mpv's scripts raise and catch themselves, many times a second, and that writing itself could crash. It now records only the thread that fails, and only a real crash.

## [0.16.0] - 2026-11-07

### Added
- If OY Player closed unexpectedly, the next start says so once, in a small card over the picture: «Report» opens a new GitHub issue already filled with the player's version, the Windows build and the error's line (no folders, no user name, no names of your videos), and «Open the log folder» shows the logs to attach. Native crashes are written to `last-crash.log` and the log of that run is kept as `oyplayer.previous.log`, both in `%LOCALAPPDATA%\OYPlayer`. Python errors go into the log with their trace.
- Issue forms for bug reports and feature requests, and a security policy: security problems are reported privately through GitHub.

### Changed
- Settings › About: two keys under the version, «Support the developer» (the site's ways to say thanks: Ko-fi, Patreon, Donatello, crypto) and «Developer's site» (the player's page there), and a quiet line to the source code on GitHub. The old «Thank» key went to a section of GitHub that does not exist.
- Installed apps link to the developer's site, the issues and the releases.

### Fixed
- On a computer without a video card driver (a bare virtual machine, Windows' basic display adapter) the player did not start at all: its check for the video card's Direct3D sharing failed on Windows' software OpenGL. It now plays through OpenGL there.

## [0.15.0] - 2026-11-07

### Added
- The interface in 39 languages, each listed by its own name: those Windows 11 is fully translated into, and Hindi, Indonesian, Vietnamese and Persian. The player starts in the one closest to Windows' own (Mexican Spanish in Latin American Spanish, Taiwanese Chinese in Traditional), and the settings' list holds the rest. Counts take each language's plural forms. Arabic, Persian and Hebrew mirror the window; the timeline and the keys under it keep running left to right. Every script is drawn in the Windows font made for it.
- Setup speaks 25 of these languages, those Inno Setup has a translation for.
- Audio and subtitle tracks in the interface's language come first, then English, in every language (it was Ukrainian or English only).
- YouTube and the other sites yt-dlp knows: drop a link on the window or copy it and press Ctrl+V. The first time, the player asks to download yt-dlp and Deno from their GitHub releases (about 65 MB), checks each against its published SHA-256 and plays the link; yt-dlp then updates itself once a week.
- Ctrl+V also opens a file copied in Explorer, or a copied path.
- Settings › General › File icons: the files OY Player opens can keep Windows' own video and sound icons, with the player's key in the corner. Sound files are offered as their own type, with their own icon.

### Changed
- A file opened from Explorer while the editor is open plays in the player: the clip just saved no longer opens straight into the edit. The edit stays, and Ctrl+E brings it back.

### Fixed
- Going full screen could leave a still picture of the whole monitor over everything until the player was closed, when Windows' call that sends the taskbar back failed. The still picture now always goes, within half a second at most.
- Files in a network folder (\\server\share): subtitles and a sound track loaded from a file there, an edit saved there and a list saved there now go to that folder; the server's name was dropped from the way. A picture from a network folder shows over the video.
- Restarting or shutting down Windows, or signing out, while a film plays keeps where it was for the next start, with the list and the volume. It was lost when Windows ended the player before it had written them.
- Several files opened together from Explorer open in one player, all of them in its list in their folder's order, instead of a player each.
- Editing without loss: when a border moves to its keyframe, the cursor goes with it only while it is still at the border. It no longer jumps back after the person has moved on, or after an undo.

## [0.14.1] - 2026-11-03

### Fixed
- In full screen a thin lit line ran along the monitor's edges round the black, with a lit rounded corner: Windows' own window outline, left on under Direct3D. Full screen is now black to the very edge.

## [0.14.0] - 2026-11-03

### Added
- A screenshot can open to be drawn on (Settings › Screenshot › «Open to draw on»): a window with the frame alone, no timeline, where arrows, rectangles, circles, lines, text and pictures go on it; then Copy, Save or Close. Pressing the screenshot key again while drawings are on it brings the window forward and keeps them.
- A saved screenshot shows its file name for three seconds with «Open the folder».
- Drawings, in the editor and on a screenshot: a circle among the shapes and black among the inks. Text being typed counts as entered when another tool is chosen, or on Save and Copy.

### Changed
- An inserted image is a picture, not a logo: its corners stretch and squeeze it freely, and it cannot be squeezed to nothing.
- A screenshot is written aside and the video does not stop for it; a PNG is 8-bit, a fraction of the size and the time. It is saved in the format chosen in Settings.
- The installer tells Windows when it is done, so files offered to the player show the new icon at once.
- The play key is a knob: a graphite bezel with a lit ring in the accent, inside it the face of a volume knob, lighter up and to the left and darker to its edge, and a larger sign set by its weight; it is drawn a little larger, without the dark ring the panel's groove had round it. The colour dial in Settings shows the same key.
- The player's icon is the new play key itself, round and edge to edge, its lit ring as the rim, with no square body round it: it fills its place in the tray and the taskbar. Each size is drawn on its own.
- The panel: the dark well now runs under the settings and play keys too, and the right keys (scheduler, on top, the list) sit in a well of their own.
- Settings: Appearance (formerly Skins) is the third section and holds the theme and the main colour as well as the skins; Window is now General. The settings window can be moved by its top strip, to watch the panel while a skin or the colour changes.
- About shows the play key as the program's mark in a card framed in the accent, and, each on a line of its own, the way to the project's site and to thanking its developer.
- Menus show each item's key on a small sunk cap and frame the row under the pointer in the accent; the scheduler's choices sit in wells, its times on the LCD glass.
- Skins: Default, Classic and Studio; Deck and Switcher are gone for now. The skin pictures in Settings show the current panel.
- The editor's title bar shows only the EDITING label: the scheduler and on-top keys are the player's alone again, and the editor closes from a key at the right end of the edit strip (or Esc).

### Fixed
- A screenshot that cannot be saved (a folder without rights, a full disk) says so and leaves no empty file; the player waits for a screenshot being written before it quits.

## [0.13.0] - 2026-11-01

### Added
- Skins. Settings has a Skins section with a card for each skin showing its panel: Default, Classic (the earlier look), Deck, Studio and Switcher. A skin is a sealed, signed `.oyskin` file; a damaged or changed file is skipped and never stops the player.
- The play key is the same in every skin: graphite lit from behind, its rim in the accent.
- Drawings have three line widths, thin, medium and thick, kept in the saved video too.
- Five inks for drawings: white, yellow, orange, blue and red.
- The chosen drawing shows its name and times on a plate over it; a rectangle's corners and an arrow's ends can be dragged.
- While editing, the title bar shows the picture's size and frame rate, and a Playlist key with the number of files.
- A right click on the time display copies the time shown.

### Changed
- The editor is laid out anew. The drawing tools sit over the middle of the picture. Up to six drawings each get a track of their own, named after the drawing with a dot of its ink; a bar is an outline in the drawing's ink with grips at its ends and its times inside. Over the scale the chosen drawing's times read «0:32.0 – 0:36.0 (4.0 s)».
- The editor's strip: the in, cut, out and delete keys are one capsule; the length with the number of fragments, and the encoding, are in frames of their own; «Result» has an eye. The separate Close key is gone: the × on the EDITING badge and Esc close the editor.
- While editing, the scheduler and always on top are in the title bar.

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
- Plays local files and streams through libmpv with hardware decoding; a compact window in a hardware style with a key for every command.
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
