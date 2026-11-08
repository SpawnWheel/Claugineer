"""Cross-session views for the dashboard: every lap of a track+car combo, habit flags per
corner pass, habit rates over all sessions, and multi-session trace comparison.

Habit definitions live here (one place) so the dashboard, the brief and Claude agree.
"""
from . import analysis as an
from . import lines as ln

TRACE_STEP = 2.0          # metres; fine enough to zoom into a single corner
TRACE_CHANNELS = ("spd", "thr", "brk", "str", "gear", "latg", "long", "rpm", "abs", "x", "z")

# id -> (label, explanation). Order = display order.
HABITS = {
    "coast": ("Coasting", "More than 12 m with neither pedal pressed between braking and throttle."),
    "onoff": ("On/off brake release", "Brake fully released before turn-in instead of trailing it into the corner."),
    "slow_ramp": ("Slow brake hit", "More than 0.35 s from first touch to peak brake pressure."),
    "lockup": ("Lockup", "A wheel locked (slip below -18% for 3+ samples) under braking."),
    "late_throttle": ("Late throttle", "First throttle more than 30 m after the apex."),
    "lift": ("Lift on exit", "Throttle dropped below 70% after you had reached full throttle."),
    "wheelspin": ("Wheelspin", "More than 8 m of driven-wheel spin on exit."),
    "countersteer": ("Counter-steer", "Opposite lock needed - the rear stepped out."),
    "overslow": ("Over-slowing", "Minimum speed 4+ km/h below your best lap in this corner."),
    "early_brake": ("Early braking", "Braking 10+ m earlier than on your best lap in this corner."),
    "early_turn_in": ("Early turn-in", "Turning in 10+ m earlier than on your best lap."),
    "early_apex": ("Early apex", "Closest to the inside 20+ m earlier than on your fastest laps - usually means running wide on exit."),
    "late_apex": ("Late apex", "Closest to the inside 20+ m later than on your best lap."),
    "missed_apex": ("Missed apex", "1.5 m+ further from the inside than the tightest line you've driven here (valid laps)."),
}


def habit_flags(m, ref=None):
    """Flags for one corner pass. ref = metrics of the same corner on the reference (best) lap."""
    if not m:
        return []
    f = []
    if (m.get("coast_m") or 0) > 12:
        f.append("coast")
    if m.get("braking") and m.get("release_style") in ("on-off", "early-release") and \
            (m.get("trail_m") or 0) <= 2:
        f.append("onoff")
    if m.get("braking") and (m.get("brake_ramp_s") or 0) > 0.35:
        f.append("slow_ramp")
    if m.get("lockups"):
        f.append("lockup")
    if (m.get("throttle_on_m") or 0) > 30:
        f.append("late_throttle")
    if m.get("lifts"):
        f.append("lift")
    if (m.get("wheelspin_m") or 0) > 8:
        f.append("wheelspin")
    if m.get("countersteer"):
        f.append("countersteer")
    if ref:
        if m.get("min_speed") is not None and ref.get("min_speed") is not None and \
                m["min_speed"] < ref["min_speed"] - 4:
            f.append("overslow")
        if m.get("braking") and ref.get("braking") and m.get("brake_m") is not None and \
                ref.get("brake_m") is not None and m["brake_m"] < ref["brake_m"] - 10:
            f.append("early_brake")
    return f


_KEEP = ("time", "min_speed", "entry_speed", "exit_speed", "braking", "brake_m", "brake_speed",
         "brake_peak", "brake_ramp_s", "release_style", "trail_m", "turn_in_m", "throttle_on_m",
         "full_throttle_m", "coast_m", "wheelspin_m", "bal_entry", "bal_mid", "bal_exit",
         "max_steer", "gear_min", "abs_pct", "countersteer")


def _slim(m):
    if not m:
        return None
    out = {k: m.get(k) for k in _KEEP}
    out["lockups"] = len(m.get("lockups") or [])
    out["lifts"] = len(m.get("lifts") or [])
    out["lift_at"] = (m.get("lifts") or [{}])[0].get("at_m")
    return out


def combos(store):
    out = {}
    for s in store.list_sessions():
        if not s.get("track") or not s.get("laps"):
            continue
        key = (s["track"], s["variation"], s["car"])
        c = out.setdefault(key, {"track": s["track"], "variation": s["variation"], "car": s["car"],
                                 "sessions": 0, "laps": 0, "best": None, "last": None, "sid": s["id"]})
        c["sessions"] += 1
        c["laps"] += s["laps"]
        if s.get("best") and (c["best"] is None or s["best"] < c["best"]):
            c["best"] = s["best"]
        if not c["last"] or (s.get("started") or "") > c["last"]:
            c["last"] = s.get("started")
            c["sid"] = s["id"]
    return sorted(out.values(), key=lambda c: c["last"] or "", reverse=True)


def combo_laps(app, sid):
    """Every analysed lap of the track+car combo of `sid`, oldest first, with corner metrics
    and habit flags (relative flags use the combo's best valid lap as reference)."""
    store = app.store
    meta = store.load_session(sid)
    sids = store.sessions_for_combo(meta["track"], meta["variation"], meta["car"])
    sessions, laps, corners, tmap, changes = [], [], None, None, []
    for s in sids:
        a = app.analysis(s)
        m = store.load_session(s) or {}
        if not a or not a.get("laps"):
            continue
        if a.get("track_map"):
            corners = a["track_map"].get("corners") or corners
            tmap = a["track_map"]
        lc = a.get("lap_corners") or {}
        entries = {e["lap"]: e for e in m.get("laps", [])}
        sess = {"id": s, "started": m.get("started"), "type": m.get("session_type"),
                "best": a.get("best_time"), "laps": 0}
        for l in a["laps"]:
            cm = lc.get(str(l["lap"])) or lc.get(l["lap"]) or {}
            e = entries.get(l["lap"], {})
            tyres = e.get("tyres") or {}
            laps.append({"session": s, "started": m.get("started"), "lap": l["lap"],
                         "time": l["time"], "valid": l["valid"], "pit": l["pit"],
                         "run": l.get("run"), "sectors": l.get("sectors"),
                         "technique": l.get("technique"), "brake_bias": l.get("brake_bias"),
                         "fuel_used": l.get("fuel_used"), "recorded": e.get("recorded"),
                         "tyres": {w: {"p": t.get("pressure_end"), "mid": t.get("middle")}
                                   for w, t in tyres.items()},
                         "corners": {k: _slim(v) for k, v in cm.items()}})
            sess["laps"] += 1
        sessions.append(sess)
    clean = [l for l in laps if l["valid"] and not l["pit"]]
    ref = min(clean, key=lambda l: l["time"]) if clean else None
    for l in laps:
        l["flags"] = {cid: habit_flags(m, (ref or {}).get("corners", {}).get(cid))
                      for cid, m in l["corners"].items() if m}
    # driving line (needs the raw traces; cached in memory after the first call)
    env = None
    try:
        cmb = {(l["session"], l["lap"]): l["corners"] for l in laps if not l["pit"]}
        vk = {(l["session"], l["lap"]) for l in clean}
        cl = ln.combo_lines(store, sid, corners or [], cmb, vk)
    except Exception as e:          # never break the dashboard over line maths
        cl = None
    if cl:
        fastest = [(l["session"], l["lap"]) for l in sorted(clean, key=lambda l: l["time"])[:3]]
        rl = ln.reference_metrics(cl["laps"], fastest)
        for l in laps:
            lm = cl["laps"].get((l["session"], l["lap"]))
            if not lm:
                continue
            l["line"] = lm
            for cid, m in lm.items():
                l["flags"].setdefault(cid, []).extend(ln.line_flags(m, rl.get(cid)))
    # setup change log typed in the Setup tab
    from .storage import read_json
    sheet = read_json(store.setup_path(meta["car"], meta["track"], meta["variation"]), {}) or {}
    changes = sheet.get("changes", [])
    return {"track": meta["track"], "variation": meta["variation"], "car": meta["car"],
            "track_length": meta.get("track_length"), "sessions": sessions, "laps": laps,
            "corners": corners or [], "map": (tmap or {}).get("map"),
            "landmarks": (tmap or {}).get("landmarks") or [],
            "sector_dist": (tmap or {}).get("sector_dist"),
            "ref": {"session": ref["session"], "lap": ref["lap"], "time": ref["time"]} if ref else None,
            "habits": [{"id": k, "label": v[0], "why": v[1]} for k, v in HABITS.items()],
            "changes": changes}


def habits_all(app):
    """Habit rates (% of corner passes) per session across every track and car."""
    out = []
    for s in reversed(app.store.list_sessions()):
        if not s.get("laps") or not s.get("track"):
            continue
        a = app.analysis(s["id"])
        if not a or not a.get("laps"):
            continue
        lc = a.get("lap_corners") or {}
        clean = [l for l in a["laps"] if l["valid"] and not l["pit"]]
        if not clean:
            continue
        best = min(clean, key=lambda l: l["time"])
        refc = lc.get(str(best["lap"])) or lc.get(best["lap"]) or {}
        counts, passes = {k: 0 for k in HABITS}, 0
        for l in a["laps"]:
            if l["pit"]:
                continue
            for cid, m in (lc.get(str(l["lap"])) or lc.get(l["lap"]) or {}).items():
                if not m:
                    continue
                passes += 1
                for fl in habit_flags(m, refc.get(cid)):
                    counts[fl] += 1
        if passes:
            out.append({"session": s["id"], "started": s.get("started"), "track": s["track"],
                        "variation": s["variation"], "car": s["car"], "passes": passes,
                        "laps": len(a["laps"]),
                        "rates": {k: round(100.0 * v / passes, 1) for k, v in counts.items()}})
    return {"habits": [{"id": k, "label": v[0], "why": v[1]} for k, v in HABITS.items()],
            "sessions": out}


def traces(store, refs, step=TRACE_STEP):
    """refs = [(sid, lap), ...]; first is the reference. Laps may come from different sessions
    of the same track. Returns distance-aligned channels and delta to the reference."""
    objs = []
    L = None
    for sid, n in refs:
        meta = store.load_session(sid)
        if not meta:
            continue
        e = next((x for x in meta["laps"] if x["lap"] == n), None)
        if not e:
            continue
        try:
            lp = an.Lap(e, store.load_lap(sid, n), meta["track_length"])
        except Exception:            # unreadable / corrupt lap file
            continue
        if len(lp.d) < 100:
            continue
        L = L or meta["track_length"]
        objs.append((sid, meta, lp))
    if not objs:
        return None
    ref = objs[0][2]
    xs = [round(i * step, 1) for i in range(int(L // step) + 1)]
    out = {"dist": xs, "laps": [], "track_length": L}
    for sid, meta, lp in objs:
        tr = {"session": sid, "started": meta.get("started"), "lap": lp.n, "time": lp.time,
              "valid": lp.entry.get("valid"), "complete": lp.entry.get("complete", True)}
        dmax = lp.d[-1] if lp.d else 0
        for ch in TRACE_CHANNELS:
            if ch not in lp.c:
                continue
            tr[ch] = [an.rnd(lp.val(ch, x), 3) if x <= dmax + 1 else None for x in xs]
        tr["delta"] = [an.rnd(lp.time_at(x) - ref.time_at(x), 3) if x <= dmax + 1 else None
                       for x in xs]
        out["laps"].append(tr)
    # driving line vs the best lap at this track/car + the road you have used (valid laps)
    try:
        env = ln.envelope(store, objs[0][0])
        if env and abs(step - ln.STEP) < 1e-9:
            out["line_ref"] = {"session": env["ref"][0], "lap": env["ref"][1]}
            out["env_left"], out["env_right"] = env["env_left"], env["env_right"]
            for (sid, meta, lp), tr in zip(objs, out["laps"]):
                tr["lat"] = ln.offsets(store, env["ref"], (sid, lp.n), xs)
            rg = ln._lap_grid(store, env["ref"][0], env["ref"][1], xs)
            out["ref_x"] = [None if v is None else round(v, 2) for v in rg[0]]
            out["ref_z"] = [None if v is None else round(v, 2) for v in rg[1]]
    except Exception:
        pass
    return out
