"""Synthetic AMS2 data source for testing and demo (no game needed).

Produces objects with the same field names as the shared-memory struct. A fictional
2.6 km circuit with 8 corners; the 'driver' has corner-specific habits and learns
(or gets worse) over the session so trends, outliers, lockups and coasting all show up.
"""
import math
import random
from types import SimpleNamespace

G = 9.81

# (length m, curvature 1/m)  curvature sign: + = right, - = left
TRACK = [
    (420, 0), (120, 1 / 22), (160, 0), (90, -1 / 60), (60, 0), (110, 1 / 140),
    (300, 0), (80, -1 / 30), (140, 0), (70, 1 / 45), (60, -1 / 45), (220, 0),
    (130, 1 / 90), (180, 0), (95, -1 / 25), (260, 0), (100, 1 / 70), (110, 0),
]
CORNER_HABITS = {
    # index of curved piece -> (min-speed factor, brake-decel factor, coast m, throttle delay m)
    1: (0.97, 0.92, 12, 10), 3: (0.99, 1.0, 0, 0), 5: (1.0, 1.0, 0, 0),
    7: (0.95, 0.85, 18, 18), 9: (0.98, 0.95, 5, 6), 10: (0.98, 1.0, 0, 8),
    12: (0.99, 1.0, 0, 0), 14: (0.96, 0.9, 10, 14), 16: (0.99, 1.0, 4, 4),
}


def build_track(step=1.0):
    k = []
    for length, curv in TRACK:
        k.extend([curv] * int(length / step))
    # smooth curvature (clothoid-ish transitions) over 30 m
    w = int(30 / step)
    sm = []
    n = len(k)
    for i in range(n):
        acc = 0.0
        for j in range(-w, w + 1):
            acc += k[(i + j) % n]
        sm.append(acc / (2 * w + 1))
    piece_of = []
    for pi, (length, curv) in enumerate(TRACK):
        piece_of.extend([pi] * int(length / step))
    # x/z coordinates
    x = z = 0.0
    hdg = 0.0
    xs, zs = [], []
    for c in sm:
        xs.append(x)
        zs.append(z)
        hdg += c * step
        x += math.sin(hdg) * step
        z += math.cos(hdg) * step
    return sm, piece_of, xs, zs


class SimSource:
    def __init__(self, laps=14, seed=7, hz=60, pit_after=7):
        self.rng = random.Random(seed)
        self.k, self.piece, self.xs, self.zs = build_track()
        self.L = float(len(self.k))
        self.hz = hz
        self.total_laps = laps
        self.pit_after = pit_after
        self.finished = False
        self.lap = 1
        self.s = 0.0
        self.t_lap = 0.0
        self.last_lap = -1.0
        self.best = -1.0
        self.fuel = 40.0
        self.temps = [30.0] * 4
        self.wear = [0.0] * 4
        self.brake_t = [150.0] * 4
        self.in_pit = True          # first lap is an out-lap
        n = len(self.k)
        self._prev = [self._prev_corner_slow(i) for i in range(n)]
        self._next = [self._next_corner_slow(i) for i in range(n)]
        self._after = [self._dist_after_apex_slow(i) for i in range(n)]
        self._new_lap_profile()

    def _prev_corner(self, i):
        return self._prev[i % len(self.k)]

    def _next_corner(self, i):
        return self._next[i % len(self.k)]

    def _dist_after_apex(self, i):
        return self._after[i % len(self.k)]

    # ---------------------------------------------------------------- driver model
    def _new_lap_profile(self):
        rng = self.rng
        n = len(self.k)
        mu, vtop, amax, bmax = 1.45, 72.0, 6.5, 13.0
        lap = self.lap
        vmax = []
        self.events = {"lock": set(), "spin": set(), "lift": set()}
        mods = {}
        for pi, (mf, bf, coast, delay) in CORNER_HABITS.items():
            learn = min(lap, 10) * 0.004 if pi in (1, 14) else 0.0     # improving corners
            fade = max(0, lap - 8) * 0.006 if pi == 7 else 0.0           # losing corner
            jitter = rng.gauss(0, 0.012)
            if rng.random() < 0.07:                                       # occasional big mistake
                jitter -= 0.05
            if rng.random() < 0.05:                                       # lucky lap
                jitter += 0.02
            mods[pi] = (mf + learn - fade + jitter, bf * (1 + rng.gauss(0, 0.04)),
                        max(0, coast * (1 - min(lap, 10) * 0.05 * (pi == 1)) + rng.gauss(0, 3)),
                        max(0, delay + rng.gauss(0, 4)))
            if rng.random() < (0.25 if pi == 7 else 0.08):
                self.events["lock"].add(pi)
            if rng.random() < (0.3 if pi == 14 else 0.06):
                self.events["spin"].add(pi)
        if rng.random() < 0.5:
            self.events["lift"].add(12)
        self.mods = mods
        for i in range(n):
            c = abs(self.k[i])
            v = math.sqrt(mu * G / c) if c > 1e-5 else vtop
            pi = self.piece[i]
            if pi in mods:
                v *= mods[pi][0]
            vmax.append(min(v, vtop))
        # forward pass (traction), backward pass (braking) - two loops for wrap-around
        v = vmax[:]
        for _ in range(2):
            for i in range(n):
                p = v[i - 1]
                pi = self.piece[i]
                delay = mods.get(self._prev_corner(i), (0, 0, 0, 0))[3]
                a = amax * (1 - p / vtop)
                if self._dist_after_apex(i) < delay:
                    a *= 0.25
                v[i] = min(v[i], math.sqrt(max(p * p + 2 * a, 0.1)))
            for i in range(n - 1, -1, -1):
                nx = v[(i + 1) % n]
                pi = self._next_corner(i)
                bf = mods.get(pi, (1, 1, 0, 0))[1]
                v[i] = min(v[i], math.sqrt(nx * nx + 2 * bmax * bf))
        self.v = v
        self.vmax = vmax
        self.lap_invalid = rng.random() < 0.08

    def _prev_corner_slow(self, i):
        j = i
        for _ in range(400):
            j -= 1
            if abs(self.k[j % len(self.k)]) > 0.004:
                return self.piece[j % len(self.k)]
        return None

    def _next_corner_slow(self, i):
        n = len(self.k)
        for j in range(i, i + 400):
            if abs(self.k[j % n]) > 0.004:
                return self.piece[j % n]
        return None

    def _dist_after_apex_slow(self, i):
        n = len(self.k)
        for back in range(0, 300):
            if abs(self.k[(i - back) % n]) > 0.004:
                return back
        return 999

    # ---------------------------------------------------------------- frame output
    def read(self):
        if self.finished:
            return None
        dt = 1.0 / self.hz
        n = len(self.k)
        i = int(self.s) % n
        v = self.v[i]
        nv = self.v[(i + 3) % n]
        accel = (nv * nv - v * v) / 6.0        # m/s^2 along track
        curv = self.k[i]
        pi = self.piece[i]
        nxt = self._next_corner(i)
        coast = self.mods.get(nxt, (0, 0, 0, 0))[2]
        thr = brk = 0.0
        if accel > 0.3:
            thr = 1.0 if accel > 1.0 else 0.55
        elif accel < -1.0:
            brk = min(1.0, -accel / 13.0)
        else:
            thr = 0.35 if abs(curv) > 0.004 else 0.9
        # coasting gap before turn-in: release the brake early
        if brk > 0 and abs(curv) < 0.004 and coast > 2 and \
                abs(self.k[(i + int(coast) + 1) % n]) > 0.004:
            brk = 0.0
        if 12 in self.events["lift"] and pi == 12 and 20 < self._dist_after_apex(i) < 60:
            thr = 0.55
        steer = max(-1, min(1, curv * 18 * (1 + 0.15 * abs(v * v * curv) / G)))
        latg = v * v * curv / G
        yaw = v * curv
        vx = 0.0
        rps = [v / 0.31, v / 0.31, v / 0.32, v / 0.32]
        abs_on = 0
        if pi is not None and nxt in self.events["lock"] and brk > 0.75:
            rps[0] *= 0.55
            abs_on = 1 if self.rng.random() < 0.3 else 0
        if self._prev_corner(i) in self.events["spin"] and thr > 0.9 and \
                self._dist_after_apex(i) < 60:
            rps[2] *= 1.22
            rps[3] *= 1.12
            yaw *= 1.25
            vx = 0.8
        # tyres warm up through the session
        for w in range(4):
            target = 75 + (6 if w < 2 else 0) + 12 * abs(latg) / 1.4
            self.temps[w] += (target - self.temps[w]) * 0.0006
            self.wear[w] = min(1.0, self.wear[w] + 0.0000015)
            self.brake_t[w] += (180 + 520 * brk - self.brake_t[w]) * 0.01
        self.fuel -= 0.00042 * thr + 0.00004

        gear = 1 + min(5, int(v / 13))
        d = self._struct(v, thr, brk, steer, latg, accel / G, yaw, vx, rps, gear, abs_on, i)

        # advance
        self.s += v * dt
        self.t_lap += dt
        if self.in_pit and self.s > 250:
            self.in_pit = False
        if self.s >= self.L:
            self.s -= self.L
            self.last_lap = round(self.t_lap, 3)
            if not self.lap_invalid and (self.best < 0 or self.last_lap < self.best):
                self.best = self.last_lap
            self.t_lap = self.s / max(v, 1)
            self.lap += 1
            if self.lap > self.total_laps:
                self.finished = True
            if self.lap - 1 == self.pit_after:
                self.in_pit = True
                for w in range(4):
                    self.temps[w] = 45
            self._new_lap_profile()
        return d

    def _struct(self, v, thr, brk, steer, latg, longg, yaw, vx, rps, gear, abs_on, i):
        sector = 0 if self.s < self.L / 3 else (1 if self.s < 2 * self.L / 3 else 2)
        part = SimpleNamespace(
            mIsActive=True, mName=b"Driver", mWorldPosition=[self.xs[i], 0, self.zs[i]],
            mCurrentLapDistance=self.s, mRacePosition=1, mLapsCompleted=self.lap - 1,
            mCurrentLap=self.lap, mCurrentSector=sector)
        temps = self.temps
        pressure = [1.70 + (t - 20) * 0.0055 for t in temps]
        return SimpleNamespace(
            mGameState=2, mSessionState=1, mViewedParticipantIndex=0, mNumParticipants=1,
            mParticipantInfo=[part], mTrackLocation=b"Simulated Park", mTrackVariation=b"GP",
            mCarName=b"Sim GT3", mCarClassName=b"GT3", mTrackLength=self.L,
            mCurrentTime=self.t_lap, mLastLapTime=self.last_lap, mBestLapTime=self.best,
            mLapInvalidated=self.lap_invalid and self.s > 900,
            mPitMode=2 if self.in_pit else 0,
            mUnfilteredThrottle=thr, mUnfilteredBrake=brk, mUnfilteredSteering=steer,
            mUnfilteredClutch=0.0, mSpeed=v, mGear=gear, mRpm=4000 + (v % 13) * 300,
            mMaxRPM=8000, mNumGears=6, mAntiLockActive=bool(abs_on),
            mLocalAcceleration=[latg * G, 0, longg * G], mAngularVelocity=[0, yaw, 0],
            mLocalVelocity=[vx, 0, v], mTyreRPS=rps,
            mRideHeight=[0.055 - 0.01 * brk, 0.055 - 0.01 * brk, 0.07, 0.07],
            mSuspensionVelocity=[0, 0, 0, 0], mTyreTemp=list(temps),
            mTerrain=[0, 0, 0, 0],
            mTyreTempLeft=[temps[0] - 4, temps[1] + 3, temps[2] - 3, temps[3] + 2],
            mTyreTempRight=[temps[0] + 4, temps[1] - 3, temps[2] + 3, temps[3] - 2],
            mTyreCarcassTemp=[t + 273.15 + 5 for t in temps],
            mAirPressure=[p * 100 for p in pressure], mTyreWear=list(self.wear),
            mBrakeTempCelsius=list(self.brake_t),
            mFuelLevel=self.fuel / 100.0, mFuelCapacity=100.0,
            mAmbientTemperature=22.0, mTrackTemperature=31.0, mRainDensity=0.0,
            mBrakeBias=0.42,  # rear share like AMS2 -> 58% front
            mAntiLockSetting=4, mTractionControlSetting=3,
            mTyreCompound=[b"Slick Medium"] * 4)
