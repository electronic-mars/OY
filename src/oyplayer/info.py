"""File information: ffprobe's view of a file, in readable rows."""
import json
import shutil
import subprocess
from pathlib import Path

from .i18n import dec, tr

_FFPROBE = shutil.which("ffprobe")


def _dur(s):
    s = int(float(s or 0))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _rate(r):
    try:
        n, d = (int(x) for x in str(r).split("/"))
        return tr("fps", dec(f"{n / d:.3f}".rstrip("0").rstrip("."))) if d else ""
    except ValueError:
        return ""


def _kbps(b):
    return tr("kbps", int(b) // 1000) if b and str(b).isdigit() else ""


def _size(n):
    n = float(n)
    units = tr("size_units").split("|")
    for unit in units:
        if n < 1024 or unit == units[-1]:
            return dec(f"{n:.1f} {unit}") if unit != units[0] else f"{int(n)} {unit}"
        n /= 1024


def probe_sections(path):
    if not _FFPROBE or not Path(path).is_file():
        return [{"title": tr("info_file"), "rows": [{"k": tr("info_path"), "v": path}]}]
    r = subprocess.run([_FFPROBE, "-v", "error", "-show_format", "-show_streams", "-show_chapters",
                        "-of", "json", path], capture_output=True, text=True, encoding="utf-8",
                       timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    data = json.loads(r.stdout or "{}")
    fmt = data.get("format", {})
    tags = {k.lower(): v for k, v in fmt.get("tags", {}).items()}
    rows = [("name", Path(path).name), ("folder", str(Path(path).parent)),
            ("size", _size(fmt.get("size", 0))), ("duration", _dur(fmt.get("duration"))),
            ("container", fmt.get("format_long_name", "")), ("bitrate_total", _kbps(fmt.get("bit_rate"))),
            ("title", tags.get("title", "")), ("artist", tags.get("artist", "")),
            ("album", tags.get("album", "")), ("year", tags.get("date", "")),
            ("chapters", str(len(data.get("chapters", []))) if data.get("chapters") else "")]
    sections = [{"title": tr("info_file"), "rows": [{"k": tr("info_" + k), "v": v} for k, v in rows if v]}]
    kinds = {"video": "info_video", "audio": "info_audio", "subtitle": "info_subs"}
    counters = {}
    for st in data.get("streams", []):
        kind = st.get("codec_type")
        if kind not in kinds or st.get("disposition", {}).get("attached_pic"):
            continue
        counters[kind] = counters.get(kind, 0) + 1
        t = st.get("tags", {})
        rows = [("format", st.get("codec_long_name") or st.get("codec_name", "")),
                ("profile", st.get("profile", "")), ("lang", t.get("language", "")),
                ("title", t.get("title", ""))]
        if kind == "video":
            rows += [("frame", f"{st.get('width')}×{st.get('height')}"),
                     ("aspect", st.get("display_aspect_ratio", "")),
                     ("fps", _rate(st.get("avg_frame_rate"))),
                     ("bitrate", _kbps(st.get("bit_rate"))),
                     ("color", " ".join(x for x in (st.get("pix_fmt"), st.get("color_space"),
                                                  st.get("color_transfer")) if x))]
        elif kind == "audio":
            rows += [("channels", f"{st.get('channels')} ({st.get('channel_layout', '')})"),
                     ("rate", tr("hz", st.get("sample_rate"))), ("bitrate", _kbps(st.get("bit_rate")))]
        title = tr(kinds[kind]) + (f" #{counters[kind]}" if counters[kind] > 1 else "")
        sections.append({"title": title, "rows": [{"k": tr("info_" + k), "v": v} for k, v in rows if v and v != "None"]})
    return sections
