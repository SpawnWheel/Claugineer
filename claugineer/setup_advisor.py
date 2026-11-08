"""Data-driven setup advice.

Rules are deliberately conservative: each one cites the measured numbers it is based
on, gives a direction and a typical step size, and says what the driver should feel.
AMS2-specific conventions:
  * Diff ramp angle: HIGHER angle = LESS locking.
  * Engine braking: HIGHER number = LESS engine braking.
  * Front ARB stiffer = more understeer; rear ARB stiffer = more oversteer.
"""
from .analysis import median, rnd
from .frames import WHEELS


def find_profile(cfg, car, car_class):
    profiles = cfg.get("car_profiles", {})
    name = (car or "").lower()
    cls = (car_class or "").lower()
    for key, prof in profiles.items():
        if key.lower() in name:
            return key, prof
    for key, prof in profiles.items():
        if key.lower() in cls:
            return key, prof
    return None, {}


def run_laps(analysis):
    """Clean laps of the most recent run (stint)."""
    laps = [l for l in analysis["laps"] if l["valid"] and not l["pit"]]
    if not laps:
        return []
    last_run = laps[-1]["run"]
    return [l for l in laps if l["run"] == last_run]


def advise(analysis, cfg, setup_sheet=None):
    meta = analysis["session"]
    setup_vals = (setup_sheet or {}).get("values", {})
    prof_name, prof = find_profile(cfg, meta.get("car"), meta.get("car_class"))
    recs = []
    laps = run_laps(analysis)
    tyres_by_lap = analysis.get("tyres_by_lap", {})
    run_tyres = [tyres_by_lap.get(l["lap"]) or tyres_by_lap.get(str(l["lap"])) for l in laps]
    run_tyres = [t for t in run_tyres if t]
    # use the second half of the run (tyres up to temperature)
    hot = run_tyres[len(run_tyres) // 2:] or run_tyres

    # ------------------------------------------------ consistency gate
    times = [l["time"] for l in laps][-5:]
    spread = (max(times) - min(times)) if len(times) >= 3 else None
    phase = "setup" if spread is not None and spread <= cfg.get("consistency_gate_s", 0.5) \
        else "driving"

    # ------------------------------------------------ tyre pressures
    tyre_state = {}
    if hot:
        for w in WHEELS:
            vals = [t[w] for t in hot if w in t]
            tyre_state[w] = {
                "pressure_hot": rnd(median([v["pressure_end"] for v in vals]), 3),
                "inner": rnd(median([v["inner"] for v in vals]), 1),
                "middle": rnd(median([v["middle"] for v in vals]), 1),
                "outer": rnd(median([v["outer"] for v in vals]), 1),
                "carcass": rnd(median([v["carcass"] for v in vals]), 1),
                "brake_max": rnd(max(v["brake_max"] for v in vals), 0),
                "wear": vals[-1]["wear_end"],
            }
        tgt = prof.get("hot_pressure_bar")
        if tgt:
            for axle, ws in (("front", ("FL", "FR")), ("rear", ("RL", "RR"))):
                t_ax = tgt.get(axle) if isinstance(tgt, dict) else tgt
                if not t_ax:
                    continue
                lo, hi = (t_ax if isinstance(t_ax, list) else [t_ax - 0.03, t_ax + 0.03])
                mid = (lo + hi) / 2
                p = median([tyre_state[w]["pressure_hot"] for w in ws])
                if p is None:
                    continue
                if p < lo - 0.02 or p > hi + 0.02:
                    delta = mid - p
                    cold_key = "pressure_" + axle
                    frm = setup_vals.get(cold_key)
                    change = "%s cold pressure %+.2f bar" % (axle, delta)
                    if isinstance(frm, (int, float)):
                        change = "%s cold pressure %.2f -> %.2f bar" % (axle, frm, frm + delta)
                    recs.append({
                        "area": "tyres", "priority": 90 if abs(delta) > 0.08 else 60,
                        "observation": "%s hot pressure %.2f bar (target %.2f-%.2f, profile '%s')"
                                       % (axle, p, lo, hi, prof_name),
                        "change": change,
                        "why": "Hot pressure outside the target window; a cold change carries "
                               "over roughly 1:1 to the hot value.",
                        "feel": "More consistent grip through the run; fewer laps where the car "
                                "goes off after 2-3 laps." if delta < 0 else
                                "Sharper response, less squirm and lower tyre temps.",
                    })
        # camber from inner/outer spread on the wheel the track loads (hotter carcass side)
        left = median([tyre_state[w]["carcass"] for w in ("FL", "RL")]) or 0
        right = median([tyre_state[w]["carcass"] for w in ("FR", "RR")]) or 0
        loaded = ("FL", "RL") if left > right else ("FR", "RR")
        for w in loaded:
            t = tyre_state[w]
            spread_io = (t["inner"] or 0) - (t["outer"] or 0)
            t["io_spread"] = rnd(spread_io, 1)
            axle = "front" if w[0] == "F" else "rear"
            if spread_io < -1:
                recs.append({"area": "camber", "priority": 50,
                             "observation": "%s (loaded side) outer edge %.1f C hotter than inner"
                                            % (w, -spread_io),
                             "change": "%s camber 0.2-0.3 deg more negative (if adjustable)" % axle,
                             "why": "Outer shoulder overheating on the loaded tyre means it rolls "
                                    "over in the corner.",
                             "feel": "More mid-corner grip on that axle."})
            elif spread_io > 10:
                recs.append({"area": "camber", "priority": 40,
                             "observation": "%s (loaded side) inner edge %.1f C hotter than outer"
                                            % (w, spread_io),
                             "change": "%s camber 0.2 deg less negative (if adjustable)" % axle,
                             "why": "Even the loaded tyre runs hot on the inside: more camber "
                                    "than the corners use, costing braking/traction grip.",
                             "feel": "Better braking and traction, similar cornering."})
        for w in WHEELS:
            if "io_spread" not in tyre_state[w]:
                tyre_state[w]["io_spread"] = rnd((tyre_state[w]["inner"] or 0) -
                                                 (tyre_state[w]["outer"] or 0), 1)

    # ------------------------------------------------ brake bias from lockups
    lc = analysis.get("lap_corners", {})
    clean_laps = [l["lap"] for l in analysis["laps"] if l["valid"] and not l["pit"]]
    f_lock = r_lock = 0
    for n in clean_laps:
        for m in (lc.get(n) or lc.get(str(n)) or {}).values():
            for lk in (m or {}).get("lockups", []):
                if lk["wheel"][0] == "F":
                    f_lock += 1
                else:
                    r_lock += 1
    bias = median([l.get("brake_bias") for l in laps])
    bias_txt = ("%.1f%% front" % (bias * 100)) if bias else "current"
    if f_lock >= 3 and f_lock > 2 * r_lock:
        to = (" -> %.1f%% front" % (bias * 100 - 1)) if bias else " 1% rearward"
        recs.append({"area": "brakes", "priority": 70,
                     "observation": "%d front lockups vs %d rear over %d clean laps"
                                    % (f_lock, r_lock, len(clean_laps)),
                     "change": "brake bias %s%s (one click/1%% rearward)" % (bias_txt, to),
                     "why": "The fronts lock first; moving bias back uses more rear braking.",
                     "feel": "Fronts stop flat-spotting at the hard stops; car turns in better "
                             "under brakes. If the rear gets nervous on entry, go back."})
    elif r_lock >= 2 and r_lock >= f_lock:
        to = (" -> %.1f%% front" % (bias * 100 + 1)) if bias else " 1% forward"
        recs.append({"area": "brakes", "priority": 75,
                     "observation": "%d rear lockups vs %d front" % (r_lock, f_lock),
                     "change": "brake bias %s%s" % (bias_txt, to),
                     "why": "Rear wheels locking makes the car unstable on entry.",
                     "feel": "Calmer rear on the brakes, a touch more entry understeer."})

    # ------------------------------------------------ balance by phase
    def collect(key, fast):
        vals = []
        for n in clean_laps[-6:]:
            for m in (lc.get(n) or lc.get(str(n)) or {}).values():
                if m and m.get(key) is not None and m.get("min_speed") is not None:
                    if (m["min_speed"] >= cfg.get("fast_corner_kmh", 120)) == fast:
                        vals.append(m[key])
        return median(vals), len(vals)

    bal = {}
    for spd_cls, fast in (("slow", False), ("fast", True)):
        for ph in ("entry", "mid", "exit"):
            v, n = collect("bal_" + ph, fast)
            bal["%s_%s" % (spd_cls, ph)] = {"value": rnd(v, 3), "n": n}
    us, os_ = cfg.get("understeer_threshold", 0.15), cfg.get("oversteer_threshold", -0.10)
    rules = {
        ("entry", "us"): ("brake bias 1% rearward or soften front bump 1 click; first check you "
                          "trail-brake into the turn-in", "Front pushes wide as you turn in."),
        ("entry", "os"): ("brake bias 1% forward, less engine braking (HIGHER number in AMS2), "
                          "or more coast diff locking (LOWER coast ramp angle)",
                          "Rear steps out as you release the brake."),
        ("mid", "us"): ("soften front ARB 1 step (or stiffen rear ARB); in fast corners add "
                        "1 step front wing", "Mid-corner push, needing more lock to hold the line."),
        ("mid", "os"): ("soften rear ARB 1 step (or stiffen front ARB); in fast corners add "
                        "1 step rear wing", "Rear rotates/slides at the apex."),
        ("exit", "us"): ("less power diff locking (HIGHER power ramp angle) or soften front ARB",
                         "Car runs wide on throttle."),
        ("exit", "os"): ("softer rear ARB / softer rear springs, +1 TC, or more power diff "
                         "locking if only the inside wheel spins",
                         "Rear slides or wheelspin as you pick up the throttle."),
    }
    for key, b in bal.items():
        v = b["value"]
        if v is None or b["n"] < 4:
            continue
        spd_cls, ph = key.split("_")
        kind = "us" if v > us else ("os" if v < os_ else None)
        if not kind:
            continue
        change, feel = rules[(ph, kind)]
        recs.append({
            "area": "balance", "priority": 55 + int(min(30, abs(v) * 60)),
            "observation": "%s %s-corner %s: steering per unit of path curvature %+.0f%% vs the "
                           "car's neutral reference (%d samples)"
                           % (spd_cls, ph, "understeer" if kind == "us" else "oversteer",
                              v * 100, b["n"]),
            "change": change, "why": "Measured %s on %s %s" % (
                "understeer" if kind == "us" else "oversteer", spd_cls, ph),
            "feel": "Fixes: " + feel})

    # wheelspin / countersteer on exit
    spin = median([l["technique"]["wheelspin_m"] for l in laps])
    if spin and spin > 15:
        tc = median([l.get("tc_setting") for l in analysis["laps"] if l.get("tc_setting")])
        recs.append({"area": "traction", "priority": 50,
                     "observation": "%.0f m of driven-wheel spin per lap (median, this run)" % spin,
                     "change": "TC +1 (if fitted), or softer rear ARB/springs; driving: squeeze "
                               "the throttle over 40-60 m instead of stepping on it",
                     "why": "Wheelspin on exit costs drive down the next straight.",
                     "feel": "Car hooks up earlier, less rear movement on throttle."})

    # gearing
    lim = median([l["technique"]["limiter_s"] for l in laps])
    if lim and lim > 0.4:
        recs.append({"area": "gearing", "priority": 45,
                     "observation": "%.1f s per lap on the rev limiter at full throttle" % lim,
                     "change": "lengthen top gear / final drive one step",
                     "why": "Time on the limiter is speed you can't use.",
                     "feel": "Higher top speed at the end of the longest straight."})
    top_gear = median([l["technique"]["top_gear_used"] for l in laps])
    if meta.get("num_gears") and top_gear and top_gear < meta["num_gears"] and not lim:
        recs.append({"area": "gearing", "priority": 20,
                     "observation": "top gear used %d of %d" % (top_gear, meta["num_gears"]),
                     "change": "optional: shorten final drive one step for better acceleration",
                     "why": "Highest gear never used.", "feel": "Punchier exits."})

    # ride height / bottoming
    rh = [l["technique"]["ride_min_mm"] for l in laps if l["technique"].get("ride_min_mm")]
    if rh:
        fr = median([min(r[0], r[1]) for r in rh])
        rr = median([min(r[2], r[3]) for r in rh])
        if fr is not None and 0 < fr < cfg.get("bottoming_mm", 8):
            recs.append({"area": "ride_height", "priority": 45,
                         "observation": "front ride height reaches %.0f mm (min per lap, median)" % fr,
                         "change": "front ride height +2 mm or +1 step front bump/spring",
                         "why": "Car is close to bottoming at the front.",
                         "feel": "Less snap understeer/instability over bumps and kerbs."})
        if rr is not None and 0 < rr < cfg.get("bottoming_mm", 8):
            recs.append({"area": "ride_height", "priority": 45,
                         "observation": "rear ride height reaches %.0f mm" % rr,
                         "change": "rear ride height +2 mm or stiffer rear spring",
                         "why": "Rear close to bottoming.", "feel": "More stable rear at speed."})

    recs.sort(key=lambda r: -r["priority"])
    fuel = median([l.get("fuel_used") for l in analysis["laps"]
                   if l.get("fuel_used") and l["valid"]])
    return {
        "phase": phase,
        "consistency_last5_s": rnd(spread, 3),
        "phase_note": ("Last 5 laps within %.2f s: setup changes are worthwhile now." % spread)
        if phase == "setup" else
        ("Laps still spread %s s: work on driving first, setup changes would be lost in the noise."
         % (("%.2f" % spread) if spread is not None else "?")),
        "car_profile": prof_name,
        "tyres": tyre_state, "balance": bal, "lockups": {"front": f_lock, "rear": r_lock},
        "brake_bias": bias, "fuel_per_lap": rnd(fuel, 2),
        "recommendations": recs,
        "one_change": recs[0] if (recs and phase == "setup") else None,
    }


def run_comparison(analysis, setup_sheet):
    """Compare runs (stints) by robust medians, labelled with the setup change log."""
    runs = analysis.get("runs", [])
    changes = {c.get("run"): c.get("text") for c in (setup_sheet or {}).get("changes", [])}
    out = []
    prev = None
    for r in runs:
        row = {"run": r["run"], "laps": len(r["laps"]), "best": r["best"], "median": r["median"],
               "change": changes.get(r["run"])}
        if prev and r["median"] and prev["median"]:
            row["median_delta"] = rnd(r["median"] - prev["median"], 3)
            deltas = {}
            for cid, v in r["corners_median"].items():
                pv = prev["corners_median"].get(cid)
                if v is not None and pv is not None:
                    deltas[cid] = rnd(v - pv, 3)
            row["corner_deltas"] = deltas
            n1, n2 = len(r["laps"]), len(prev["laps"])
            pooled = []
            for rr in (r, prev):
                m_ = median(rr.get("times") or [])
                pooled += [abs(t - m_) for t in rr.get("times") or []]
            sd = 1.4826 * (median(pooled) or 0.2)
            se = sd * (1.0 / max(n1, 1) + 1.0 / max(n2, 1)) ** 0.5
            row["noise_s"] = rnd(2 * se, 3)
            row["significant"] = n1 >= 3 and n2 >= 3 and abs(row["median_delta"]) > 2 * se
        out.append(row)
        prev = r
    return out
