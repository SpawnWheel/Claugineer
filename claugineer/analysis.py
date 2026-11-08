"""Lap analysis: corners, driving technique, trends, consistency.

Pure Python (no numpy) so the app installs with nothing but Python itself.
All distances are metres from the start/finish line; 'rel' values are metres
relative to the corner apex (negative = before the apex).
"""
import bisect
import math
import statistics as st

from .storage import read_json, write_json

GRID = 5.0          # metres, for delta / trace comparison


# =============================================================== small helpers
def median(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def mad(xs):
    m = median(xs)
    if m is None:
        return None
    return median([abs(x - m) for x in xs])


def pct(xs, q):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def theil_sen(ys):
    """Robust slope per step, ignoring None."""
    pts = [(i, y) for i, y in enumerate(ys) if y is not None]
    slopes = []
    for a in range(len(pts)):
        for b in range(a + 1, len(pts)):
            dx = pts[b][0] - pts[a][0]
            slopes.append((pts[b][1] - pts[a][1]) / dx)
    return median(slopes) if slopes else None


def rnd(x, n=3):
    return None if x is None else round(x, n)


def interp(xs, ys, x):
    i = bisect.bisect_left(xs, x)
    if i <= 0:
        return ys[0]
    if i >= len(xs):
        return ys[-1]
    x0, x1 = xs[i - 1], xs[i]
    if x1 == x0:
        return ys[i]
    return ys[i - 1] + (ys[i] - ys[i - 1]) * (x - x0) / (x1 - x0)


def smooth(v, w):
    out = []
    n = len(v)
    for i in range(n):
        a, b = max(0, i - w), min(n, i + w + 1)
        out.append(sum(v[a:b]) / (b - a))
    return out


# =============================================================== lap object
class Lap:
    def __init__(self, entry, cols, L):
        self.n = entry["lap"]
        self.entry = entry
        self.time = entry["time"]
        self.L = L
        d = cols["d"]
        keep = []
        last = -1.0
        for i, x in enumerate(d):
            if i < 60 and x > 0.5 * L:          # still reading previous lap's distance
                continue
            if x >= last and x <= L + 30:
                keep.append(i)
                last = x
        self.c = {k: [v[i] for i in keep] for k, v in cols.items()}
        self.d = self.c["d"]
        self.t = self.c["t"]
        # time/distance for interpolation incl. start and finish anchors
        self._td = [0.0] + self.d + [L]
        self._tt = [0.0] + self.t + [self.time]
        for i in range(1, len(self._tt)):          # enforce monotonic time
            if self._tt[i] < self._tt[i - 1]:
                self._tt[i] = self._tt[i - 1]

    def time_at(self, dist):
        return interp(self._td, self._tt, dist)

    def idx(self, dist):
        return min(len(self.d) - 1, bisect.bisect_left(self.d, dist))

    def val(self, ch, dist):
        return interp(self.d, self.c[ch], dist)

    def on_grid(self, ch, step=GRID):
        out = []
        x = 0.0
        while x <= self.L:
            out.append(round(self.val(ch, x), 3))
            x += step
        return out


# =============================================================== calibration
def calibrate(laps):
    """Session-wide constants derived from the data itself (no assumptions about units)."""
    radius = [None] * 4
    for w in range(4):
        ratios = []
        for lp in laps:
            c = lp.c
            for i in range(0, len(lp.d), 3):
                v = c["spd"][i] / 3.6
                r = abs(c["rps%d" % w][i])
                if v > 15 and r > 1 and c["brk"][i] < 0.02 and c["thr"][i] < 0.6 \
                        and abs(c["latg"][i]) < 0.3 and abs(c["long"][i]) < 0.15:
                    ratios.append(v / r)
        radius[w] = median(ratios)
    prod_y, prod_s = [], []
    for lp in laps:
        c = lp.c
        for i in range(0, len(lp.d), 3):
            if abs(c["latg"][i]) > 0.4:
                prod_y.append(c["yaw"][i] * c["latg"][i])
                prod_s.append(c["str"][i] * c["latg"][i])
    s_yaw = 1 if (median(prod_y) or 1) >= 0 else -1
    s_str = 1 if (median(prod_s) or 1) >= 0 else -1
    cal = {"radius": radius, "s_yaw": s_yaw, "s_str": s_str}
    # steering per unit path curvature at low lateral load = neutral reference
    ks = []
    for lp in laps:
        c = lp.c
        for i in range(0, len(lp.d), 2):
            v = c["spd"][i] / 3.6
            curv = s_yaw * c["yaw"][i] / v if v > 8 else 0
            if 0.15 < abs(c["latg"][i]) < 0.5 and abs(curv) > 0.003:
                ks.append(s_str * c["str"][i] / curv)
    cal["k_ref"] = median(ks)
    # which wheels are driven: larger positive slip at full throttle, low speed
    slips = [[], [], [], []]
    for lp in laps:
        for i in range(0, len(lp.d), 2):
            if lp.c["thr"][i] > 0.95 and 30 < lp.c["spd"][i] < 140:
                for w in range(4):
                    s = wheel_slip(lp.c, i, w, cal)
                    if s is not None:
                        slips[w].append(s)
    fr = median([median(slips[0]) or 0, median(slips[1]) or 0]) or 0
    rr = median([median(slips[2]) or 0, median(slips[3]) or 0]) or 0
    cal["driven"] = [2, 3] if rr > fr + 0.005 else ([0, 1] if fr > rr + 0.005 else [0, 1, 2, 3])
    return cal


def wheel_slip(c, i, w, cal):
    r = cal["radius"][w]
    v = c["spd"][i] / 3.6
    if not r or v < 8:
        return None
    return abs(c["rps%d" % w][i]) * r / v - 1.0


# =============================================================== corners
def detect_corners(ref):
    L = ref.L
    v = ref.on_grid("spd")
    v = smooth(v, 4)
    n = len(v)
    mins = []
    W = 8
    for i in range(1, n - 1):
        a, b = max(0, i - W), min(n, i + W + 1)
        if v[i] != min(v[a:b]):
            continue
        left = max(v[max(0, i - 80):i + 1])
        right = max(v[i:min(n, i + 60)])
        if left - v[i] >= 7 and right - v[i] >= 4:
            if mins and (i - mins[-1]) * GRID < 70:
                if v[i] < v[mins[-1]]:
                    mins[-1] = i
                continue
            mins.append(i)
    corners = []
    bounds = [0.0]
    for a, b in zip(mins, mins[1:]):
        seg = v[a:b + 1]
        j = a + seg.index(max(seg))
        bounds.append(j * GRID)
    bounds.append(L)
    for k, m in enumerate(mins):
        corners.append({"id": "T%d" % (k + 1), "name": "T%d" % (k + 1),
                        "apex_m": round(m * GRID, 1),
                        "start_m": round(bounds[k], 1), "end_m": round(bounds[k + 1], 1)})
    return corners


def track_map(store, meta, ref, remap=False, ref_clean=True, n_clean=0):
    """Corner map for this track. Re-detected until a session has 3+ clean laps, then locked
    so corner numbering stays stable across sessions. User-typed names are kept."""
    path = store.track_map_path(meta["track"], meta["variation"])
    tm = read_json(path)
    if tm and tm.get("corners") and tm.get("locked", True) and not remap and \
            abs(tm.get("length", 0) - meta["track_length"]) < 20:
        return tm
    corners = detect_corners(ref)
    if tm and tm.get("corners"):                   # keep names the user typed
        for c in corners:
            for old in tm["corners"]:
                if abs(old["apex_m"] - c["apex_m"]) < 40 and old.get("name") != old.get("id"):
                    c["name"] = old["name"]
    new = {"track": meta["track"], "variation": meta["variation"],
           "length": meta["track_length"], "corners": corners,
           "sector_dist": (ref.entry.get("sector_dist") or []),
           "map": {"x": ref.on_grid("x", 10), "z": ref.on_grid("z", 10)},
           "locked": ref_clean and n_clean >= 3,
           "landmarks": (tm or {}).get("landmarks") or [],
           "note": "Rename corners by editing 'name' (or in the dashboard). Delete this file "
                   "or use 'Re-detect corners' to rebuild it."}
    if ref_clean:
        write_json(path, new)
    return new


# =============================================================== per-corner metrics
def corner_metrics(lp, cn, cal):
    c = lp.c
    i0, i1 = lp.idx(cn["start_m"]), lp.idx(cn["end_m"])
    if i1 - i0 < 10:
        return None
    rng = range(i0, i1)
    # apex = min speed in the window around the mapped apex
    ia, ib = lp.idx(cn["apex_m"] - 60), lp.idx(cn["apex_m"] + 60)
    ia, ib = max(ia, i0), min(ib, i1 - 1)
    apex_i = min(range(ia, ib + 1), key=lambda i: c["spd"][i])
    apex_d = lp.d[apex_i]
    d = lp.d
    spd, thr, brk, steer = c["spd"], c["thr"], c["brk"], c["str"]
    m = {"apex_m": rnd(apex_d, 1), "min_speed": rnd(spd[apex_i], 1),
         "time": rnd(lp.time_at(cn["end_m"]) - lp.time_at(cn["start_m"]), 3)}
    entry_speed = max(spd[i] for i in range(i0, apex_i + 1))
    m["entry_speed"] = rnd(entry_speed, 1)
    m["exit_speed"] = rnd(spd[i1 - 1], 1)

    # ---- braking zone: contiguous brake>5% region ending before the apex (gaps < 8 m ok)
    bz_end = None
    for i in range(apex_i, i0 - 1, -1):
        if brk[i] > 0.05:
            bz_end = i
            break
    if bz_end is not None and apex_d - d[bz_end] < 120:
        bz_start = bz_end
        i = bz_end
        while i > i0:
            i -= 1
            if brk[i] > 0.05:
                bz_start = i
            elif d[bz_start] - d[i] > 8:
                break
        peak = max(brk[bz_start:bz_end + 1])
        ip = bz_start + brk[bz_start:bz_end + 1].index(peak)
        ramp_to = next((j for j in range(bz_start, bz_end + 1) if brk[j] >= 0.9 * peak), ip)
        # release: brake after the peak drops below 5%
        rel_i = next((j for j in range(ip, apex_i + 1) if brk[j] < 0.05), apex_i)
        m.update({
            "braking": True, "brake_m": rnd(d[bz_start] - apex_d, 1),
            "brake_start_m": rnd(d[bz_start], 1),
            "brake_speed": rnd(spd[bz_start], 1), "brake_peak": rnd(peak, 2),
            "brake_ramp_s": rnd(c["t"][ramp_to] - c["t"][bz_start], 3),
            "release_m": rnd(d[rel_i] - apex_d, 1),
        })
        # release shape: distance over which brake went from 50% of peak to <5%
        half_i = next((j for j in range(ip, rel_i + 1) if brk[j] < 0.5 * peak), rel_i)
        m["release_len_m"] = rnd(d[rel_i] - d[half_i], 1)
        # ABS / lockups during braking
        n_b = rel_i - bz_start + 1
        m["abs_pct"] = rnd(100.0 * sum(c["abs"][bz_start:rel_i + 1]) / max(1, n_b), 1)
        locks = []
        for w in range(4):
            run = 0
            worst = 0.0
            for j in range(bz_start, min(rel_i + 10, i1)):
                s_ = wheel_slip(c, j, w, cal)
                if s_ is not None and s_ < -0.18 and brk[j] > 0.1:
                    run += 1
                    worst = min(worst, s_)
                else:
                    if run >= 3:
                        break
                    run = 0
            if run >= 3:
                locks.append({"wheel": ("FL", "FR", "RL", "RR")[w], "slip": rnd(worst, 2)})
        m["lockups"] = locks
    else:
        m.update({"braking": False})
        lift_i = next((j for j in range(apex_i, i0 - 1, -1) if thr[j] > 0.9), None)
        m["lift_m"] = rnd(d[lift_i] - apex_d, 1) if lift_i is not None else None
        m["min_throttle"] = rnd(min(thr[i0:apex_i + 1]), 2)
        rel_i = apex_i

    # ---- turn-in: last point before the apex where steering < 25% of apex steering
    s_apex = abs(steer[apex_i]) or max(abs(steer[j]) for j in range(i0, i1))
    ti = apex_i
    while ti > i0 and abs(steer[ti]) > 0.25 * s_apex:
        ti -= 1
    m["turn_in_m"] = rnd(d[ti] - apex_d, 1)
    if m.get("braking"):
        m["brake_at_turn_in"] = rnd(brk[ti], 2)
        trail = 0.0
        for j in range(ti + 1, apex_i + 1):
            if brk[j] > 0.05:
                trail += d[j] - d[j - 1]
        m["trail_m"] = rnd(trail, 1)
        gap = None
        if trail <= 2:
            last_b = next((j for j in range(ti, i0 - 1, -1) if brk[j] > 0.05), None)
            gap = d[ti] - d[last_b] if last_b is not None else None
        m["release_gap_m"] = rnd(gap, 1)
        if trail > 8:
            style = "trail"
        elif trail <= 2 and (m["release_len_m"] or 99) < 6:
            style = "on-off"
        else:
            style = "early-release"
        m["release_style"] = style

    # ---- throttle pickup after release / apex
    start = min(rel_i, apex_i)
    pick = next((j for j in range(start, i1) if thr[j] > 0.2), None)
    full = next((j for j in range(pick or start, i1) if thr[j] > 0.95), None) if pick else None
    m["throttle_on_m"] = rnd(d[pick] - apex_d, 1) if pick is not None else None
    m["full_throttle_m"] = rnd(d[full] - apex_d, 1) if full is not None else None
    if pick is not None and full is not None:
        m["throttle_ramp_m"] = rnd(d[full] - d[pick], 1)
    # coasting: no pedals between release and pickup
    coast = 0.0
    for j in range(max(i0, rel_i if m.get("braking") else i0), (pick or apex_i) + 1):
        if j > 0 and brk[j] < 0.05 and thr[j] < 0.1:
            coast += d[j] - d[j - 1]
    m["coast_m"] = rnd(coast, 1)
    # lifts after reaching >85% throttle on exit
    lifts = []
    if pick is not None:
        reached = False
        low = None
        for j in range(pick, i1):
            if thr[j] > 0.85:
                if low is not None and low < 0.7:
                    lifts.append({"at_m": rnd(d[j] - apex_d, 0), "min_throttle": rnd(low, 2)})
                reached, low = True, None
            elif reached:
                low = thr[j] if low is None else min(low, thr[j])
    m["lifts"] = lifts
    # wheelspin on exit (driven wheels)
    spin = 0.0
    for j in range(apex_i, i1):
        if thr[j] > 0.3:
            ss = [wheel_slip(c, j, w, cal) for w in cal["driven"]]
            ss = [x for x in ss if x is not None]
            if ss and max(ss) > 0.12:
                spin += d[j] - d[j - 1]
    m["wheelspin_m"] = rnd(spin, 1)

    # ---- balance by phase: steering needed per unit of path curvature vs neutral reference
    k_ref = cal.get("k_ref")
    def bal(a, b):
        vals, slip = [], []
        for j in range(a, b):
            v = spd[j] / 3.6
            if v < 8 or abs(c["latg"][j]) < 0.35:
                continue
            curv = cal["s_yaw"] * c["yaw"][j] / v
            if abs(curv) < 0.002:
                continue
            if k_ref:
                vals.append(cal["s_str"] * steer[j] / curv / k_ref - 1.0)
            slip.append(abs(math.degrees(math.atan2(c["vx"][j], max(abs(c["vz"][j]), 1)))))
        return rnd(median(vals), 3), rnd(median(slip), 2), len(vals)
    ex_end = apex_i
    while ex_end < i1 - 1 and abs(steer[ex_end]) > 0.3 * s_apex:
        ex_end += 1
    m["bal_entry"], m["slip_entry"], _ = bal(ti, max(ti + 1, apex_i - 2))
    m["bal_mid"], m["slip_mid"], _ = bal(max(i0, apex_i - 4), min(i1, apex_i + 5))
    m["bal_exit"], m["slip_exit"], _ = bal(apex_i, max(apex_i + 1, ex_end))
    # counter-steer: steering points against the direction of the turn
    cs = 0
    for j in range(ti, ex_end + 1):
        if abs(c["latg"][j]) > 0.4 and abs(steer[j]) > 0.03 and \
                cal["s_str"] * steer[j] * c["latg"][j] < 0:
            cs += 1
    m["countersteer"] = cs >= 3
    m["max_steer"] = rnd(max(abs(steer[j]) for j in range(i0, i1)), 3)
    m["gear_min"] = min(int(c["gear"][j]) for j in range(i0, i1))
    return m


# =============================================================== lap-level technique
def lap_metrics(lp, corners_m, meta):
    c = lp.c
    max_rpm = meta.get("max_rpm") or 0
    limiter = 0.0
    if max_rpm:
        for j in range(1, len(lp.d)):
            if c["rpm"][j] > 0.985 * max_rpm and c["thr"][j] > 0.9:
                limiter += c["t"][j] - c["t"][j - 1]
    brakes = [m for m in corners_m.values() if m and m.get("braking")]
    trails = [m for m in brakes if m.get("release_style") == "trail"]
    return {
        "top_speed": rnd(max(c["spd"]), 1),
        "coast_m": rnd(sum((m or {}).get("coast_m") or 0 for m in corners_m.values()), 1),
        "lockups": sum(len(m.get("lockups", [])) for m in brakes),
        "wheelspin_m": rnd(sum((m or {}).get("wheelspin_m") or 0 for m in corners_m.values()), 1),
        "lifts": sum(len((m or {}).get("lifts", [])) for m in corners_m.values()),
        "trail_pct": rnd(100.0 * len(trails) / len(brakes), 0) if brakes else None,
        "countersteer": sum(1 for m in corners_m.values() if m and m.get("countersteer")),
        "limiter_s": rnd(limiter, 2),
        "top_gear_used": max(int(g) for g in c["gear"]) if c["gear"] else None,
        "full_throttle_pct": rnd(100.0 * sum(1 for x in c["thr"] if x > 0.95) / len(c["thr"]), 1),
        "ride_min_mm": [rnd(min(c["rh%d" % w]), 1) for w in range(4)],
    }


# =============================================================== trends
def trend(values, window=12):
    """values: chronological list (None allowed). Returns robust trend summary."""
    vals = [v for v in values if v is not None]
    if len(vals) < 3:
        return {"n": len(vals)}
    recent = vals[-window:]
    slope = theil_sen(recent)
    med_all = median(vals)
    sd = 1.4826 * (mad(vals) or 0)
    half = len(recent) // 2
    first, last = median(recent[:half] or recent), median(recent[half:])
    out = {"n": len(vals), "slope_per_lap": rnd(slope, 4), "median": rnd(med_all, 3),
           "robust_sd": rnd(sd, 3), "best": rnd(min(vals), 3), "p20": rnd(pct(vals, 0.2), 3),
           "recent_median": rnd(median(vals[-5:]), 3), "change": rnd(last - first, 3)}
    noise = max(sd / math.sqrt(max(half, 1)), 0.01)
    if last - first < -noise and (slope or 0) < 0:
        out["direction"] = "improving"
    elif last - first > noise and (slope or 0) > 0:
        out["direction"] = "losing"
    else:
        out["direction"] = "flat"
    out["outliers"] = [i for i, v in enumerate(values)
                       if v is not None and sd > 0 and abs(v - med_all) > 3 * sd]
    return out


# =============================================================== main entry
NUM_KEYS = ["release_gap_m", "brake_m", "brake_speed", "brake_peak", "brake_ramp_s", "release_len_m", "trail_m",
            "brake_at_turn_in", "turn_in_m", "min_speed", "throttle_on_m", "full_throttle_m",
            "coast_m", "wheelspin_m", "exit_speed", "abs_pct", "bal_entry", "bal_mid",
            "bal_exit", "slip_exit", "lift_m"]


def analyse_session(store, sid, remap=False, history_sessions=()):
    meta = store.load_session(sid)
    if not meta or not meta.get("laps"):
        return None
    L = meta["track_length"] or max(1.0, 1.0)
    laps = []
    for e in meta["laps"]:
        try:
            laps.append(Lap(e, store.load_lap(sid, e["lap"]), L))
        except (OSError, ValueError, KeyError):
            pass
    good = [lp for lp in laps if lp.entry["valid"] and not lp.entry["pit"] and len(lp.d) > 100]
    ref_clean = bool(good)
    if not good:
        good_any = [lp for lp in laps if len(lp.d) > 100 and lp.entry.get("complete")]
        if not good_any:
            return {"session": meta_summary(meta), "laps": [], "note": "no complete laps yet"}
        good = good_any
    ref = min(good, key=lambda lp: lp.time)
    cal = calibrate(good)
    tm = track_map(store, meta, ref, remap, ref_clean, len(good))
    corners = tm["corners"]

    per_lap = []
    for lp in laps:
        if len(lp.d) < 100 or not lp.entry.get("complete", True):
            continue
        cm = {cn["id"]: corner_metrics(lp, cn, cal) for cn in corners}
        per_lap.append({"lap": lp.n, "time": lp.time, "valid": lp.entry["valid"],
                        "pit": lp.entry["pit"], "run": lp.entry.get("run"),
                        "sectors": lp.entry.get("sectors"), "corners": cm,
                        "technique": lap_metrics(lp, cm, meta),
                        "tyres": lp.entry.get("tyres"), "brake_bias": front_bias(lp.entry),
                        "tc_setting": lp.entry.get("tc_setting"),
                        "abs_setting": lp.entry.get("abs_setting"),
                        "fuel_used": lp.entry.get("fuel_used")})
    clean = [p for p in per_lap if p["valid"] and not p["pit"]]

    # ---- theoretical bests
    secs = [p["sectors"] for p in clean if p["sectors"] and len(p["sectors"]) == 3]
    best_secs = [min(s[k] for s in secs) for k in range(3)] if secs else None
    seg_best = {}
    for cn in corners:
        ts = [p["corners"][cn["id"]]["time"] for p in clean if p["corners"].get(cn["id"])]
        seg_best[cn["id"]] = min(ts) if ts else None
    best_lap = min(clean, key=lambda p: p["time"]) if clean else None

    # ---- per corner summary: trend, consistency, potential, fast-vs-slow coaching
    corner_out = []
    for cn in corners:
        cid = cn["id"]
        rows = [p for p in clean if p["corners"].get(cid)]
        times = [p["corners"][cid]["time"] for p in rows]
        tr = trend(times)
        tr["outlier_laps"] = [rows[i]["lap"] for i in tr.get("outliers", [])]
        tr.pop("outliers", None)
        typical = median(times[-5:]) if times else None
        robust_best = pct(times, 0.15) if len(times) >= 4 else (min(times) if times else None)
        summary = {"id": cid, "name": cn["name"], "apex_m": cn["apex_m"],
                   "start_m": cn["start_m"], "end_m": cn["end_m"],
                   "best": rnd(min(times), 3) if times else None,
                   "robust_best": rnd(robust_best, 3), "typical": rnd(typical, 3),
                   "potential": rnd((typical or 0) - (robust_best or 0), 3) if times else None,
                   "trend": tr,
                   "typical_metrics": typical_metrics([p["corners"][cid] for p in rows[-5:]]),
                   "fast_vs_slow": fast_vs_slow(rows, cid)}
        summary["issues"] = corner_issues(summary["typical_metrics"],
                                          [p["corners"][cid] for p in rows[-5:]])
        corner_out.append(summary)

    lap_times = [p["time"] for p in clean]
    lap_trend = trend(lap_times)
    lap_trend["outlier_laps"] = [clean[i]["lap"] for i in lap_trend.get("outliers", [])]
    lap_trend.pop("outliers", None)
    tech_keys = ["coast_m", "lockups", "wheelspin_m", "lifts", "trail_pct", "countersteer"]
    tech_trend = {k: trend([p["technique"][k] for p in clean]) for k in tech_keys}
    for v in tech_trend.values():
        v.pop("outliers", None)

    runs = {}
    for p in clean:
        runs.setdefault(p["run"], []).append(p)
    run_out = []
    for r, ps in sorted(runs.items(), key=lambda kv: kv[0] or 0):
        run_out.append({"run": r, "laps": [p["lap"] for p in ps],
                        "times": [p["time"] for p in ps],
                        "best": rnd(min(p["time"] for p in ps), 3),
                        "median": rnd(median([p["time"] for p in ps]), 3),
                        "corners_median": {cn["id"]: rnd(median(
                            [p["corners"][cn["id"]]["time"] for p in ps
                             if p["corners"].get(cn["id"])]), 3) for cn in corners}})

    res = {
        "session": meta_summary(meta),
        "calibration": cal,
        "track_map": {"corners": corners, "sector_dist": tm.get("sector_dist"),
                      "map": tm.get("map")},
        "best_lap": best_lap["lap"] if best_lap else None,
        "best_time": best_lap["time"] if best_lap else None,
        "theoretical_sectors": rnd(sum(best_secs), 3) if best_secs else None,
        "best_sectors": best_secs,
        "theoretical_corners": rnd(sum(v for v in seg_best.values() if v), 3)
        if all(seg_best.values()) else None,
        "lap_trend": lap_trend,
        "technique_trend": tech_trend,
        "corners": sorted(corner_out, key=lambda c: -(c["potential"] or 0)),
        "runs": run_out,
        "laps": [{k: p[k] for k in ("lap", "time", "valid", "pit", "run", "sectors",
                                     "technique", "brake_bias", "fuel_used", "tc_setting",
                                     "abs_setting")}
                 for p in per_lap],
        "lap_corners": {p["lap"]: p["corners"] for p in per_lap},
        "tyres_last": per_lap[-1]["tyres"] if per_lap else None,
        "tyres_by_lap": {p["lap"]: p["tyres"] for p in per_lap},
    }
    if history_sessions:
        res["history"] = history(store, history_sessions, meta)
    return res


def front_bias(entry):
    """Brake bias as FRONT share. Laps recorded before 2026-11-06 stored AMS2's raw value,
    which is the REAR share (MINI showed 0.38 = 62% front); newer laps say so explicitly."""
    b = entry.get("brake_bias")
    if b is None or not 0 <= b <= 1:
        return None
    if entry.get("brake_bias_basis") == "front":
        return b
    return round(1.0 - b, 4)


def meta_summary(meta):
    return {k: meta.get(k) for k in ("id", "game", "track", "variation", "car", "car_class",
                                     "track_length", "session_type", "started",
                                     "conditions_start", "max_rpm", "num_gears")}


def typical_metrics(ms):
    ms = [m for m in ms if m]
    if not ms:
        return {}
    out = {}
    for k in NUM_KEYS:
        out[k] = rnd(median([m.get(k) for m in ms]), 3)
    styles = [m.get("release_style") for m in ms if m.get("release_style")]
    if styles:
        out["release_style"] = max(set(styles), key=styles.count)
    out["lockup_laps"] = sum(1 for m in ms if m.get("lockups"))
    out["lift_laps"] = sum(1 for m in ms if m.get("lifts"))
    out["countersteer_laps"] = sum(1 for m in ms if m.get("countersteer"))
    out["laps"] = len(ms)
    out["braking"] = any(m.get("braking") for m in ms)
    return out


def fast_vs_slow(rows, cid):
    """Compare what the driver does on his fastest third vs slowest third through this corner."""
    if len(rows) < 4:
        return None
    srt = sorted(rows, key=lambda p: p["corners"][cid]["time"])
    k = max(2, len(srt) // 3)
    fast, slow = srt[:k], srt[-k:]
    diff = {}
    for key in NUM_KEYS:
        a = median([p["corners"][cid].get(key) for p in fast])
        b = median([p["corners"][cid].get(key) for p in slow])
        if a is not None and b is not None:
            diff[key] = {"fast": rnd(a, 3), "slow": rnd(b, 3), "diff": rnd(a - b, 3)}
    lock_f = sum(1 for p in fast if p["corners"][cid].get("lockups"))
    lock_s = sum(1 for p in slow if p["corners"][cid].get("lockups"))
    return {"fast_laps": [p["lap"] for p in fast], "slow_laps": [p["lap"] for p in slow],
            "time_gap": rnd(median([p["corners"][cid]["time"] for p in slow]) -
                            median([p["corners"][cid]["time"] for p in fast]), 3),
            "lockups_fast": lock_f, "lockups_slow": lock_s, "metrics": diff,
            "insights": insights(diff, lock_f, lock_s, k)}


def insights(diff, lock_f, lock_s, k):
    out = []
    g = lambda key: (diff.get(key) or {}).get("diff")
    if g("brake_m") is not None and abs(g("brake_m")) >= 4:
        out.append("On fast laps you brake %.0f m %s (%.0f m vs %.0f m before the apex)." % (
            abs(g("brake_m")), "later" if g("brake_m") > 0 else "earlier",
            -diff["brake_m"]["fast"], -diff["brake_m"]["slow"]))
    if g("min_speed") is not None and abs(g("min_speed")) >= 1.5:
        out.append("Fast laps carry %.1f km/h %s minimum speed (%.1f vs %.1f)." % (
            abs(g("min_speed")), "more" if g("min_speed") > 0 else "less",
            diff["min_speed"]["fast"], diff["min_speed"]["slow"]))
    if g("throttle_on_m") is not None and abs(g("throttle_on_m")) >= 5:
        out.append("Throttle comes on %.0f m %s on fast laps." % (
            abs(g("throttle_on_m")), "earlier" if g("throttle_on_m") < 0 else "later"))
    if g("full_throttle_m") is not None and abs(g("full_throttle_m")) >= 8:
        out.append("Full throttle %.0f m %s on fast laps." % (
            abs(g("full_throttle_m")), "earlier" if g("full_throttle_m") < 0 else "later"))
    if g("coast_m") is not None and abs(g("coast_m")) >= 5:
        out.append("%.0f m %s coasting on fast laps." % (
            abs(g("coast_m")), "less" if g("coast_m") < 0 else "more"))
    if g("trail_m") is not None and abs(g("trail_m")) >= 8:
        out.append("Fast laps trail the brake %.0f m %s past turn-in." % (
            abs(g("trail_m")), "further" if g("trail_m") > 0 else "less far"))
    if g("exit_speed") is not None and abs(g("exit_speed")) >= 2:
        out.append("Exit speed %.1f km/h %s on fast laps." % (
            abs(g("exit_speed")), "higher" if g("exit_speed") > 0 else "lower"))
    if lock_s > lock_f:
        out.append("Lockups on %d of %d slow laps vs %d of %d fast laps." % (lock_s, k, lock_f, k))
    return out


def corner_issues(t, ms):
    out = []
    if not t:
        return out
    n = t.get("laps") or 1
    if t.get("braking") and t.get("release_style") in ("on-off", "early-release") and \
            (t.get("trail_m") or 0) <= 2:
        out.append({"type": "trail_braking", "text": "On/off brake release - brake is gone %.0f m "
                    "before turn-in. Bleed it off into the corner." % (t.get("release_gap_m") or 0)})
    if (t.get("coast_m") or 0) > 12:
        out.append({"type": "coasting", "text": "%.0f m coasting (no brake, no throttle) before "
                    "the throttle comes on." % t["coast_m"]})
    if t.get("lockup_laps", 0) >= max(2, n * 0.4):
        wheels = {}
        for m in ms:
            for lk in (m or {}).get("lockups", []):
                wheels[lk["wheel"]] = wheels.get(lk["wheel"], 0) + 1
        out.append({"type": "lockup", "text": "Lockup in %d of last %d laps (%s)." % (
            t["lockup_laps"], n, ", ".join("%s x%d" % kv for kv in sorted(wheels.items())))})
    if (t.get("wheelspin_m") or 0) > 8:
        out.append({"type": "wheelspin", "text": "%.0f m of wheelspin on exit." % t["wheelspin_m"]})
    if t.get("lift_laps", 0) >= max(2, n * 0.4):
        out.append({"type": "lift", "text": "Lift after reaching full throttle on exit in %d of "
                    "last %d laps." % (t["lift_laps"], n)})
    if t.get("countersteer_laps", 0) >= max(2, n * 0.4):
        out.append({"type": "oversteer", "text": "Counter-steer in %d of last %d laps." % (
            t["countersteer_laps"], n)})
    if (t.get("throttle_on_m") or 0) > 30:
        out.append({"type": "late_throttle", "text": "Throttle only %.0f m after the apex." %
                    t["throttle_on_m"]})
    if t.get("braking") and (t.get("brake_ramp_s") or 0) > 0.35:
        out.append({"type": "brake_ramp", "text": "Slow initial brake application (%.2f s to "
                    "peak) - hit the pedal harder at the start." % t["brake_ramp_s"]})
    return out


def history(store, sids, meta):
    """Best and median lap of earlier sessions with the same car/track."""
    out = []
    for sid in sids:
        m = store.load_session(sid)
        if not m:
            continue
        ts = [l["time"] for l in m["laps"] if l.get("valid") and not l.get("pit")]
        if ts:
            out.append({"session": sid, "started": m.get("started"), "laps": len(ts),
                        "best": min(ts), "median": rnd(median(ts), 3)})
    return out


def compare_traces(store, sid, laps, step=GRID):
    """Distance-aligned channels + delta for the dashboard / screenshots."""
    meta = store.load_session(sid)
    L = meta["track_length"]
    entries = {e["lap"]: e for e in meta["laps"]}
    objs = []
    for n in laps:
        if n in entries:
            objs.append(Lap(entries[n], store.load_lap(sid, n), L))
    if not objs:
        return None
    ref = objs[0]
    xs = [round(i * step, 1) for i in range(int(L // step) + 1)]
    out = {"dist": xs, "laps": []}
    for lp in objs:
        tr = {"lap": lp.n, "time": lp.time}
        for ch in ("spd", "thr", "brk", "str", "gear", "latg", "long", "rpm"):
            tr[ch] = [rnd(lp.val(ch, x), 3) for x in xs]
        tr["delta"] = [rnd(lp.time_at(x) - ref.time_at(x), 3) for x in xs]
        out["laps"].append(tr)
    return out
