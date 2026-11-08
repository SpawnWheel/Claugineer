"""Files on disk. Everything is plain JSON / gzipped CSV so any tool (or Claude) can read it.

data/
  sessions/<YYYY-MM-DD_HHMM>__<track>__<car>__<type>/
      session.json         meta + one entry per lap (times, sectors, tyres, flags)
      laps/L007.csv.gz     full trace for lap 7 (columns: frames.SAMPLE_COLS)
      analysis.json        full machine-readable analysis (rebuilt after every lap)
      brief.md             short engineer brief (rebuilt after every lap)
  tracks/<track>__<variation>.json   corner map (rename corners here)
  setups/<car>__<track>.json         setup sheet + change log you enter in the dashboard
  latest_brief.md / latest.json       pointers to the most recent session
"""
import csv
import gzip
import io
import json
import os
import re
import time

from .frames import SAMPLE_COLS


def slug(text):
    text = re.sub(r"[^A-Za-z0-9]+", "-", str(text)).strip("-").lower()
    return text or "unknown"


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


class Store:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        for sub in ("sessions", "tracks", "setups"):
            os.makedirs(os.path.join(self.root, sub), exist_ok=True)

    # ---- sessions
    def new_session_dir(self, ctx, session_type):
        name = "{}__{}__{}__{}".format(time.strftime("%Y-%m-%d_%H%M%S"),
                                       slug(ctx["track"] + " " + ctx["variation"]),
                                       slug(ctx["car"]), session_type)
        path = os.path.join(self.root, "sessions", name)
        os.makedirs(os.path.join(path, "laps"), exist_ok=True)
        return name

    def session_path(self, sid, *parts):
        return os.path.join(self.root, "sessions", sid, *parts)

    def list_sessions(self):
        out = []
        base = os.path.join(self.root, "sessions")
        for name in sorted(os.listdir(base), reverse=True):
            meta = read_json(os.path.join(base, name, "session.json"))
            if meta:
                laps = meta.get("laps", [])
                valid = [l["time"] for l in laps if l.get("valid") and not l.get("pit")]
                out.append({"id": name, "track": meta.get("track"),
                            "variation": meta.get("variation"), "car": meta.get("car"),
                            "type": meta.get("session_type"), "started": meta.get("started"),
                            "laps": len(laps), "best": min(valid) if valid else None})
        return out

    def load_session(self, sid):
        return read_json(self.session_path(sid, "session.json"))

    def save_session(self, sid, meta):
        write_json(self.session_path(sid, "session.json"), meta)

    def save_lap(self, sid, lap_no, samples):
        path = self.session_path(sid, "laps", "L%03d.csv.gz" % lap_no)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(SAMPLE_COLS)
        w.writerows(samples)
        with gzip.open(path, "wt", encoding="utf-8", compresslevel=5) as f:
            f.write(buf.getvalue())
        return os.path.basename(path)

    def load_lap(self, sid, lap_no):
        path = self.session_path(sid, "laps", "L%03d.csv.gz" % lap_no)
        with gzip.open(path, "rt", encoding="utf-8") as f:
            r = csv.reader(f)
            header = next(r)
            cols = {h: [] for h in header}
            for row in r:
                for h, v in zip(header, row):
                    cols[h].append(float(v))
        return cols

    # ---- track maps and setups
    def track_map_path(self, track, variation):
        return os.path.join(self.root, "tracks", slug(track) + "__" + slug(variation) + ".json")

    def setup_path(self, car, track, variation):
        return os.path.join(self.root, "setups",
                            slug(car) + "__" + slug(track) + "__" + slug(variation) + ".json")

    def sessions_for_combo(self, track, variation, car):
        res = []
        for s in self.list_sessions():
            if s["track"] == track and s["variation"] == variation and s["car"] == car:
                res.append(s["id"])
        return sorted(res)
