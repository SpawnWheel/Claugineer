# AMS2 / RaceRoom Race Engineer – Quick Reference

## Claugineer app – the data source
- Recorder/analyser reading AMS2 shared memory ($pcars2$, layout v14) and RaceRoom shared memory ($R3E, r3e.h v3.6). config.json `"game": "auto"` records whichever game is running. Launch: desktop shortcut / run.bat. Dashboard http://localhost:8770.
- Read first: `data/latest_brief.md` (laps, theoretical bests, per-corner potential + trend + issues + fast-vs-slow insights, tyres, setup recs, run comparison, next-run plan, open driver notes). Full detail: `data/sessions/<id>/analysis.json`. Raw 60 Hz laps: `data/sessions/<id>/laps/L###.csv.gz`.
- "Typical" = median of last 5 clean laps; "robust best" = 15th percentile; trend = Theil-Sen slope; outliers > 3 robust SD. Use these instead of single-lap comparisons.
- Balance index: steering per unit path curvature vs the car's own low-g reference (+ = understeer). Lockup = wheel slip < -18% for 3+ samples; wheelspin = driven wheel > +12%.
- Setup values aren't in shared memory: the driver types them into the Setup tab (data/setups/...), plus a change log per run → run comparison with a noise estimate.
- Pressure targets per car in config.json → car_profiles (GT3 1.80–1.90; MINI JCW front 2.65–2.75 hot – check the in-game car name matches).
- **Brake bias = FRONT share** in session.json / brief / advisor (lap field `brake_bias_basis: "front"`). Both games publish the REAR share raw; Claugineer converts it.
- A session = first lap driven → sim closed. Garage visits start a new *run* in the same session; a track/car/session-type change starts a new session. `data/recorder.log` gives the reason any session closed.
- Code changes need a Claugineer restart.

## Driver notes – CHECK EVERY DEBRIEF
- The driver clicks a chart or map in the dashboard and types what they felt. Stored in **`data/notes.json`** (id, created, track/variation/car, dist m, x/z, corner + from_apex_m, optional session/lap, text, status open|resolved, resolution). Open notes are also appended to brief.md under "## Driver notes".
- Workflow: each debrief, stage data/notes.json → analyse each open note for that combo at its distance (steering vs lat-g, speed, pedals, line) → answer it → set `status: "resolved"`, `resolution: "<one-line answer>"`, `resolved_at` and write the file back (the app may have added notes since – re-read first). The answer shows in green in the dashboard.

## Dashboard
- **Compare**: up to 4 laps from any session of the same track+car (first = reference). Zoomable linked charts, corner buttons, hover readout + track-map dot, corner table (Δ per corner, brake point, min speed, throttle on/flat, coast, max steer, exit speed, turn-in, apex, off-apex, exit line). Click a chart/map = add note.
- **Driving line** (Compare): zoomed corner map with each lap's line, ▲ turn-in, ○ geometric apex, ■ slowest point, grey "road used" envelope (valid laps). "Line vs best lap" chart: metres left(+)/right(−) of the best lap's line.
- Line metrics (claugineer/lines.py) are measured vs the combo's best valid lap (no track edges in shared memory). Flags vs median of the 3 fastest laps: early/late apex ±20 m, early turn-in 10 m, missed apex >1.5 m.
- **Shareable links** – send alongside chart PNGs so the driver can zoom:
  `http://localhost:8770/#Compare&laps=<sessionid>~<lap>,<sessionid>~<lap>&z=<cornerId e.g. T6>`
- **Habits**: notes list; lap-time progression across sessions; habit rates last 10 laps; habit × corner heat map; per-corner metric trends; habit rates across every track/car.
- Over-slowing/early-braking are relative to the best lap, so they jump after a setup change. A deliberate lift between apexes shows as "coast" – check before calling it a habit.
- API: /api/combo_laps?sid=, /api/traces?laps=sid~n,..., /api/habits_all, /api/combos, /api/notes?sid=, POST /api/note_add|note_delete|note_resolve.

## RaceRoom in Claugineer
- Sessions get " [R3E]" on the layout name (folder e.g. `..._donington-park-national-r3e__<car>__practice`) so maps/setups/history don't mix with AMS2.
- Same CSV columns. Differences: carcass = mean of the 3 tread temps; no air/track temp (null); ride height is real mm; ter0–3 = R3E surface codes (1 tarmac, 2 grass, 3 dirt, 4 gravel, 5 kerb, 6 concrete); session.json has `"game": "r3e"`.
- Tyre left/right = car frame; steering sign as AMS2; **yaw sign opposite to AMS2** (analysis self-calibrates).
- Invalid laps: R3E sets the current lap time to −1 when invalidated; the recorder keeps going on wall-clock time.
- RaceRoom hot pressures can read lower than the cold menu setting. The AMS2 GT3 1.80–1.90 target does not apply to R3E.

## Connection
- AMS2: Options → System → Use Shared Memory = Project CARS 2 (UDP not needed).
- RaceRoom: shared memory is always on, nothing to set.

## Session loop
Baseline run → measure vs reference lap (distance axis) → find 2–3 biggest delta losses → diagnose (brake point, brake shape, coasting, min speed, throttle pickup, steering, line) → change ONE thing (driving or setup) → re-run 3–5 laps and log.
Until laps are within ~0.5 s of each other, work on technique, not setup.

## Track learning stages
1. Orientation (5–10 laps, ~90% pace, build map) 2. Reference points (brake/turn-in/apex/exit markers) 3. Consistency (5 laps within ~0.5 s) 4. Optimisation (worst corners vs own best laps, then setup).

## Setup order
Tyres (pressure → middle temp, camber → in/out spread) → brakes → ride height/springs → ARBs → aero → diff → dampers → gearing.

## Key AMS2 facts
- GT3 hot pressure target 1.8–1.9 bar (Reiza staff). Tread ~85 °C; graining <~70 °C, blistering >~100 °C (community).
- Diff ramp angles 25–90°: HIGHER angle = LESS locking.
- Engine braking scale inverted: HIGHER number = LESS engine braking.
- Front ARB stiffer = more understeer; rear ARB stiffer = more oversteer.
- AMS2 shared memory: no camber, no DRS, no AI tyre compounds; AI telemetry only speed + lap time.
- Shared memory field notes: mAirPressure = bar×100; carcass/tread temps in Kelvin; mTyreTempLeft/Right are car-frame left/right, not inner/outer; mBrakeBias = REAR share (0.38 = 62/38 front/rear); mRideHeight unscaled.

## Driver preferences (edit to suit)
- Annotated chart images every debrief (dark background, laps cyan vs peach (+ green), yellow boxes on the corners discussed) plus a dashboard Compare link.
- Answer every open driver note, then mark it resolved.
- Never judge pace against AI times – own laps only.
- Only analyse when the driver says they're in the pits.
