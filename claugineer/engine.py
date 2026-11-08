"""Runs analysis + setup advice and writes analysis.json / brief.md for a session."""
import os

from . import analysis as an
from .recorder import fmt_time
from .setup_advisor import advise, run_comparison
from .storage import read_json, write_json


def build(store, cfg, sid, remap=False):
    meta = store.load_session(sid)
    if not meta:
        return None
    combo = [s for s in store.sessions_for_combo(meta["track"], meta["variation"], meta["car"])
             if s != sid]
    res = an.analyse_session(store, sid, remap=remap, history_sessions=combo[-10:])
    if not res or not res.get("laps"):
        return res
    sheet = read_json(store.setup_path(meta["car"], meta["track"], meta["variation"]), {})
    res["setup"] = advise(res, cfg, sheet)
    res["setup"]["sheet"] = sheet
    res["run_comparison"] = run_comparison(res, sheet)
    res["plan"] = next_run_plan(res)
    write_json(store.session_path(sid, "analysis.json"), res)
    md = brief_md(res)
    try:
        from .notes import brief_section
        md += brief_section(store, meta)
    except Exception:
        pass
    with open(store.session_path(sid, "brief.md"), "w", encoding="utf-8") as f:
        f.write(md)
    with open(os.path.join(store.root, "latest_brief.md"), "w", encoding="utf-8") as f:
        f.write(md)
    write_json(os.path.join(store.root, "latest.json"),
               {"session": sid, "analysis": os.path.join("sessions", sid, "analysis.json"),
                "brief": os.path.join("sessions", sid, "brief.md")})
    return res


def next_run_plan(res):
    """Top 3 places to find time, each with one concrete action, plus the one change."""
    items = []
    for c in res["corners"]:
        if not c.get("potential") or c["potential"] < 0.03:
            continue
        action = None
        fvs = c.get("fast_vs_slow") or {}
        if c.get("issues"):
            action = c["issues"][0]["text"]
        if fvs.get("insights"):
            action = (action + " " if action else "") + "Repeat your fast laps: " + \
                fvs["insights"][0]
        items.append({"corner": c["name"], "id": c["id"], "potential_s": c["potential"],
                      "trend": c["trend"].get("direction"), "action": action or
                      "Look at the trace: no single clear cause measured."})
    items = items[:3]
    setup = res.get("setup", {})
    one = setup.get("one_change")
    return {"focus": items, "phase": setup.get("phase"),
            "one_change": one["change"] if one else
            ("Driving only - " + items[0]["action"] if items else None)}


def _f(x, n=3, unit=""):
    if x is None:
        return "-"
    return ("%." + str(n) + "f%s") % (x, unit)


def brief_md(res):
    s = res["session"]
    L = []
    L.append("# Engineer brief - %s %s - %s" % (s["track"], s["variation"], s["car"]))
    cond = s.get("conditions_start") or {}
    if cond.get("air_c") is None:            # RaceRoom publishes no air/track temperature
        L.append("Session %s (%s, %s), started %s." % (
            s["id"], s["session_type"], s.get("game", "ams2").upper(), s["started"]))
    else:
        L.append("Session %s (%s), started %s. Air %s C, track %s C, rain %s." % (
            s["id"], s["session_type"], s["started"], cond.get("air_c"), cond.get("track_c"),
            cond.get("rain")))
    L.append("")
    lt = res["lap_trend"]
    L.append("## Headline")
    L.append("- Best lap: %s (lap %s). Theoretical: sectors %s, corners %s." % (
        fmt_time(res["best_time"]), res["best_lap"], fmt_time(res["theoretical_sectors"]),
        fmt_time(res["theoretical_corners"])))
    L.append("- Lap-time trend: %s, %s s/lap (robust), recent median %s, spread (robust sd) %s s."
             % (lt.get("direction"), _f(lt.get("slope_per_lap"), 3), fmt_time(lt.get("recent_median")),
                _f(lt.get("robust_sd"), 3)))
    if lt.get("outlier_laps"):
        L.append("- Outlier laps (ignored for comparisons): %s" % lt["outlier_laps"])
    if res.get("history"):
        h = res["history"][-1]
        L.append("- Previous session same combo: best %s, median %s." % (
            fmt_time(h["best"]), fmt_time(h["median"])))
    setup = res.get("setup", {})
    L.append("- Phase: **%s** - %s" % (setup.get("phase"), setup.get("phase_note")))
    L.append("")
    L.append("## Laps")
    L.append("| lap | run | time | S1 | S2 | S3 | valid | coast m | lockups | spin m | lifts | trail % |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for l in res["laps"]:
        sec = l.get("sectors") or [None, None, None]
        t = l["technique"]
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            l["lap"], l["run"], fmt_time(l["time"]), _f(sec[0]), _f(sec[1]), _f(sec[2]),
            "pit" if l["pit"] else ("Y" if l["valid"] else "N"), _f(t["coast_m"], 0),
            t["lockups"], _f(t["wheelspin_m"], 0), t["lifts"], _f(t["trail_pct"], 0)))
    L.append("")
    L.append("## Where the time is (typical = median of last 5, vs your robust best)")
    for c in res["corners"]:
        tr = c["trend"]
        tm = c["typical_metrics"]
        L.append("### %s apex %.0f m - potential %s s, trend %s (%s s/lap)%s" % (
            c["name"] if c["name"] == c["id"] else "%s (%s)" % (c["name"], c["id"]), c["apex_m"], _f(c["potential"]), tr.get("direction"),
            _f(tr.get("slope_per_lap"), 3),
            ("; outliers laps %s" % tr["outlier_laps"]) if tr.get("outlier_laps") else ""))
        if tm:
            parts = []
            if tm.get("braking"):
                parts.append("brake %s m before apex from %s km/h, peak %s, release %s, trail %s m"
                             % (_f(-(tm.get("brake_m") or 0), 0), _f(tm.get("brake_speed"), 0),
                                _f(tm.get("brake_peak"), 2), tm.get("release_style"),
                                _f(tm.get("trail_m"), 0)))
            parts.append("min %s km/h" % _f(tm.get("min_speed"), 1))
            parts.append("throttle on %s m / full %s m after apex" % (
                _f(tm.get("throttle_on_m"), 0), _f(tm.get("full_throttle_m"), 0)))
            parts.append("coast %s m, exit %s km/h" % (_f(tm.get("coast_m"), 0),
                                                      _f(tm.get("exit_speed"), 1)))
            parts.append("balance entry/mid/exit %s/%s/%s" % (
                _f(tm.get("bal_entry"), 2), _f(tm.get("bal_mid"), 2), _f(tm.get("bal_exit"), 2)))
            L.append("- " + "; ".join(parts))
        for i in c.get("issues", []):
            L.append("- ISSUE: " + i["text"])
        fvs = c.get("fast_vs_slow")
        if fvs and fvs.get("insights"):
            L.append("- Fast laps %s vs slow %s (%s s): %s" % (
                fvs["fast_laps"], fvs["slow_laps"], _f(fvs["time_gap"]), " ".join(fvs["insights"])))
    L.append("")
    L.append("## Tyres (second half of last run)")
    ty = setup.get("tyres") or {}
    if ty:
        L.append("| wheel | hot bar | inner | mid | outer | in-out | carcass | brake max | wear |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for w, t in ty.items():
            L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                w, _f(t["pressure_hot"], 2), t["inner"], t["middle"], t["outer"],
                t.get("io_spread"), t["carcass"], t["brake_max"], t["wear"]))
    L.append("- Lockups this session: front %s, rear %s. Brake bias (front share): %s. Fuel/lap: %s L."
             % (setup.get("lockups", {}).get("front"), setup.get("lockups", {}).get("rear"),
                setup.get("brake_bias"), setup.get("fuel_per_lap")))
    L.append("")
    L.append("## Setup recommendations (ranked)")
    for r in setup.get("recommendations", [])[:6]:
        L.append("- [%s] %s -> **%s**. Why: %s Feel: %s" % (
            r["area"], r["observation"], r["change"], r["why"], r["feel"]))
    if res.get("run_comparison") and len(res["run_comparison"]) > 1:
        L.append("")
        L.append("## Runs")
        for r in res["run_comparison"]:
            L.append("- Run %s (%s laps): best %s, median %s%s%s" % (
                r["run"], r["laps"], fmt_time(r["best"]), fmt_time(r["median"]),
                (", delta median %+.3f s%s" % (r["median_delta"],
                 "" if r.get("significant") else " (within noise)"))
                if r.get("median_delta") is not None else "",
                (" - change: " + r["change"]) if r.get("change") else ""))
    L.append("")
    L.append("## Plan for the next run")
    plan = res.get("plan", {})
    for i, f in enumerate(plan.get("focus", []), 1):
        L.append("%d. %s (%s s, %s): %s" % (i, f["corner"], _f(f["potential_s"]), f["trend"],
                                           f["action"]))
    L.append("- ONE change: %s" % plan.get("one_change"))
    return "\n".join(L) + "\n"
