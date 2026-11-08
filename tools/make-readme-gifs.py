"""Builds the README's GIFs, stills and the social preview from the marketing sources.

    python tools/make-readme-gifs.py [--story DIR] [--only NAME ...]

Sources (not in the repository):
  local/marketing/video/bb-*.mp4              screen recordings of the real window
  local/marketing/stills/*.png                window stills made by showcase.py
  <story>/OY-launch-full-story.mp4            the launch cartoon, 1280x720, ends on the title

Writes docs/demo/*.gif, docs/screenshots/*.webp and docs/social-preview.png.
Needs ffmpeg and ffprobe on the PATH, numpy and Pillow.
"""
import argparse
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
# local/ is git-ignored, so a worktree has none: read it from the main checkout.
VIDEO = Path("D:/Documents/Claude/Projects/kr4P/local/marketing/video")
STILLS = ROOT / "local/marketing/stills"
STORY_DIR = Path(r"D:\Documents\ClaudeScripts\gemini-out\oy-launch")
DEMO = ROOT / "docs/demo"
SHOTS = ROOT / "docs/screenshots"

# source file in VIDEO, start s, source length s, speed, crop, width, fps, colours, dither, still, hold s at end
#   dither: Bayer amplitude in 0..255 levels (0 = none)
#   still:  a pixel is redrawn only if it moved more than this from what the GIF shows
GIFS = {
    # The film footage changes every pixel, so these two get fewer frames, colours and a higher threshold.
    # drop a file, seek with the frame preview, 2x speed, a timer, Japanese subtitles
    "plays": ("bb-plays-16x9.mp4", 0.0, 15.0, 1.0, None, 860, 7, 96, 6, 26, 1.0),
    # Ctrl+E, cut the start and the end, a circle, an arrow, a caption, save
    "edit": ("bb-edit2.mp4", 0.0, 15.0, 1.0, None, 900, 10, 256, 6, 10, 1.0),
    # two annotated screenshots of a frame, from two films
    "shot": ("bb-shot2.mp4", 0.0, 15.6, 1.0, None, 860, 7, 96, 6, 26, 1.0),
}

# README stills: published name -> source file, optional crop box (left, top, right, bottom)
SCREENSHOTS = {
    "series-playlist.webp": ("03-series-playlist.png", None),
    "skip-menu.webp": ("04-skip-menu.png", None),
    "frame-16x9.webp": ("06-editor-frame-16x9.png", None),
    "keys.webp": ("08-keys.png", None),
}
SHOT_WIDTH = 1200

BAYER4 = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) + 0.5) / 16 - 0.5


def ffmpeg(*args: str) -> bytes:
    return subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
                          capture_output=True, check=True).stdout


def size_of(clip: Path) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0", str(clip)],
                         capture_output=True, text=True, check=True).stdout
    w, h = out.split()[0].split(",")
    return int(w), int(h)


def make_gif(name: str) -> Path:
    """ffmpeg cuts and scales; the GIF itself is written here.

    The sources are compressed video, so every pixel flickers a little from
    frame to frame, and a plain palettegen/paletteuse GIF stores the whole
    picture again each frame. Here a pixel is redrawn only when it moved more
    than `still` away from what the GIF already shows; everything else is
    transparent and costs almost nothing. Ordered (Bayer) dithering keeps a
    still area identical between frames, unlike error diffusion.
    """
    src, start, length, speed, crop, width, fps, colours, dither, still, hold = GIFS[name]
    clip = VIDEO / src
    cw, ch = crop[:2] if crop else size_of(clip)
    height = round(width * ch / cw / 2) * 2
    chain = [f"crop={cw}:{ch}:{crop[2]}:{crop[3]}"] if crop else []
    if speed != 1.0:
        chain.append(f"setpts=PTS/{speed}")
    chain += [f"fps={fps}", f"scale={width}:{height}:flags=lanczos"]
    vf = ",".join(chain)
    cut = ["-ss", str(start), "-t", str(length), "-i", str(clip)]

    # One palette for the whole clip; the last index is kept for "unchanged".
    palette = DEMO / f".{name}-palette.png"
    ffmpeg(*cut, "-vf", f"{vf},palettegen=max_colors={colours - 1}:reserve_transparent=0", str(palette))
    pal = np.asarray(Image.open(palette).convert("RGB")).reshape(-1, 3)[: colours - 1].astype(np.int32)
    palette.unlink()
    keep = len(pal)

    raw = ffmpeg(*cut, "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-")
    frames = np.frombuffer(raw, np.uint8).reshape(-1, height, width, 3).astype(np.int32)

    # nearest palette entry through a 32x32x32 lookup table
    grid = np.stack(np.meshgrid(*[np.arange(32)] * 3, indexing="ij"), -1).reshape(-1, 3) * 8 + 4
    lut = np.empty(len(grid), np.uint8)
    for i in range(0, len(grid), 2048):
        lut[i:i + 2048] = ((grid[i:i + 2048, None, :] - pal[None]) ** 2).sum(-1).argmin(1)

    yy, xx = np.mgrid[0:height, 0:width]
    offset = (BAYER4[yy % 4, xx % 4] * dither)[..., None]
    shown = None
    images = []
    for n, f in enumerate(frames):
        q = np.clip(f + offset, 0, 255).astype(np.int32) >> 3
        idx = lut[(q[..., 0] << 10) | (q[..., 1] << 5) | q[..., 2]]
        # compare with the source as it was when last drawn, not with its palette colour
        moved = None if shown is None else np.abs(f - shown).max(-1) > still
        # The first and last frames and every cut (most of the picture moved) are drawn whole:
        # a fade or a sliding window leaves no stale patches below the threshold.
        if moved is None or n == len(frames) - 1 or moved.mean() > 0.5:
            shown, out = f, idx
        else:
            out = np.where(moved, idx, keep).astype(np.uint8)
            shown = np.where(moved[..., None], f, shown)
        images.append(out)
    durations = [round(1000 / fps)] * len(images)
    durations[-1] += round(hold * 1000)

    flat = pal.astype(np.uint8).ravel().tolist() + [0, 0, 0]
    pil = []
    for a in images:
        im = Image.fromarray(a, "P")
        im.putpalette(flat)
        pil.append(im)
    out = DEMO / f"{name}.gif"
    pil[0].save(out, save_all=True, append_images=pil[1:], duration=durations, loop=0,
                transparency=keep, disposal=1, optimize=False)
    return out


def make_stills() -> list[Path]:
    made = []
    for out_name, (src, box) in SCREENSHOTS.items():
        im = Image.open(STILLS / src).convert("RGB")
        if box:
            im = im.crop(box)
        im = im.resize((SHOT_WIDTH, round(im.height * SHOT_WIDTH / im.width)), Image.LANCZOS)
        out = SHOTS / out_name
        im.save(out, quality=88, method=6)  # lossy WebP: the cartoon's sky would band in a 256-colour PNG
        made.append(out)
    return made


def make_preview(story: Path) -> Path:
    """GitHub's social preview, 1280x640: the cartoon's title card."""
    out = ROOT / "docs/social-preview.png"
    ffmpeg("-sseof", "-0.2", "-i", str(story / "OY-launch-full-story.mp4"), "-frames:v", "1",
           "-update", "1", "-vf", "crop=1280:640:0:40", str(out))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--story", type=Path, default=STORY_DIR)
    ap.add_argument("--only", nargs="*", default=None, help="gif names, 'stills' or 'preview'")
    a = ap.parse_args()
    DEMO.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    want = set(a.only) if a.only else set(GIFS) | {"stills", "preview"}
    made = [make_gif(n) for n in GIFS if n in want]
    if "stills" in want:
        made += make_stills()
    if "preview" in want:
        made.append(make_preview(a.story))
    for f in made:
        print(f"{f.relative_to(ROOT)}  {f.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
