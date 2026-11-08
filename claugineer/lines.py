"""Driving-line analysis from the car's world position (x, z).

The games don't publish track edges, so every line is measured against the line of your
best valid lap at this track in this car:
  * lateral offset (m) of a lap from the best lap's line, + = LEFT of it in the direction
    of travel (for the charts), and inside-positive per corner (for the metrics);
  * the "used road" envelope = the widest you have been on either side over all laps,
    a stand-in for the track edges;
  * per corner: turn-in point, geometric apex (closest you get to the inside edge of the
    envelope), minimum-speed point, and where you are across the road at turn-in / apex /
    exit compared with the best lap.
"""
import math

from . import analysis as an

STEP = 2.0
_CACHE = {}           # (sid, lap, ref_sid, ref_lap) -> offsets (left-positive) on the grid
_GRID = {}            # (sid, lap) -> (gx, gz, gspd, dmax)


def grid(n_len, step=STEP):
    return [round(i * step, 1) for i in range(int(n_len // step) + 1)]


def _lap_grid(store, sid, n, xs):
    key = (sid, n, len(xs))
    if key in _GRID:
        return _GRID[key]
    meta = store.load_session(sid)
    e = next((x for x in meta["laps"] if x["lap"] == n), None)
    lp = an.Lap(e, store.load_lap(sid, n), meta["track_length"])
    if len(lp.d) < 100:
        raise ValueError("short lap")
    dmax = lp.d[-1]
    gx = [lp.val("x", x) if x <= dmax + 1 else None for x in xs]
    gz = [lp.val("z", x) if x <= dmax + 1 else None for x in xs]
    gs = [lp.val("spd", x) if x <= dmax + 1 else None for x in xs]
    gst = [lp.val("str", x) if x <= dmax + 1 else None for x in xs]
    _GRID[key] = (gx, gz, gs, dmax, gst)
    return _GRID[key]


class RefLine:
    def __init__(self, gx, gz):
        self.x, self.z = gx, gz
        n = len(gx)
        self.tx, self.tz = [0.0] * n, [0.0] * n
        for i in range(n):
            a, b = max(0, i - 2), min(n - 1, i + 2)
            while a < i and gx[a] is None:
                a += 1
            while b > i and gx[b] is None:
                b -= 1
            if gx[a] is None or gx[b] is None or a == b:
                continue
            dx, dz = gx[b] - gx[a], gz[b] - gz[a]
            L = math.hypot(dx, dz) or 1.0
            self.tx[i], self.tz[i] = dx / L, dz / L
        # turn direction (+1 / -1) from the change of heading over +-20 m
        self.turn = [0] * n
        for i in range(n):
            a, b = max(0, i - 10), min(n - 1, i + 10)
            c = self.tx[a] * self.tz[b] - self.tz[a] * self.tx[b]
            self.turn[i] = 1 if c > 0.02 else (-1 if c < -0.02 else 0)

    def offset(self, px, pz, k):
        """Signed distance of point p from the line, searching near grid index k.
        + = left of the line in the direction of travel (same sign convention as `turn`)."""
        n = len(self.x)
        best, bi = None, None
        for i in range(max(0, k - 25), min(n, k + 26)):
            if self.x[i] is None:
                continue
            d = (px - self.x[i]) ** 2 + (pz - self.z[i]) ** 2
            if best is None or d < best:
                best, bi = d, i
        if bi is None:
            return None, None
        cr = self.tx[bi] * (pz - self.z[bi]) - self.tz[bi] * (px - self.x[bi])
        return cr, bi


def best_lap(store, sid):
    """(sid, lap, time) of the best valid complete lap over all sessions of this combo."""
    meta = store.load_session(sid)
    best = None
    for s in store.sessions_for_combo(meta["track"], meta["variation"], meta["car"]):
        m = store.load_session(s) or {}
        for e in m.get("laps", []):
            if e.get("valid") and not e.get("pit") and e.get("complete", True) and e.get("time"):
                if best is None or e["time"] < best[2]:
                    best = (s, e["lap"], e["time"])
    return best


def offsets(store, ref, lap, xs):
    """Left-positive offsets of `lap` (sid, n) from the line of `ref` (sid, n)."""
    key = (lap[0], lap[1], ref[0], ref[1], len(xs))
    if key in _CACHE:
        return _CACHE[key]
    rx, rz = _lap_grid(store, ref[0], ref[1], xs)[:2]
    R = RefLine(rx, rz)
    gx, gz = _lap_grid(store, lap[0], lap[1], xs)[:2]
    out = []
    for i in range(len(xs)):          # lap distance is projected on the track, so same i = same place
        if gx[i] is None:
            out.append(None)
            continue
        o, _ = R.offset(gx[i], gz[i], i)
        out.append(None if o is None or abs(o) > 25 else round(o, 2))
    _CACHE[key] = out
    return out


def combo_lines(store, sid, corners, corner_metrics_by_lap, valid_keys=None):
    """Line metrics for every complete lap of the combo + the used-road envelope.

    corner_metrics_by_lap: {(sid, lap): {cid: metrics}} from the analysis (for turn-in).
    Returns {"ref": (sid, lap), "env_left": [...], "env_right": [...], "laps": {(sid, lap): {cid: {...}}}}
    """
    ref = best_lap(store, sid)
    if not ref:
        return None
    ref = (ref[0], ref[1])
    meta = store.load_session(sid)
    xs = grid(meta["track_length"])
    rx, rz, rs = _lap_grid(store, ref[0], ref[1], xs)[:3]
    R = RefLine(rx, rz)
    offs = {}
    speeds = {}
    for key in corner_metrics_by_lap:
        try:
            offs[key] = offsets(store, ref, key, xs)
            speeds[key] = _lap_grid(store, key[0], key[1], xs)[2]
        except Exception:
            continue
    n = len(xs)
    env_l = [None] * n
    env_r = [None] * n
    for key, o in offs.items():
        if valid_keys is not None and key not in valid_keys:
            continue                  # the used-road envelope only from valid laps (track limits)
        for i, v in enumerate(o):
            if v is None:
                continue
            if env_l[i] is None or v > env_l[i]:
                env_l[i] = v
            if env_r[i] is None or v < env_r[i]:
                env_r[i] = v
    idx = lambda d: max(0, min(n - 1, int(round(d / STEP))))

    def turn_at(a):
        s = sum(R.turn[max(0, idx(a) - 10):idx(a) + 11])
        return 1 if s > 0 else -1

    grids = {}
    for key in offs:
        grids[key] = _lap_grid(store, key[0], key[1], xs)

    def heading_change(a):
        i0, i1 = idx(a - 40), idx(a + 40)
        c = R.tx[i0] * R.tx[i1] + R.tz[i0] * R.tz[i1]
        return math.degrees(math.acos(max(-1.0, min(1.0, c))))

    def centre(a):
        """Centre of the circle through the best lap's line at apex-30, apex, apex+30."""
        p = [(rx[idx(d)], rz[idx(d)]) for d in (a - 30, a, a + 30)]
        if any(v[0] is None for v in p):
            return None
        (x1, y1), (x2, y2), (x3, y3) = p
        dd = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
        if abs(dd) < 1e-6:
            return None
        ux = ((x1 * x1 + y1 * y1) * (y2 - y3) + (x2 * x2 + y2 * y2) * (y3 - y1) + (x3 * x3 + y3 * y3) * (y1 - y2)) / dd
        uz = ((x1 * x1 + y1 * y1) * (x3 - x2) + (x2 * x2 + y2 * y2) * (x1 - x3) + (x3 * x3 + y3 * y3) * (x2 - x1)) / dd
        return ux, uz

    res = {}
    cinfo = {}
    for c in corners:
        A = c["apex_m"]
        cinfo[c["id"]] = {"A": A, "sgn": turn_at(A), "hc": heading_change(A), "C": centre(A),
                          "w": (idx(max(c["start_m"], A - 120)), idx(min(c["end_m"], A + 100)))}
    for key, o in offs.items():
        gx, gz, sp, _, st = grids[key]
        out = {}
        for c in corners:
            ci = cinfo[c["id"]]
            A, sgn, (a0, a1), C = ci["A"], ci["sgn"], ci["w"], ci["C"]
            # geometric apex = point of the line closest to the centre of the corner
            gd, gi = None, None
            if C and ci["hc"] > 35:
                ds = [(i, math.hypot(gx[i] - C[0], gz[i] - C[1])) for i in range(a0, a1 + 1)
                      if gx[i] is not None]
                if ds:
                    gd = min(v for _, v in ds)
                    # the apex of an arc is flat: take the middle of the part within 0.3 m
                    near = [i for i, v in ds if v <= gd + 0.3]
                    gi = int(round(sum(near) / len(near)))
            # minimum-speed point
            ms, mi = None, None
            for i in range(a0, a1 + 1):
                if sp[i] is not None and (ms is None or sp[i] < ms):
                    ms, mi = sp[i], i
            # turn-in = first point before the apex where steering (towards the corner)
            # reaches 35% of this lap's peak steering in the corner
            ti = None
            vals = [(i, st[i]) for i in range(a0, min(a1, idx(A + 20)) + 1) if st[i] is not None]
            if vals and ci["hc"] > 35:
                peak_i, peak = max(vals, key=lambda v: abs(v[1]))
                if abs(peak) > 0.05:
                    for i, v in vals:
                        if i > peak_i:
                            break
                        if v * peak > 0 and abs(v) >= 0.35 * abs(peak):
                            ti = i
                            break
            pin = lambda d: (o[idx(d)] * sgn) if o[idx(d)] is not None else None
            out[c["id"]] = {
                "dir": "L" if sgn > 0 else "R", "angle": round(ci["hc"]),
                "turn_in_m": round(xs[ti] - A) if ti is not None else None,
                "apex_geo_m": round(xs[gi] - A) if gi is not None else None,
                "apex_r": round(gd, 2) if gd is not None else None,
                "min_speed_at_m": round(xs[mi] - A) if mi is not None else None,
                "off_apex": _r(pin(A)),
                "off_exit": _r(pin(A + 80)),
            }
        res[key] = out
    # how far from the tightest apex you've driven (valid laps) -> missed apex
    for c in corners:
        rs_ = [m[c["id"]]["apex_r"] for k, m in res.items()
               if m[c["id"]]["apex_r"] is not None and (valid_keys is None or k in valid_keys)]
        rs_.sort()
        tight = rs_[int(len(rs_) * 0.2)] if rs_ else None      # 20th percentile, not one outlier
        for m in res.values():
            r = m[c["id"]]["apex_r"]
            m[c["id"]]["apex_gap_m"] = round(r - tight, 2) if (r is not None and tight is not None) else None
    return {"ref": ref, "dist": xs, "env_left": env_l, "env_right": env_r, "laps": res}


def _r(v):
    return None if v is None else round(v, 2)


def line_flags(m, ref):
    """Line habits vs the best lap. m/ref = line metrics of one corner."""
    f = []
    if not m or not ref:
        return f
    if m.get("apex_geo_m") is not None and ref.get("apex_geo_m") is not None and \
            m["apex_geo_m"] < ref["apex_geo_m"] - 20:
        f.append("early_apex")
    if m.get("apex_geo_m") is not None and ref.get("apex_geo_m") is not None and \
            m["apex_geo_m"] > ref["apex_geo_m"] + 20:
        f.append("late_apex")
    if m.get("turn_in_m") is not None and ref.get("turn_in_m") is not None and \
            m["turn_in_m"] < ref["turn_in_m"] - 10:
        f.append("early_turn_in")
    if m.get("apex_gap_m") is not None and m["apex_gap_m"] > 1.5:
        f.append("missed_apex")
    return f


def envelope(store, sid):
    """Best-lap reference + used-road envelope (valid laps) on the 2 m grid, for the charts."""
    ref = best_lap(store, sid)
    if not ref:
        return None
    ref = (ref[0], ref[1])
    meta = store.load_session(sid)
    xs = grid(meta["track_length"])
    n = len(xs)
    env_l, env_r = [None] * n, [None] * n
    for s in store.sessions_for_combo(meta["track"], meta["variation"], meta["car"]):
        m = store.load_session(s) or {}
        for e in m.get("laps", []):
            if not (e.get("valid") and not e.get("pit") and e.get("complete", True)):
                continue
            try:
                o = offsets(store, ref, (s, e["lap"]), xs)
            except Exception:
                continue
            for i, v in enumerate(o):
                if v is None:
                    continue
                if env_l[i] is None or v > env_l[i]:
                    env_l[i] = v
                if env_r[i] is None or v < env_r[i]:
                    env_r[i] = v
    return {"ref": ref, "env_left": env_l, "env_right": env_r}


def reference_metrics(per_lap, fastest_keys):
    """Median line metrics of your fastest laps (a steadier target than one lap)."""
    out = {}
    rows = [per_lap[k] for k in fastest_keys if k in per_lap]
    if not rows:
        return out
    for cid in rows[0]:
        out[cid] = {}
        for f in ("turn_in_m", "apex_geo_m", "min_speed_at_m", "off_apex", "off_exit"):
            v = sorted(r[cid][f] for r in rows if r.get(cid) and r[cid].get(f) is not None)
            out[cid][f] = v[len(v) // 2] if v else None
    return out
