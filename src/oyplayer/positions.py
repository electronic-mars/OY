"""What each file was left with: where it stopped, the sound and subtitle tracks, the volume."""
import json

from .log import home, write_later

KEEP = 2000   # most recent files remembered
SETUP = ("aid", "sid", "volume")


class Positions:
    def __init__(self):
        self._file = home() / "positions.json"
        try:
            saved = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        # files written before tracks and volume were kept hold just the position
        self._d = {p: v if isinstance(v, dict) else {"pos": v} for p, v in saved.items()}

    def remember(self, path, pos, duration, setup):
        """setup: what was changed in this file (aid, sid, volume); the rest stays as kept."""
        rec = self._d.pop(path, {})
        rec.update(setup)
        # Only a real interruption is worth resuming: not the first seconds, not the credits.
        if duration > 60 and 10 < pos < duration - 20:
            rec["pos"] = round(pos, 1)
        else:
            rec.pop("pos", None)
        if rec:
            self._d[path] = rec
            while len(self._d) > KEEP:
                self._d.pop(next(iter(self._d)))
        write_later(self._file, json.dumps(self._d, ensure_ascii=False))

    def position(self, path):
        return self._d.get(path, {}).get("pos")

    def setup(self, path):
        rec = self._d.get(path, {})
        return {k: rec[k] for k in SETUP if k in rec}
