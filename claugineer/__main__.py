"""Claugineer - AMS2 / RaceRoom telemetry recorder, analyser and coach.

  python -m claugineer run        record the running game + dashboard (default)
                                  config.json "game": "auto" (default), "ams2" or "r3e"
  python -m claugineer serve      dashboard only (look at old sessions)
  python -m claugineer sim        demo: simulated laps through the whole pipeline
  python -m claugineer analyze    rebuild analysis for a session and print the brief
  python -m claugineer doctor     check the setup (shared memory, header layout, folders)
"""
import argparse
import glob
import json
import os
import sys
import threading
import time
import webbrowser

from . import engine
from .recorder import Recorder
from .server import App, serve
from .storage import Store

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_CFG = {
    "game": "auto",
    "data_dir": "data",
    "host": "127.0.0.1",
    "port": 8770,
    "sample_hz": 60,
    "player_name": "",
    "pressure_unit": "bar100",
    "consistency_gate_s": 0.5,
    "fast_corner_kmh": 120,
    "understeer_threshold": 0.15,
    "oversteer_threshold": -0.10,
    "bottoming_mm": 8,
    "open_browser": True,
    "car_profiles": {
        "GT3": {"hot_pressure_bar": [1.80, 1.90], "note": "Reiza staff guidance"},
        "Mini Cooper JCW": {"hot_pressure_bar": {"front": [2.65, 2.75]},
                             "note": "Donington data: best laps at ~2.7 bar hot front"},
    },
}


def load_cfg():
    path = os.path.join(APP_DIR, "config.json")
    cfg = json.loads(json.dumps(DEFAULT_CFG))
    if os.path.exists(path):
        try:
            user = json.load(open(path, encoding="utf-8"))
            for k, v in user.items():
                if k == "car_profiles":
                    cfg["car_profiles"].update(v)
                else:
                    cfg[k] = v
        except ValueError as e:
            print("config.json is not valid JSON (%s) - using defaults" % e)
    else:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CFG, f, indent=2)
    dd = cfg["data_dir"]
    cfg["data_dir"] = dd if os.path.isabs(dd) else os.path.join(APP_DIR, dd)
    return cfg


GAMES = ("ams2", "r3e")
GAME_LABEL = {"ams2": "AMS2", "r3e": "RaceRoom"}


def running_game():
    """'r3e', 'ams2', None (neither running) or 'unknown' (can't tell)."""
    from . import shm, shm_r3e
    r3e, ams2 = shm_r3e.game_running(), shm.game_running()
    if r3e:
        return "r3e"
    if ams2:
        return "ams2"
    if r3e is None and ams2 is None:
        return "unknown"
    return None


def open_reader(game):
    if game == "r3e":
        from .shm_r3e import Reader
    else:
        from .shm import Reader
    return Reader().open()


class LiveSource:
    """Reads whichever game is running. In "auto" mode a background thread checks the
    running processes every few seconds (the AMS2 mapping survives the game closing, so
    the process list is the reliable signal) and the reader switches games on its own."""

    def __init__(self, game="auto", log=print):
        game = (game or "auto").lower()
        self.mode = game if game in GAMES else "auto"
        self.log = log
        self.r = None
        self.active = None
        self.wanted = None if self.mode == "auto" else self.mode
        self.finished = False
        self.game_alive = True             # False once the game process is gone (closes the session)
        if self.mode == "auto":
            self.wanted = running_game()
            threading.Thread(target=self._watch, daemon=True).start()

    def _watch(self):
        while True:
            time.sleep(5)
            try:
                g = running_game()
            except Exception:
                continue
            if g in GAMES:
                self.wanted = g
                self.game_alive = True
            elif g is None:                # process list says no supported game is running
                self.game_alive = False

    def _pick(self):
        if self.mode != "auto":
            return self.mode
        g = self.wanted
        if g in GAMES:
            return g
        if g == "unknown":                 # can't list processes: try the mappings
            for cand in GAMES[::-1]:
                try:
                    open_reader(cand).close()
                    return cand
                except Exception:
                    pass
        raise RuntimeError("no supported game running (AMS2 or RaceRoom)")

    def read(self):
        if self.r is not None and self.mode == "auto" and self.wanted in GAMES \
                and self.wanted != self.active:
            self.log("[src] switching %s -> %s" % (GAME_LABEL[self.active],
                                                   GAME_LABEL[self.wanted]))
            self.r.close()
            self.r = None
        if self.r is None:
            game = self._pick()
            self.r = open_reader(game)
            self.active = game
            self.log("[src] reading %s shared memory" % GAME_LABEL[game])
        d = self.r.snapshot()
        if self.active == "r3e" and getattr(self.r, "warnings", None) and \
                not getattr(self, "_warned", False):
            self._warned = True
            if self.r.warnings != ["ok"]:
                for w in self.r.warnings:
                    self.log("[src] RaceRoom layout WARNING: " + w)
        return d


def start(cfg, source, realtime=True, open_browser=True):
    store = Store(cfg["data_dir"])
    app = App(store, cfg)
    rec = Recorder(source, store, cfg, on_lap=app.on_lap)
    app.recorder = rec
    httpd = serve(app, cfg["host"], cfg["port"])
    url = "http://%s:%d/" % ("localhost" if cfg["host"] in ("0.0.0.0", "127.0.0.1")
                             else cfg["host"], cfg["port"])
    print("Claugineer dashboard: %s" % url)
    print("Data folder: %s" % cfg["data_dir"])
    if open_browser and cfg.get("open_browser", True):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        rec.run_forever(realtime=realtime)
    except KeyboardInterrupt:
        print("stopping...")
    finally:
        rec.close_session()
    return httpd, app


def cmd_doctor(cfg):
    import ctypes
    from . import shm
    print("Python      :", sys.version.split()[0], sys.platform)
    print("Data folder :", cfg["data_dir"])
    print("Struct size :", ctypes.sizeof(shm.SharedMemory), "bytes (layout v%d)" % shm.EXPECTED_VERSION)
    pats = [r"C:\Program Files (x86)\Steam\steamapps\common\Automobilista 2\Support\SharedMemory\**\SharedMemory.h",
            r"?:\SteamLibrary\steamapps\common\Automobilista 2\Support\SharedMemory\**\SharedMemory.h",
            r"?:\Steam\steamapps\common\Automobilista 2\Support\SharedMemory\**\SharedMemory.h",
            r"?:\Games\Steam\steamapps\common\Automobilista 2\Support\SharedMemory\**\SharedMemory.h"]
    found = []
    if sys.platform == "win32":
        for p in pats:
            if p.startswith("?"):
                for drive in "CDEFGH":
                    found += glob.glob(drive + p[1:], recursive=True)
            else:
                found += glob.glob(p, recursive=True)
    if found:
        ok, msgs = shm.check_against_header(found[0])
        print("Game header :", found[0])
        for m in msgs:
            print("   ", m)
    else:
        print("Game header : not found (fine - set the AMS2 path manually if you want this check)")
    try:
        r = shm.Reader().open()
        d = r.snapshot()
        print("Shared mem  : OK  mVersion=%d  gameState=%d  car='%s'  track='%s'" % (
            d.mVersion, d.mGameState, bytes(d.mCarName).split(b"\0")[0].decode(),
            bytes(d.mTrackLocation).split(b"\0")[0].decode()))
        if d.mVersion and d.mVersion != shm.EXPECTED_VERSION:
            print("   WARNING: game reports version %d, Claugineer expects %d" % (
                d.mVersion, shm.EXPECTED_VERSION))
        if d.mGameState == 2:
            print("   speed %.0f km/h, rpm %.0f, tyre FL %.1f C, pressure FL raw %.2f, ride FL raw %.4f" % (
                d.mSpeed * 3.6, d.mRpm, d.mTyreTemp[0], d.mAirPressure[0], d.mRideHeight[0]))
        r.close()
    except Exception as e:
        print("Shared mem  : not available -", e)
        print("   In AMS2: Options > System > Shared Memory = Project CARS 2, and be on track.")
    cmd_doctor_r3e()


def cmd_doctor_r3e():
    import ctypes
    from . import shm_r3e as r3
    print("")
    print("--- RaceRoom ---")
    print("Game mode   :", cfg_game_note())
    print("Running     :", {True: "yes", False: "no", None: "unknown"}[r3.game_running()])
    print("Layout      : r3e.h v%d.%d, %d bytes, driver list at %d" % (
        r3.R3E_VERSION_MAJOR, r3.R3E_VERSION_MINOR, ctypes.sizeof(r3.r3e_shared),
        r3.EXPECTED_ALL_DRIVERS_OFFSET))
    try:
        rd = r3.Reader().open()
        raw = rd.raw()
        print("Shared mem  : OK  version=%d.%d  in_menus=%d  car='%s'  track='%s %s'" % (
            raw.version_major, raw.version_minor, raw.game_in_menus,
            r3._txt(raw.vehicle_info.name).decode("utf-8", "replace"),
            r3._txt(raw.track_name).decode("utf-8", "replace"),
            r3._txt(raw.layout_name).decode("utf-8", "replace")))
        probs = r3.layout_check(raw)
        if raw.version_major == 0:
            print("   game hasn't filled the block yet - load into a session and run doctor again")
        elif probs:
            for p in probs:
                print("   WARNING:", p)
        else:
            print("   Layout matches the live game (offset + driver struct size checked).")
        if raw.version_minor and raw.version_minor != r3.R3E_VERSION_MINOR:
            print("   note: game minor version %d, built for %d (minor bumps only append fields)"
                  % (raw.version_minor, r3.R3E_VERSION_MINOR))
        d = r3.translate(raw)
        if d.mGameState == 2:
            print("   speed %.0f km/h, rpm %.0f, gear %d, lap dist %.0f m / %.0f m" % (
                d.mSpeed * 3.6, d.mRpm, d.mGear, d.mParticipantInfo[0].mCurrentLapDistance,
                d.mTrackLength))
            print("   tyre FL L/C/R %.1f/%.1f/%.1f C, pressure FL %.2f bar, ride FL %.1f mm, "
                  "fuel %.1f L, steer %.2f" % (
                      d.mTyreTempLeft[0], d.mTyreTemp[0], d.mTyreTempRight[0],
                      d.mAirPressure[0] / 100.0, d.mRideHeight[0] * 1000, d.mFuelLevel *
                      d.mFuelCapacity, d.mUnfilteredSteering))
        else:
            print("   not driving right now (state %d) - sit in the car on track for live values"
                  % d.mGameState)
        rd.close()
    except Exception as e:
        print("Shared mem  : not available -", e)


def cfg_game_note():
    try:
        return load_cfg().get("game", "auto")
    except Exception:
        return "auto"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="claugineer")
    ap.add_argument("cmd", nargs="?", default="run",
                    choices=["run", "serve", "sim", "analyze", "doctor"])
    ap.add_argument("session", nargs="?", default="latest")
    ap.add_argument("--laps", type=int, default=14)
    ap.add_argument("--realtime", action="store_true")
    ap.add_argument("--remap", action="store_true", help="re-detect corners")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_cfg()
    if a.no_browser:
        cfg["open_browser"] = False

    if a.cmd == "doctor":
        return cmd_doctor(cfg)
    if a.cmd == "run":
        print("Game: %s" % cfg.get("game", "auto"))
        return start(cfg, LiveSource(cfg.get("game", "auto")))
    if a.cmd == "sim":
        from .sim import SimSource
        httpd, app = start(cfg, SimSource(laps=a.laps), realtime=a.realtime)
        print("Simulation finished. Dashboard stays up - Ctrl+C to quit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return
    if a.cmd == "serve":
        store = Store(cfg["data_dir"])
        app = App(store, cfg)
        serve(app, cfg["host"], cfg["port"])
        url = "http://localhost:%d/" % cfg["port"]
        print("Claugineer dashboard (viewer only): %s" % url)
        if cfg.get("open_browser", True):
            webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return
    if a.cmd == "analyze":
        store = Store(cfg["data_dir"])
        sid = a.session
        if sid == "latest":
            ss = store.list_sessions()
            if not ss:
                print("no sessions recorded yet")
                return
            sid = ss[0]["id"]
        engine.build(store, cfg, sid, remap=a.remap)
        print(open(store.session_path(sid, "brief.md"), encoding="utf-8").read())


if __name__ == "__main__":
    main()
