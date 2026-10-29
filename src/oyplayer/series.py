"""The next episodes of a series.

A simpler rule compares the first four letters of two names after dropping [tags], spaces, "_"
and "-", and added every video after the opened one in the folder. That also takes
"Movie A" with "Movie B". Here two names are one series when, with [tags] and (tags)
dropped, they are the same text up to a number that differs: "Show S01E01 Pilot" and
"Show S01E02 The Return" are, "Movie A" and "Movie B" are not.
"""
import re
from pathlib import Path

VIDEO_EXT = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".webm", ".flv", ".m4v", ".ts", ".m2ts",
             ".mts", ".mpg", ".mpeg", ".vob", ".3gp", ".ogv", ".rm", ".rmvb", ".divx", ".asf"}


def _norm(name):
    # tags and the picture size ("1080p") are not the episode number
    name = re.sub(r"\[[^\]]*\]|\([^)]*\)|\b\d{3,4}p\b", " ", Path(name).stem.lower())
    return re.sub(r"[\s._\-]+", " ", name).strip()


def same_series(a, b):
    """Episodes of one series share the container: "film.mp4" and "film2.mkv" are not one."""
    if Path(a).suffix.lower() != Path(b).suffix.lower():
        return False
    a, b = _norm(a), _norm(b)
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    if i == min(len(a), len(b)) or not (a[i].isdigit() and b[i].isdigit()):
        return False
    while i and a[i - 1].isdigit():      # back to where the differing number starts
        i -= 1
    return sum(c.isalpha() for c in a[:i]) >= 3


def following(path):
    """The videos after `path` in its folder (in natural order) that belong to its series."""
    from .playlist import natural_key
    p = Path(path)
    if p.suffix.lower() not in VIDEO_EXT or not p.is_file():
        return []
    files = sorted((f for f in p.parent.iterdir() if f.suffix.lower() in VIDEO_EXT and f.is_file()),
                   key=lambda f: natural_key(f.name))
    later = files[files.index(p) + 1:] if p in files else []
    return [str(f) for f in later if same_series(p.name, f.name)]
