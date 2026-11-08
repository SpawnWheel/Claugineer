"""Polls the data source, splits the stream into laps and writes them to disk."""
import os
import threading
import time

from . import frames
from .shm import GAME_INGAME_PLAYING, PIT_MODE_NONE, SESSION_NAMES


class LapBuffer:
    def __init__(self, lap_no, d, idx):
        self.lap = lap_no
        self.samples = []
        self.invalid = False
        self.pit_start = int(d.mPitMode) != PIT_MODE_NONE
        self.pit_any = self.pit_start
        self.sector_marks = []          # (t, dist) where the sector changed
        self.last_sector = int(d.mParticipantInfo[idx].mCurrentSector)
        self.tyre_snaps = []
        self.fuel_start = float(d.mFuelLevel) * float(d.mFuelCapacity)
        self.started = time.time()


class Recorder:
    def __init__(self, source, store, cfg, on_lap=None, log=print):
        self.source = source
        self.store = store
        self.cfg = cfg
        self.on_lap = on_lap
        logpath = os.path.join(cfg.get("data_dir", "data"), "recorder.log")

        def _log(msg, _out=log):
            _out(msg)
            try:                                  # keep a file copy so sessions can be debugged later
                with open(logpath, "a", encoding="utf-8") as f:
                    f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(msg) + "\n")
            except Exception:
                pass
        self.log = _log
        self.hz = float(cfg.get("sample_hz", 60))
        self.sid = None
        self.meta = None
        self.key = None
        self.buf = None
        self.pending = None           # lap waiting for mLastLapTime to update
        self.prev_last_lap = None
        self.run = 0
        self.live = {"status": "waiting for the game"}
        self._stop = threading.Event()
        self._frame = 0
        self._away_since = None          # when we left the track (garage / menus / pause)
        self._new_run = False
        self._dead = 0
        self._ctx_new = None              # (key, frames seen) for a context change in progress

    # ------------------------------------------------------------------ loop
    def stop(self):
        self._stop.set()

    def run_forever(self, realtime=True):
        period = 1.0 / self.hz
        nxt = time.perf_counter()
        while not self._stop.is_set():
            try:
                d = self.source.read()
            except Exception as e:                       # source not ready yet / game gone
                if self.sid:
                    self.log("[rec] game not readable (%r) - closing session" % (e,))
                    self.close_session()
                self.live = {"status": "waiting for the game (%s)" % e}
                d = None
                time.sleep(1.0)
            if d is None:
                if getattr(self.source, "finished", False):
                    self.close_session()
                    break
                continue
            self.step(d)
            if realtime:
                nxt += period
                delay = nxt - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                else:
                    nxt = time.perf_counter()
        self.close_session()

    # ------------------------------------------------------------------ core
    def step(self, d):
        self._frame += 1
        # A session lasts from the first lap driven until the sim is closed (or track /
        # car / session type changes). Garage visits and menus only start a new run.
        if getattr(self.source, "game_alive", True) is False:
            self._dead += 1
        else:
            self._dead = 0
        if self._dead > self.hz * 12:            # game gone for ~12 s (2+ process checks)
            if self.sid:
                self.log("[rec] game closed - closing session")
                self.close_session()
            self.live = {"status": "waiting for the game"}
            return
        if int(d.mGameState) != GAME_INGAME_PLAYING:
            if self._away_since is None:
                self._away_since = time.time()
            self.live["status"] = "not on track"
            return
        if self._away_since is not None:
            away = time.time() - self._away_since
            self._away_since = None
            if away > 20 or int(d.mPitMode) != PIT_MODE_NONE:
                # back from the garage / menus: drop the partial lap, next lap = new run
                self.buf = None
                self.pending = None
                self._new_run = True

        if not frames.s(d.mTrackLocation) or not frames.s(d.mCarName) or \
                float(getattr(d, "mTrackLength", 0) or 0) <= 0:
            self.live["status"] = "loading"          # menus / loading: no track or car yet
            return
        idx = frames.player_index(d, self.cfg.get("player_name", ""))
        ctx_key = (frames.s(d.mTrackLocation), frames.s(d.mTrackVariation),
                   frames.s(d.mCarName), int(d.mSessionState))
        if self.key is None:
            self.open_session(d)
            self.key = ctx_key
        elif ctx_key != self.key:
            # only split when the new track/car/session type is stable for 3 s
            # (ignores flickering values while RaceRoom loads in/out of the garage)
            if self._ctx_new and self._ctx_new[0] == ctx_key:
                self._ctx_new[1] += 1
            else:
                self._ctx_new = [ctx_key, 1]
            if self._ctx_new[1] < self.hz * 3:
                return
            self.log("[rec] context changed %r -> %r" % (self.key, ctx_key))
            self._ctx_new = None
            self.close_session()
            self.open_session(d)
            self.key = ctx_key
        else:
            self._ctx_new = None

        p = d.mParticipantInfo[idx]
        lap_no = int(p.mCurrentLap)

        # finish a lap that is waiting for its official time
        if self.pending:
            self._try_finish_pending(d)

        if self.buf is None:
            self.buf = LapBuffer(lap_no, d, idx)
            if self._new_run:
                self.buf.pit_start = self.buf.pit_any = True
                self._new_run = False
        elif lap_no != self.buf.lap:
            if lap_no == self.buf.lap + 1 and self.buf.samples:
                self.pending = {"buf": self.buf, "frames": 0, "ctx": frames.context(d),
                                "before": self.prev_last_lap}
                self._try_finish_pending(d)
            # restart / jump: drop the partial lap
            self.buf = LapBuffer(lap_no, d, idx)

        b = self.buf
        if self.pending is None:
            self.prev_last_lap = float(d.mLastLapTime)
        if d.mLapInvalidated:
            b.invalid = True
        if int(d.mPitMode) != PIT_MODE_NONE:
            b.pit_any = True
        sec = int(p.mCurrentSector)
        if sec != b.last_sector:
            b.sector_marks.append((float(d.mCurrentTime), float(p.mCurrentLapDistance)))
            b.last_sector = sec
        if float(d.mCurrentTime) >= 0:
            b.samples.append(frames.sample(d, idx))
        if self._frame % 6 == 0:
            b.tyre_snaps.append(frames.tyre_snapshot(d, self.cfg.get("pressure_unit", "bar100")))
        if self._frame % 3 == 0:
            self._update_live(d, idx)

    def _try_finish_pending(self, d):
        pend = self.pending
        pend["frames"] += 1
        last = float(d.mLastLapTime)
        buf = pend["buf"]
        sample_time = buf.samples[-1][0] if buf.samples else 0
        got = last > 0 and last != pend["before"]
        if got or pend["frames"] > int(self.hz * 1.5):
            lap_time = last if got else (sample_time if sample_time > 0 else None)
            self.pending = None
            self._save_lap(buf, lap_time, pend["ctx"], official=got)

    # ------------------------------------------------------------------ session
    def open_session(self, d):
        ctx = frames.context(d)
        stype = SESSION_NAMES.get(ctx["session_state"], "session")
        self.sid = self.store.new_session_dir(ctx, stype)
        self.meta = {
            "id": self.sid, "game": ctx["game"],
            "track": ctx["track"], "variation": ctx["variation"],
            "car": ctx["car"], "car_class": ctx["car_class"],
            "track_length": ctx["track_length"], "session_type": stype,
            "started": time.strftime("%Y-%m-%d %H:%M:%S"),
            "conditions_start": {k: ctx[k] for k in ("air_c", "track_c", "rain")},
            "max_rpm": ctx["max_rpm"], "num_gears": ctx["num_gears"],
            "sample_cols": frames.SAMPLE_COLS, "laps": [],
        }
        self.store.save_session(self.sid, self.meta)
        self.run = 0
        self.buf = None
        self.pending = None
        self.log("[rec] new session %s" % self.sid)

    def close_session(self):
        if self.pending:
            p = self.pending
            self.pending = None
            st = p["buf"].samples[-1][0] if p["buf"].samples else None
            self._save_lap(p["buf"], st, p["ctx"], official=False)
        if self.sid and self.meta is not None:
            self.store.save_session(self.sid, self.meta)
            self.log("[rec] closed session %s (%d laps)" % (self.sid, len(self.meta["laps"])))
        self.sid = None
        self.meta = None
        self.key = None
        self.buf = None

    def _save_lap(self, buf, lap_time, ctx, official):
        if not buf.samples or lap_time is None:
            return
        L = self.meta.get("track_length") or 0
        dists = [r[1] for r in buf.samples]
        coverage = (max(dists) - min(dists)) / L if L else 1
        complete = coverage > 0.9 and min(dists) < 0.1 * L + 50
        if buf.pit_start or self.run == 0:
            self.run += 1
        sectors, sector_d = [], []
        prev_t = 0.0
        for (t, dist) in buf.sector_marks[:2]:
            if 0 < t < lap_time:
                sectors.append(round(t - prev_t, 3))
                sector_d.append(round(dist, 1))
                prev_t = t
        if len(sectors) == 2:
            sectors.append(round(lap_time - prev_t, 3))
        else:
            sectors = []
        done = [l["lap"] for l in self.meta["laps"]]
        if done and buf.lap <= max(done):        # game restarted its lap count: keep files unique
            buf.lap = max(done) + 1
        tyres = summarise_tyres(buf.tyre_snaps)
        fuel_end = ctx["fuel_l"]
        entry = {
            "lap": buf.lap, "time": round(lap_time, 3), "official_time": official,
            "valid": (not buf.invalid) and complete, "invalid_flag": buf.invalid,
            "complete": complete, "pit": buf.pit_any, "out_lap": buf.pit_start,
            "run": self.run, "sectors": sectors, "sector_dist": sector_d,
            "fuel_used": round(buf.fuel_start - fuel_end, 2) if buf.fuel_start > fuel_end else None,
            "fuel_left": fuel_end, "tyres": tyres,
            "brake_bias": ctx["brake_bias"], "brake_bias_basis": "front",
            "abs_setting": ctx["abs_setting"],
            "tc_setting": ctx["tc_setting"], "air_c": ctx["air_c"],
            "track_c": ctx["track_c"], "rain": ctx["rain"], "compound": ctx["compound"],
            "recorded": time.strftime("%H:%M:%S"),
        }
        entry["file"] = self.store.save_lap(self.sid, buf.lap, buf.samples)
        self.meta["laps"].append(entry)
        self.store.save_session(self.sid, self.meta)
        self.log("[rec] lap %d  %s  %s%s" % (buf.lap, fmt_time(lap_time),
                                            "valid" if entry["valid"] else "INVALID",
                                            " (pit)" if entry["pit"] else ""))
        if self.on_lap:
            try:
                self.on_lap(self.sid)
            except Exception as e:  # analysis must never stop recording
                self.log("[analysis] error: %r" % e)

    # ------------------------------------------------------------------ live
    def _update_live(self, d, idx):
        p = d.mParticipantInfo[idx]
        self.live = {
            "status": "recording", "session": self.sid, "game": getattr(d, "_game", "ams2"),
            "track": frames.s(d.mTrackLocation), "car": frames.s(d.mCarName),
            "lap": int(p.mCurrentLap), "dist": round(float(p.mCurrentLapDistance), 1),
            "cur": round(float(d.mCurrentTime), 3), "last": round(float(d.mLastLapTime), 3),
            "best": round(float(d.mBestLapTime), 3),
            "speed": round(float(d.mSpeed) * 3.6, 1), "gear": int(d.mGear),
            "thr": round(float(d.mUnfilteredThrottle), 2), "brk": round(float(d.mUnfilteredBrake), 2),
            "invalid": bool(d.mLapInvalidated),
            "tyres": frames.tyre_snapshot(d, self.cfg.get("pressure_unit", "bar100")),
            "fuel_l": round(float(d.mFuelLevel) * float(d.mFuelCapacity), 2),
            "brake_bias": frames.front_bias(d),
        }


def summarise_tyres(snaps):
    """Average tyre state over the lap plus end-of-lap values."""
    if not snaps:
        return {}
    out = {}
    for w in frames.WHEELS:
        rows = [s[w] for s in snaps]
        n = len(rows)
        tail = rows[-max(1, n // 4):]
        avg = lambda k, rr=rows: round(sum(r[k] for r in rr) / len(rr), 2)
        out[w] = {
            "inner": avg("inner"), "middle": avg("middle"), "outer": avg("outer"),
            "carcass": avg("carcass"), "pressure_avg": avg("pressure"),
            "pressure_end": round(sum(r["pressure"] for r in tail) / len(tail), 3),
            "pressure_max": round(max(r["pressure"] for r in rows), 3),
            "wear_end": rows[-1]["wear"],
            "brake_avg": avg("brake"), "brake_max": round(max(r["brake"] for r in rows), 1),
            "ride_min_mm": round(min(r["ride_mm"] for r in rows), 1),
        }
    return out


def fmt_time(t):
    if t is None or t <= 0:
        return "-"
    m = int(t // 60)
    return "%d:%06.3f" % (m, t - 60 * m)
