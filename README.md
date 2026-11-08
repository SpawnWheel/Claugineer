# Claugineer – AMS2 / RaceRoom race engineer app

> New here? Start with **[SETUP.md](SETUP.md)** – install, first drive, and how to set Claude up as your race engineer.

Reads Automobilista 2's or RaceRoom's shared memory directly (same source Second Monitor uses), records every lap, and after each lap writes an analysis you can read in the dashboard and Claude can read as a file. No extra Python packages needed.

## Install (once)

1. Unzip or clone into a folder of your choice, e.g. **`C:\Claugineer`**. You'll connect that folder to Claude so it can read your data (see **SETUP.md**).
2. Double-click **`install.bat`**. It finds Python 3.9+ (or installs Python 3.12 via winget), creates a desktop shortcut and runs a connection check.
3. In AMS2: **Options → System → Shared Memory = Project CARS 2** (UDP not needed).
   RaceRoom needs no setting – its shared memory (`$R3E`) is always on.

Want to see it before driving? Run **`sim.bat`** – it generates 14 simulated laps and opens the dashboard.

## Every session

Double-click **Claugineer** on the desktop (or `run.bat`) before you go out. Leave the console window open. The dashboard opens at http://localhost:8770 – you don't need to look at it in VR; everything is analysed when you cross the line.

| File | What |
|---|---|
| `run.bat` | record + dashboard |
| `viewer.bat` | dashboard only (old sessions) |
| `analyze.bat` | rebuild the latest session and print the brief |
| `doctor.bat` | check shared memory / layout |
| `sim.bat` | simulated demo |

## Dashboard tabs

- **Live** – delta to your best lap, times, tyres (for a phone/second screen).
- **Session** – best, theoretical best (sectors and corner-by-corner), typical lap (median of last 5), trend, lap table with outliers greyed, plan for the next run.
- **Corners** – each corner ranked by time you're leaving vs your *own robust best* (15th percentile, not one lucky lap), its own trend line, typical brake point / trail / min speed / throttle pickup / coasting / balance, issues, and *"what you do differently on your fast laps vs slow laps"*. Rename corners here (e.g. T1 → Redgate).
- **Compare** – up to 4 laps from *any* session at this track in this car (first = reference). Zoomable, linked charts: drag across a chart to zoom, double-click to zoom out, corner buttons jump to a corner, hover shows every lap's values at that point plus a dot on the track map. The corner table shows time gained/lost per corner and brake point / min speed / throttle / exit speed side by side. The address bar keeps the selection, so a comparison can be bookmarked or shared (Claude can send you a link like `http://localhost:8770/#Compare&laps=<session>~22,<session>~17&z=T6`).
- **Driving line** (in Compare) – each lap's actual line drawn on a zoomed map of the corner (scroll to zoom the map), with ▲ turn-in, ○ apex (where you're closest to the inside) and ■ slowest point per lap, plus the "road you've used" on valid laps (the games don't publish track edges, so this stands in for them). A chart shows how many metres left/right of your best lap's line each lap is. The corner table and the Habits tab add turn-in point, apex point, metres off your tightest apex and exit line, and flag early/late apex, early turn-in and missed apex.
- **Notes for your engineer** – click anywhere on a chart or a track map and type what you felt ("understeering here"). Notes are saved in `data/notes.json`, show as purple pins, are added to `brief.md`, and Claude answers them in the next debrief (then marks them analysed). Remove one with ✕.
- **Habits** – every session at this track+car together: lap-time progression, your habits right now (coasting, on/off brake release, slow brake hit, lockups, late throttle, lifts, wheelspin, counter-steer, over-slowing and early braking vs your best lap) with how often and where, a habit map per corner, any corner's numbers lap by lap, and habit rates across every track and car you drive.
- **Technique** – per-lap trends for coasting, trail braking %, lockups, wheelspin, lifts, counter-steer.
- **Setup** – recommendations from the data (pressures, camber, brake bias, balance by phase, traction, gearing, ride height), tyre table, run-by-run comparison with noise estimate, setup sheet and change log.

## Why trends instead of single laps

Every comparison uses medians and robust statistics: typical = median of the last 5 clean laps; best = 15th percentile; trend = Theil-Sen slope (ignores outliers); outliers are laps more than 3 robust SDs from the median. A lucky lap no longer moves the target.

## Files (for Claude and for you)

```
data/latest_brief.md                    short engineer brief of the newest session
data/sessions/<session>/brief.md        same, per session
data/sessions/<session>/analysis.json   everything, machine-readable
data/sessions/<session>/session.json    lap list: times, sectors, tyres, bias, fuel
data/sessions/<session>/laps/L007.csv.gz  full 60 Hz trace of lap 7
data/tracks/<track>.json                corner map (names editable)
data/setups/<car>__<track>.json         your setup sheet + change log
config.json                             port, car pressure targets, thresholds
```

## Config

`config.json` is created on first run. Useful keys:
- `car_profiles` – hot-pressure targets per car or class (matched on car name, then class). Example: `"GT3": {"hot_pressure_bar": [1.80, 1.90]}` or per axle `{"front": [2.65, 2.75]}`.
- `host` – set to `"0.0.0.0"` to open the dashboard from a phone on your home Wi-Fi.
- `player_name` – your AMS2 name, needed only online (the viewed car follows the camera in multiplayer).
- `pressure_unit` – `bar100` (AMS2 default; leave it for RaceRoom too, its kPa values are converted to the same scale).
- `game` – `auto` (default: records whichever of AMS2 / RaceRoom is running, switches by itself), `ams2` or `r3e` to force one.

## RaceRoom

Same app, same files, same dashboard. Differences:
- RaceRoom sessions get ` [R3E]` added to the layout name (e.g. `donington-park-national-r3e`), so corner maps, setups and history never mix with AMS2 on the same track.
- No carcass temperature in RaceRoom: the `carcass` value is the average of the three tread temps.
- No air/track temperature in RaceRoom: `air_c` / `track_c` are empty.
- Ride height is real millimetres (AMS2's values are unscaled).
- `ter0-3` use RaceRoom surface codes: 1 tarmac, 2 grass, 3 dirt, 4 gravel, 5 kerb, 6 concrete.
- Brake bias: both games publish the REAR share; Claugineer stores and shows the FRONT share (AMS2 MINI raw 0.38 = 62% front). Laps recorded before this change are converted when read.
- The struct layout is generated from Sector3's official `r3e.h` (v3.6). `doctor.bat` checks it against the running game. If RaceRoom bumps the API version, regenerate with `python tools\gen_r3e.py r3e.h`.

## Known limits

- AMS2 doesn't publish setup values, so the Setup tab asks you to type them; advice then says "from → to".
- Inner/middle/outer tyre temps: AMS2's "middle" is the same number as the overall tyre temp, so pressure advice uses hot-pressure targets, not the centre-vs-edge rule.
- Corner detection is automatic from your best lap; it locks after 3 clean laps so numbering stays stable. Use "Re-detect corners" if it picked badly.
- Lockup/wheelspin detection calibrates wheel radius from your own straight-line data – first lap of a session is less reliable.
- Built and tested against simulated data. First real session: run `doctor.bat` with the car on track and check the numbers look sane.
