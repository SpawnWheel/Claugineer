"""Local web server: dashboard + JSON API (stdlib only)."""
import json
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import analysis as an
from . import engine
from . import insights
from . import notes as nt
from .storage import read_json, write_json

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


class App:
    def __init__(self, store, cfg, recorder=None):
        self.store = store
        self.cfg = cfg
        self.recorder = recorder
        self.lock = threading.Lock()
        self.ref = None          # (sid, Lap) best lap of the current session for live delta

    # called by the recorder after each lap
    def on_lap(self, sid):
        with self.lock:
            res = engine.build(self.store, self.cfg, sid)
        if res and res.get("best_lap"):
            meta = self.store.load_session(sid)
            e = next(l for l in meta["laps"] if l["lap"] == res["best_lap"])
            self.ref = (sid, an.Lap(e, self.store.load_lap(sid, e["lap"]), meta["track_length"]))

    def analysis(self, sid, rebuild=False, remap=False):
        path = self.store.session_path(sid, "analysis.json")
        if rebuild or remap or not os.path.exists(path):
            with self.lock:
                return self._names(sid, engine.build(self.store, self.cfg, sid, remap=remap))
        return self._names(sid, read_json(path))

    def _names(self, sid, a):
        """Corner names + map landmarks always come from the track file (data/tracks), so a
        rename shows up in every session straight away, without re-analysing old sessions."""
        try:
            if not a or not a.get("track_map"):
                return a
            meta = self.store.load_session(sid)
            tm = read_json(self.store.track_map_path(meta["track"], meta["variation"])) or {}
            names = {c["id"]: c.get("name") or c["id"] for c in tm.get("corners") or []}
            for c in (a["track_map"].get("corners") or []) + (a.get("corners") or []):
                if c.get("id") in names:
                    c["name"] = names[c["id"]]
            for f in ((a.get("plan") or {}).get("focus") or []):
                if f.get("id") in names:
                    f["corner"] = names[f["id"]]
            a["track_map"]["landmarks"] = tm.get("landmarks") or []
        except Exception:
            pass
        return a

    def live(self):
        live = dict(self.recorder.live) if self.recorder else {"status": "viewer only"}
        if self.ref and live.get("session") == self.ref[0] and live.get("dist") is not None:
            try:
                live["delta"] = round(live["cur"] - self.ref[1].time_at(live["dist"]), 3)
                live["ref_lap"] = self.ref[1].n
            except Exception:
                pass
        return live

    def combo(self, sid):
        meta = self.store.load_session(sid)
        out = {"sessions": [], "laps": []}
        for s in self.store.sessions_for_combo(meta["track"], meta["variation"], meta["car"]):
            a = self.analysis(s)
            if not a or not a.get("laps"):
                continue
            out["sessions"].append({"id": s, "best": a.get("best_time"),
                                    "median": a["lap_trend"].get("median"),
                                    "theoretical": a.get("theoretical_corners")})
            for l in a["laps"]:
                if l["valid"] and not l["pit"]:
                    lc = a["lap_corners"].get(str(l["lap"])) or a["lap_corners"].get(l["lap"]) or {}
                    out["laps"].append({"session": s, "lap": l["lap"], "time": l["time"],
                                        "corners": {k: (v or {}).get("time") for k, v in lc.items()}})
        out["lap_trend"] = an.trend([l["time"] for l in out["laps"]], window=30)
        return out


def make_handler(app):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            if not isinstance(body, (bytes, bytearray)):
                body = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            try:
                if u.path in ("/", "/index.html"):
                    with open(os.path.join(WEB, "index.html"), "rb") as f:
                        return self._send(200, f.read(), "text/html; charset=utf-8")
                if u.path == "/api/status":
                    return self._send(200, app.live())
                if u.path == "/api/sessions":
                    return self._send(200, app.store.list_sessions())
                if u.path == "/api/analysis":
                    res = app.analysis(q["sid"], rebuild=q.get("rebuild") == "1")
                    return self._send(200, res or {})
                if u.path == "/api/trace":
                    laps = [int(x) for x in q["laps"].split(",") if x]
                    return self._send(200, an.compare_traces(app.store, q["sid"], laps) or {})
                if u.path == "/api/combo":
                    return self._send(200, app.combo(q["sid"]))
                if u.path == "/api/combos":
                    return self._send(200, insights.combos(app.store))
                if u.path == "/api/combo_laps":
                    return self._send(200, insights.combo_laps(app, q["sid"]))
                if u.path == "/api/notes":
                    m = app.store.load_session(q["sid"])
                    return self._send(200, nt.for_combo(app.store, m["track"], m["variation"], m["car"]))
                if u.path == "/api/habits_all":
                    return self._send(200, insights.habits_all(app))
                if u.path == "/api/traces":
                    refs = []
                    for item in q["laps"].split(","):
                        if "~" in item:
                            s_, n_ = item.rsplit("~", 1)
                            refs.append((s_, int(n_)))
                    return self._send(200, insights.traces(app.store, refs) or {})
                if u.path == "/api/brief":
                    p = app.store.session_path(q["sid"], "brief.md")
                    with open(p, "rb") as f:
                        return self._send(200, f.read(), "text/markdown; charset=utf-8")
                return self._send(404, {"error": "not found"})
            except Exception as e:  # keep the server alive
                return self._send(500, {"error": repr(e)})

        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            try:
                sid = body.get("sid")
                meta = app.store.load_session(sid)
                if u.path == "/api/setup":
                    p = app.store.setup_path(meta["car"], meta["track"], meta["variation"])
                    sheet = read_json(p, {}) or {}
                    if "values" in body:
                        sheet["values"] = body["values"]
                    if body.get("change"):
                        sheet.setdefault("changes", []).append(body["change"])
                    if "changes" in body:
                        sheet["changes"] = body["changes"]
                    write_json(p, sheet)
                    return self._send(200, app.analysis(sid, rebuild=True))
                if u.path == "/api/rename_corner":
                    p = app.store.track_map_path(meta["track"], meta["variation"])
                    tm = read_json(p)
                    for c in tm["corners"]:
                        if c["id"] == body["id"]:
                            c["name"] = body["name"].strip() or c["id"]
                    write_json(p, tm)
                    return self._send(200, app.analysis(sid, rebuild=True))
                if u.path == "/api/note_add":
                    a = app.analysis(sid) or {}
                    corners = (a.get("track_map") or {}).get("corners") or []
                    n = nt.add(app.store, meta, body, corners)
                    app.analysis(sid, rebuild=True)          # puts the note into brief.md
                    return self._send(200, n)
                if u.path == "/api/note_delete":
                    nt.delete(app.store, body["id"])
                    app.analysis(sid, rebuild=True)
                    return self._send(200, {"ok": True})
                if u.path == "/api/note_resolve":
                    nt.update(app.store, body["id"], status="resolved",
                              resolution=body.get("resolution"),
                              resolved_at=__import__("time").strftime("%Y-%m-%d %H:%M:%S"))
                    app.analysis(sid, rebuild=True)
                    return self._send(200, {"ok": True})
                if u.path == "/api/rebuild":
                    return self._send(200, app.analysis(sid, rebuild=True,
                                                        remap=bool(body.get("remap"))))
                return self._send(404, {"error": "not found"})
            except Exception as e:
                return self._send(500, {"error": repr(e)})
    return H


def serve(app, host, port):
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd
