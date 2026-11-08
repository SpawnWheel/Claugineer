"""Driver notes: "I'm understeering here" pinned to a spot on the track.

Stored in data/notes.json so Claude (the race engineer) can read them next to the laps.
Each note: id, created, track, variation, car, dist (m from the line), x/z (map position),
corner (nearest corner id/name), session/lap it refers to (optional), text, status
("open" | "resolved"), resolution (the engineer's answer), resolved_at.
"""
import os
import threading
import time
import uuid

from .storage import read_json, write_json

_LOCK = threading.Lock()


def path(store):
    return os.path.join(store.root, "notes.json")


def load(store):
    return read_json(path(store), {"notes": []}) or {"notes": []}


def for_combo(store, track, variation, car, include_resolved=True):
    out = [n for n in load(store)["notes"]
           if n.get("track") == track and n.get("variation") == variation and n.get("car") == car]
    if not include_resolved:
        out = [n for n in out if n.get("status") != "resolved"]
    return sorted(out, key=lambda n: n.get("dist") or 0)


def add(store, meta, body, corners=None):
    dist = float(body.get("dist") or 0)
    near = None
    for c in corners or []:
        if near is None or abs(c["apex_m"] - dist) < abs(near["apex_m"] - dist):
            near = c
    n = {"id": uuid.uuid4().hex[:10], "created": time.strftime("%Y-%m-%d %H:%M:%S"),
         "track": meta["track"], "variation": meta["variation"], "car": meta["car"],
         "dist": round(dist, 1), "x": body.get("x"), "z": body.get("z"),
         "corner": near["id"] if near else None, "corner_name": near["name"] if near else None,
         "from_apex_m": round(dist - near["apex_m"]) if near else None,
         "session": body.get("session"), "lap": body.get("lap"),
         "source": body.get("source", "chart"), "text": (body.get("text") or "").strip()[:500],
         "status": "open", "resolution": None}
    with _LOCK:
        d = load(store)
        d["notes"].append(n)
        write_json(path(store), d)
    return n


def update(store, nid, **fields):
    with _LOCK:
        d = load(store)
        for n in d["notes"]:
            if n["id"] == nid:
                n.update(fields)
        write_json(path(store), d)


def delete(store, nid):
    with _LOCK:
        d = load(store)
        d["notes"] = [n for n in d["notes"] if n["id"] != nid]
        write_json(path(store), d)


def brief_section(store, meta):
    ns = for_combo(store, meta["track"], meta["variation"], meta["car"], include_resolved=False)
    if not ns:
        return ""
    L = ["", "## Driver notes (open - analyse these, then mark resolved in data/notes.json)"]
    for n in ns:
        where = "%s m" % int(n["dist"])
        if n.get("corner_name") is not None:
            where += " (%+d m from %s apex)" % (n.get("from_apex_m") or 0, n["corner_name"])
        lap = " · about lap %s of %s" % (n["lap"], n["session"]) if n.get("lap") else ""
        L.append("- [%s] %s: \"%s\"%s (added %s)" % (n["id"], where, n["text"], lap, n["created"]))
    return "\n".join(L) + "\n"
