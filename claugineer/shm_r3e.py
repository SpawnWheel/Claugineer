r"""RaceRoom Racing Experience shared memory reader ($R3E) + translator to the AMS2 field names.

The struct layout below is GENERATED from the official r3e.h published by Sector3 Studios
(github.com/sector3studios/r3e-api, sample-c/src/r3e.h). Regenerate with tools\gen_r3e.py
when RaceRoom bumps the API version; don't edit the classes by hand.

Everything downstream (recorder, analysis, dashboard) reads AMS2 field names
(mSpeed, mCurrentLapDistance, ...). `translate()` builds an object with those names from
one R3E snapshot, converting units so the lap CSVs and session.json look the same as AMS2:

  AMS2 field              R3E source                         conversion
  mSpeed                  car_speed                          m/s (same)
  mRpm / mMaxRPM          engine_rps / max_engine_rps        rad/s -> rpm
  mAirPressure            tire_pressure                      kPa == bar x 100 (same as AMS2)
  mTyreTemp/Left/Right    tire_temp[].current_temp[1/0/2]    C, car-frame left/right
  mTyreCarcassTemp        (not in R3E)                       mean of the 3 tread temps
  mTyreWear               tire_wear                          R3E 1.0 = new -> 0.0 = new
  mRideHeight             player.ride_height                 metres (real metres, unlike AMS2)
  mBrakeBias              brake_bias                         rear share in both games (same)
  mTerrain                tire_on_mtrl                       R3E codes: 1 tarmac 2 grass 3 dirt
                                                             4 gravel 5 rumble 6 concrete
  mLapInvalidated         current_lap_valid / lap_valid_state
  mPitMode                in_pitlane / pit_state
  mAmbient/TrackTemp      (not in R3E)                       None
"""
import ctypes
import time
import math
import sys
from types import SimpleNamespace

# --- generated from r3e.h v3.6 (sector3studios/r3e-api, 2026-10-27) by tools/gen_r3e.py ---
R3E_VERSION_MAJOR = 3
R3E_VERSION_MINOR = 6
MAP_NAME = '$R3E'


class r3e_vec3_f32(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
        ("z", ctypes.c_float),
    ]


class r3e_vec3_f64(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("x", ctypes.c_double),
        ("y", ctypes.c_double),
        ("z", ctypes.c_double),
    ]


class r3e_ori_f32(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("pitch", ctypes.c_float),
        ("yaw", ctypes.c_float),
        ("roll", ctypes.c_float),
    ]


class r3e_sectorStarts(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("sector1", ctypes.c_float),
        ("sector2", ctypes.c_float),
        ("sector3", ctypes.c_float),
    ]


class r3e_playerdata(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("user_id", ctypes.c_int32),
        ("game_simulation_ticks", ctypes.c_int32),
        ("game_simulation_time", ctypes.c_double),
        ("position", r3e_vec3_f64),
        ("velocity", r3e_vec3_f64),
        ("local_velocity", r3e_vec3_f64),
        ("acceleration", r3e_vec3_f64),
        ("local_acceleration", r3e_vec3_f64),
        ("orientation", r3e_vec3_f64),
        ("rotation", r3e_vec3_f64),
        ("angular_acceleration", r3e_vec3_f64),
        ("angular_velocity", r3e_vec3_f64),
        ("local_angular_velocity", r3e_vec3_f64),
        ("local_g_force", r3e_vec3_f64),
        ("steering_force", ctypes.c_double),
        ("steering_force_percentage", ctypes.c_double),
        ("engine_torque", ctypes.c_double),
        ("current_downforce", ctypes.c_double),
        ("voltage", ctypes.c_double),
        ("ers_level", ctypes.c_double),
        ("power_mgu_h", ctypes.c_double),
        ("power_mgu_k", ctypes.c_double),
        ("torque_mgu_k", ctypes.c_double),
        ("suspension_deflection", (ctypes.c_double * 4)),
        ("suspension_velocity", (ctypes.c_double * 4)),
        ("camber", (ctypes.c_double * 4)),
        ("ride_height", (ctypes.c_double * 4)),
        ("front_wing_height", ctypes.c_double),
        ("front_roll_angle", ctypes.c_double),
        ("rear_roll_angle", ctypes.c_double),
        ("third_spring_suspension_deflection_front", ctypes.c_double),
        ("third_spring_suspension_velocity_front", ctypes.c_double),
        ("third_spring_suspension_deflection_rear", ctypes.c_double),
        ("third_spring_suspension_velocity_rear", ctypes.c_double),
        ("unused1", ctypes.c_double),
        ("unused2", ctypes.c_double),
        ("unused3", ctypes.c_double),
    ]


class r3e_flags(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("yellow", ctypes.c_int32),
        ("yellowCausedIt", ctypes.c_int32),
        ("yellowOvertake", ctypes.c_int32),
        ("yellowPositionsGained", ctypes.c_int32),
        ("sector_yellow", (ctypes.c_int32 * 3)),
        ("closest_yellow_distance_into_track", ctypes.c_float),
        ("blue", ctypes.c_int32),
        ("black", ctypes.c_int32),
        ("green", ctypes.c_int32),
        ("checkered", ctypes.c_int32),
        ("white", ctypes.c_int32),
        ("black_and_white", ctypes.c_int32),
    ]


class r3e_car_damage(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("engine", ctypes.c_float),
        ("transmission", ctypes.c_float),
        ("aerodynamics", ctypes.c_float),
        ("suspension", ctypes.c_float),
        ("unused1", ctypes.c_float),
        ("unused2", ctypes.c_float),
    ]


class r3e_cut_track_penalties(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("drive_through", ctypes.c_float),
        ("stop_and_go", ctypes.c_float),
        ("pit_stop", ctypes.c_float),
        ("time_deduction", ctypes.c_float),
        ("slow_down", ctypes.c_float),
    ]


class r3e_drs(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("equipped", ctypes.c_int32),
        ("available", ctypes.c_int32),
        ("numActivationsLeft", ctypes.c_int32),
        ("engaged", ctypes.c_int32),
    ]


class r3e_push_to_pass(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("available", ctypes.c_int32),
        ("engaged", ctypes.c_int32),
        ("amount_left", ctypes.c_int32),
        ("engaged_time_left", ctypes.c_float),
        ("wait_time_left", ctypes.c_float),
    ]


class r3e_tire_temp(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("current_temp", (ctypes.c_float * 3)),
        ("optimal_temp", ctypes.c_float),
        ("cold_temp", ctypes.c_float),
        ("hot_temp", ctypes.c_float),
    ]


class r3e_brake_temp(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("current_temp", ctypes.c_float),
        ("optimal_temp", ctypes.c_float),
        ("cold_temp", ctypes.c_float),
        ("hot_temp", ctypes.c_float),
    ]


class r3e_aid_settings(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("abs", ctypes.c_int32),
        ("tc", ctypes.c_int32),
        ("esp", ctypes.c_int32),
        ("countersteer", ctypes.c_int32),
        ("cornering", ctypes.c_int32),
    ]


class r3e_driver_info(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("name", (ctypes.c_uint8 * 64)),
        ("car_number", ctypes.c_int32),
        ("class_id", ctypes.c_int32),
        ("model_id", ctypes.c_int32),
        ("team_id", ctypes.c_int32),
        ("livery_id", ctypes.c_int32),
        ("manufacturer_id", ctypes.c_int32),
        ("user_id", ctypes.c_int32),
        ("slot_id", ctypes.c_int32),
        ("class_performance_index", ctypes.c_int32),
        ("engine_type", ctypes.c_int32),
        ("car_width", ctypes.c_float),
        ("car_length", ctypes.c_float),
        ("rating", ctypes.c_float),
        ("reputation", ctypes.c_float),
        ("unused1", ctypes.c_float),
        ("unused2", ctypes.c_float),
    ]


class r3e_driver_data(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("driver_info", r3e_driver_info),
        ("finish_status", ctypes.c_int32),
        ("place", ctypes.c_int32),
        ("place_class", ctypes.c_int32),
        ("lap_distance", ctypes.c_float),
        ("lap_distance_fraction", ctypes.c_float),
        ("position", r3e_vec3_f32),
        ("track_sector", ctypes.c_int32),
        ("completed_laps", ctypes.c_int32),
        ("current_lap_valid", ctypes.c_int32),
        ("lap_time_current_self", ctypes.c_float),
        ("sector_time_current_self", (ctypes.c_float * 3)),
        ("sector_time_previous_self", (ctypes.c_float * 3)),
        ("sector_time_best_self", (ctypes.c_float * 3)),
        ("time_delta_front", ctypes.c_float),
        ("time_delta_behind", ctypes.c_float),
        ("pitstop_status", ctypes.c_int32),
        ("in_pitlane", ctypes.c_int32),
        ("num_pitstops", ctypes.c_int32),
        ("penalties", r3e_cut_track_penalties),
        ("car_speed", ctypes.c_float),
        ("tire_type_front", ctypes.c_int32),
        ("tire_type_rear", ctypes.c_int32),
        ("tire_subtype_front", ctypes.c_int32),
        ("tire_subtype_rear", ctypes.c_int32),
        ("base_penalty_weight", ctypes.c_float),
        ("aid_penalty_weight", ctypes.c_float),
        ("drs_state", ctypes.c_int32),
        ("ptp_state", ctypes.c_int32),
        ("virtual_energy", ctypes.c_float),
        ("penaltyType", ctypes.c_int32),
        ("penaltyReason", ctypes.c_int32),
        ("engineState", ctypes.c_int32),
        ("orientation", r3e_vec3_f32),
        ("start_group", ctypes.c_int32),
        ("start_phase", ctypes.c_int32),
        ("formation_slot", ctypes.c_int32),
    ]


class r3e_shared(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("version_major", ctypes.c_int32),
        ("version_minor", ctypes.c_int32),
        ("all_drivers_offset", ctypes.c_int32),
        ("driver_data_size", ctypes.c_int32),
        ("game_mode", ctypes.c_int32),
        ("game_paused", ctypes.c_int32),
        ("game_in_menus", ctypes.c_int32),
        ("game_in_replay", ctypes.c_int32),
        ("game_using_vr", ctypes.c_int32),
        ("game_player_in_garage", ctypes.c_int32),
        ("player", r3e_playerdata),
        ("track_name", (ctypes.c_uint8 * 64)),
        ("layout_name", (ctypes.c_uint8 * 64)),
        ("track_id", ctypes.c_int32),
        ("layout_id", ctypes.c_int32),
        ("layout_length", ctypes.c_float),
        ("sector_start_factors", r3e_sectorStarts),
        ("race_session_laps", (ctypes.c_int32 * 3)),
        ("race_session_minutes", (ctypes.c_int32 * 3)),
        ("event_index", ctypes.c_int32),
        ("session_type", ctypes.c_int32),
        ("session_iteration", ctypes.c_int32),
        ("session_length_format", ctypes.c_int32),
        ("session_pit_speed_limit", ctypes.c_float),
        ("session_phase", ctypes.c_int32),
        ("start_lights", ctypes.c_int32),
        ("tire_wear_active", ctypes.c_int32),
        ("fuel_use_active", ctypes.c_int32),
        ("number_of_laps", ctypes.c_int32),
        ("session_time_duration", ctypes.c_float),
        ("session_time_remaining", ctypes.c_float),
        ("max_incident_points", ctypes.c_int32),
        ("start_mode", ctypes.c_int32),
        ("start_group_count", ctypes.c_int32),
        ("pit_window_status", ctypes.c_int32),
        ("pit_window_start", ctypes.c_int32),
        ("pit_window_end", ctypes.c_int32),
        ("in_pitlane", ctypes.c_int32),
        ("pit_menu_selection", ctypes.c_int32),
        ("pit_menu_state", (ctypes.c_int32 * 12)),
        ("pit_state", ctypes.c_int32),
        ("pit_total_duration", ctypes.c_float),
        ("pit_elapsed_time", ctypes.c_float),
        ("pit_action", ctypes.c_int32),
        ("num_pitstops", ctypes.c_int32),
        ("pit_min_duration_total", ctypes.c_float),
        ("pit_min_duration_left", ctypes.c_float),
        ("flags", r3e_flags),
        ("position", ctypes.c_int32),
        ("position_class", ctypes.c_int32),
        ("finish_status", ctypes.c_int32),
        ("cut_track_warnings", ctypes.c_int32),
        ("penalties", r3e_cut_track_penalties),
        ("num_penalties", ctypes.c_int32),
        ("completed_laps", ctypes.c_int32),
        ("current_lap_valid", ctypes.c_int32),
        ("track_sector", ctypes.c_int32),
        ("lap_distance", ctypes.c_float),
        ("lap_distance_fraction", ctypes.c_float),
        ("lap_time_best_leader", ctypes.c_float),
        ("lap_time_best_leader_class", ctypes.c_float),
        ("session_best_lap_sector_times", (ctypes.c_float * 3)),
        ("lap_time_best_self", ctypes.c_float),
        ("sector_time_best_self", (ctypes.c_float * 3)),
        ("lap_time_previous_self", ctypes.c_float),
        ("sector_time_previous_self", (ctypes.c_float * 3)),
        ("lap_time_current_self", ctypes.c_float),
        ("sector_time_current_self", (ctypes.c_float * 3)),
        ("lap_time_delta_leader", ctypes.c_float),
        ("lap_time_delta_leader_class", ctypes.c_float),
        ("time_delta_front", ctypes.c_float),
        ("time_delta_behind", ctypes.c_float),
        ("time_delta_best_self", ctypes.c_float),
        ("best_individual_sector_time_self", (ctypes.c_float * 3)),
        ("best_individual_sector_time_leader", (ctypes.c_float * 3)),
        ("best_individual_sector_time_leader_class", (ctypes.c_float * 3)),
        ("incident_points", ctypes.c_int32),
        ("lap_valid_state", ctypes.c_int32),
        ("prev_lap_valid", ctypes.c_int32),
        ("discharge_rate", ctypes.c_float),
        ("brake_regen", ctypes.c_float),
        ("unused1", ctypes.c_float),
        ("vehicle_info", r3e_driver_info),
        ("player_name", (ctypes.c_uint8 * 64)),
        ("control_type", ctypes.c_int32),
        ("car_speed", ctypes.c_float),
        ("engine_rps", ctypes.c_float),
        ("max_engine_rps", ctypes.c_float),
        ("upshift_rps", ctypes.c_float),
        ("gear", ctypes.c_int32),
        ("num_gears", ctypes.c_int32),
        ("car_cg_location", r3e_vec3_f32),
        ("car_orientation", r3e_ori_f32),
        ("local_acceleration", r3e_vec3_f32),
        ("total_mass", ctypes.c_float),
        ("fuel_left", ctypes.c_float),
        ("fuel_capacity", ctypes.c_float),
        ("fuel_per_lap", ctypes.c_float),
        ("virtual_energy_left", ctypes.c_float),
        ("virtual_energy_capacity", ctypes.c_float),
        ("virtual_energy_per_lap", ctypes.c_float),
        ("engine_temp", ctypes.c_float),
        ("engine_oil_temp", ctypes.c_float),
        ("fuel_pressure", ctypes.c_float),
        ("engine_oil_pressure", ctypes.c_float),
        ("turbo_pressure", ctypes.c_float),
        ("throttle", ctypes.c_float),
        ("throttle_raw", ctypes.c_float),
        ("brake", ctypes.c_float),
        ("brake_raw", ctypes.c_float),
        ("clutch", ctypes.c_float),
        ("clutch_raw", ctypes.c_float),
        ("steer_input_raw", ctypes.c_float),
        ("steer_lock_degrees", ctypes.c_int32),
        ("steer_wheel_range_degrees", ctypes.c_int32),
        ("aid_settings", r3e_aid_settings),
        ("drs", r3e_drs),
        ("pit_limiter", ctypes.c_int32),
        ("push_to_pass", r3e_push_to_pass),
        ("brake_bias", ctypes.c_float),
        ("drs_numActivationsTotal", ctypes.c_int32),
        ("ptp_numActivationsTotal", ctypes.c_int32),
        ("battery_soc", ctypes.c_float),
        ("water_left", ctypes.c_float),
        ("abs_setting", ctypes.c_int32),
        ("headlights", ctypes.c_int32),
        ("steer_wheel_max_rotation", ctypes.c_int32),
        ("tire_type", ctypes.c_int32),
        ("tire_rps", (ctypes.c_float * 4)),
        ("tire_speed", (ctypes.c_float * 4)),
        ("tire_grip", (ctypes.c_float * 4)),
        ("tire_wear", (ctypes.c_float * 4)),
        ("tire_flatspot", (ctypes.c_int32 * 4)),
        ("tire_pressure", (ctypes.c_float * 4)),
        ("tire_dirt", (ctypes.c_float * 4)),
        ("tire_temp", (r3e_tire_temp * 4)),
        ("tire_type_front", ctypes.c_int32),
        ("tire_type_rear", ctypes.c_int32),
        ("tire_subtype_front", ctypes.c_int32),
        ("tire_subtype_rear", ctypes.c_int32),
        ("brake_temp", (r3e_brake_temp * 4)),
        ("brake_pressure", (ctypes.c_float * 4)),
        ("traction_control_setting", ctypes.c_int32),
        ("engine_map_setting", ctypes.c_int32),
        ("engine_brake_setting", ctypes.c_int32),
        ("traction_control_percent", ctypes.c_float),
        ("tire_on_mtrl", (ctypes.c_int32 * 4)),
        ("tire_load", (ctypes.c_float * 4)),
        ("car_damage", r3e_car_damage),
        ("num_cars", ctypes.c_int32),
        ("all_drivers_data_1", (r3e_driver_data * 128)),
        ("formation_speed_limit", ctypes.c_float),
        ("formation_pace_floor", ctypes.c_float),
        ("start_corridor_lap_distance", ctypes.c_float),
        ("formation_side", ctypes.c_int32),
        ("formation_follow_slot_id", ctypes.c_int32),
        ("pitlane_start_delay_remaining", ctypes.c_float),
        ("start_penalty_pending", ctypes.c_int32),
    ]

# --- end generated ---


# ======================================================================= reader
_FILE_MAP_READ = 0x0004
EXPECTED_ALL_DRIVERS_OFFSET = r3e_shared.num_cars.offset
EXPECTED_DRIVER_DATA_SIZE = ctypes.sizeof(r3e_driver_data)

# AMS2-style session ids (see shm.SESSION_NAMES)
_SESSION_MAP = {0: 1, 1: 3, 2: 5, 3: 7}       # practice, qualifying, race, warmup
_SUBTYPE = {0: b"Primary", 1: b"Alternate", 2: b"Soft", 3: b"Medium", 4: b"Hard"}
_TYPE = {0: b"Option", 1: b"Prime"}
RPS_TO_RPM = 60.0 / (2.0 * math.pi)


class SharedMemoryUnavailable(Exception):
    pass


class Reader:
    """Opens $R3E read-only and returns translated snapshots (Windows only)."""

    game = "r3e"

    def __init__(self):
        if sys.platform != "win32":
            raise SharedMemoryUnavailable("RaceRoom shared memory is only available on Windows")
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenFileMappingW.restype = ctypes.c_void_p
        k.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        k.MapViewOfFile.restype = ctypes.c_void_p
        k.MapViewOfFile.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                    wintypes.DWORD, ctypes.c_size_t]
        k.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        self._k = k
        self._h = None
        self._addr = None
        self._buf = r3e_shared()
        self._size = ctypes.sizeof(r3e_shared)
        self.warnings = []

    def open(self):
        h = self._k.OpenFileMappingW(_FILE_MAP_READ, False, MAP_NAME)
        if not h:
            raise SharedMemoryUnavailable("No $R3E mapping. Start RaceRoom (shared memory is "
                                          "always on) and load into a session.")
        addr = self._k.MapViewOfFile(h, _FILE_MAP_READ, 0, 0, 0)
        if not addr:
            self._k.CloseHandle(h)
            raise SharedMemoryUnavailable("MapViewOfFile failed for $R3E")
        self._h, self._addr = h, addr
        return self

    def raw(self):
        """Raw r3e_shared copy (no translation)."""
        ctypes.memmove(ctypes.byref(self._buf), self._addr, self._size)
        return self._buf

    def snapshot(self):
        return translate(self.raw(), self)

    def close(self):
        if self._addr:
            self._k.UnmapViewOfFile(ctypes.c_void_p(self._addr))
            self._addr = None
        if self._h:
            self._k.CloseHandle(ctypes.c_void_p(self._h))
            self._h = None


def layout_check(r):
    """Compare what the live game reports with our generated layout. Returns list of problems."""
    probs = []
    if r.version_major and r.version_major != R3E_VERSION_MAJOR:
        probs.append("game API major version %d, Claugineer built for %d - layout will be wrong"
                     % (r.version_major, R3E_VERSION_MAJOR))
    if r.all_drivers_offset and r.all_drivers_offset != EXPECTED_ALL_DRIVERS_OFFSET:
        probs.append("all_drivers_offset %d, expected %d - fields before the driver list moved"
                     % (r.all_drivers_offset, EXPECTED_ALL_DRIVERS_OFFSET))
    if r.driver_data_size and r.driver_data_size != EXPECTED_DRIVER_DATA_SIZE:
        probs.append("driver_data_size %d, expected %d" % (r.driver_data_size,
                                                           EXPECTED_DRIVER_DATA_SIZE))
    return probs


def game_running():
    """True if RaceRoom (RRRE64.exe / RRRE.exe) is running, None if unknown."""
    if sys.platform != "win32":
        return None
    try:
        import subprocess
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                             text=True, timeout=5, creationflags=0x08000000).stdout.lower()
        return '"rrre64.exe"' in out or '"rrre.exe"' in out
    except Exception:
        return None


# ================================================================== translation
def _txt(arr):
    return bytes(arr).split(b"\x00")[0]


def _pos(v, default=0.0):
    v = float(v)
    return v if v >= 0 else default


def _game_state(r):
    """AMS2 mGameState: 1 = menus, 2 = driving, 3 = paused/garage."""
    if r.version_major == 0 or r.game_in_menus == 1 or r.game_in_replay == 1:
        return 1
    if r.game_paused == 1 or r.game_player_in_garage == 1:
        return 3
    if r.control_type not in (0, -1):          # AI / remote / replay driving the car
        return 3
    return 2


def _compound(r):
    out = []
    for sub, typ in ((r.tire_subtype_front, r.tire_type_front),
                     (r.tire_subtype_front, r.tire_type_front),
                     (r.tire_subtype_rear, r.tire_type_rear),
                     (r.tire_subtype_rear, r.tire_type_rear)):
        out.append(_SUBTYPE.get(sub) or _TYPE.get(typ) or b"")
    return out


def _lap_clock(r, lap, reader):
    """Current lap time that keeps running after R3E invalidates the lap.

    R3E sets lap_time_current_self to -1 once a lap is invalidated (track limits);
    the recorder only stores samples while the time is >= 0, so invalid laps were
    cut off at the moment of the cut. Rebuild the time from the simulation clock.
    """
    cur = float(r.lap_time_current_self)
    if reader is None:
        return cur
    # wall clock: game_simulation_time did not work on real R3E data (2026-11-06)
    sim = time.perf_counter()
    st = getattr(reader, "_lapclock", None)
    if st is None or st[0] != lap or sim < st[2]:
        st = [lap, (sim - cur) if cur >= 0 else None, sim]
    if cur >= 0:
        st[1] = sim - cur
    elif st[1] is not None:
        cur = sim - st[1]
    st[2] = sim
    reader._lapclock = st
    return cur


def translate(r, reader=None):
    """One r3e_shared snapshot -> object with the AMS2 field names Claugineer uses."""
    if reader is not None and not reader.warnings and r.version_major:
        reader.warnings = layout_check(r) or ["ok"]
    p = r.player
    tt = r.tire_temp
    left = [float(tt[i].current_temp[0]) for i in range(4)]
    mid = [float(tt[i].current_temp[1]) for i in range(4)]
    right = [float(tt[i].current_temp[2]) for i in range(4)]
    cap = float(r.fuel_capacity)
    fuel = _pos(r.fuel_left)
    bias = float(r.brake_bias)
    in_pit = r.in_pitlane == 1 or r.pit_state in (2, 3, 4)
    invalid = r.current_lap_valid == 0 or r.lap_valid_state in (1, 2)
    lap = int(r.completed_laps) + 1 if r.completed_laps >= 0 else 0
    pos = (float(p.position.x), float(p.position.y), float(p.position.z))
    gear = int(r.gear)
    cur_time = _lap_clock(r, lap, reader)

    part = SimpleNamespace(
        mIsActive=True, mName=_txt(r.player_name), mWorldPosition=pos,
        mCurrentLapDistance=float(r.lap_distance), mRacePosition=int(r.position),
        mLapsCompleted=max(int(r.completed_laps), 0), mCurrentLap=lap,
        mCurrentSector=int(r.track_sector))
    return SimpleNamespace(
        _game="r3e",
        mVersion=int(r.version_major), mGameState=_game_state(r),
        mSessionState=_SESSION_MAP.get(int(r.session_type), 0),
        mViewedParticipantIndex=0, mNumParticipants=1, mParticipantInfo=[part],
        mTrackLocation=_txt(r.track_name),
        # tag the layout so RaceRoom sessions, corner maps and setups never mix with AMS2 ones
        mTrackVariation=_txt(r.layout_name) + b" [R3E]",
        mCarName=_txt(r.vehicle_info.name),
        mCarClassName=("class %d" % r.vehicle_info.class_id).encode(),
        mTrackLength=float(r.layout_length),
        mCurrentTime=cur_time,
        mLastLapTime=float(r.lap_time_previous_self),
        mBestLapTime=float(r.lap_time_best_self),
        mLapInvalidated=bool(invalid),
        mPitMode=1 if in_pit else 0,
        mUnfilteredThrottle=_pos(r.throttle_raw), mUnfilteredBrake=_pos(r.brake_raw),
        mUnfilteredSteering=float(r.steer_input_raw), mUnfilteredClutch=_pos(r.clutch_raw),
        mSpeed=float(r.car_speed),
        mGear=gear if gear >= -1 else 0, mNumGears=max(int(r.num_gears), 0),
        mRpm=_pos(r.engine_rps) * RPS_TO_RPM, mMaxRPM=_pos(r.max_engine_rps) * RPS_TO_RPM,
        mAntiLockActive=r.aid_settings.abs == 5,
        # R3E local frame is +X left, +Y up, +Z back - same as AMS2
        mLocalAcceleration=(p.local_acceleration.x, p.local_acceleration.y,
                            p.local_acceleration.z),
        mLocalVelocity=(p.local_velocity.x, p.local_velocity.y, p.local_velocity.z),
        mAngularVelocity=(p.local_angular_velocity.x, p.local_angular_velocity.y,
                          p.local_angular_velocity.z),
        mTyreRPS=[float(r.tire_rps[i]) for i in range(4)],
        mRideHeight=[float(p.ride_height[i]) for i in range(4)],
        mSuspensionVelocity=[float(p.suspension_velocity[i]) for i in range(4)],
        mTerrain=[int(r.tire_on_mtrl[i]) for i in range(4)],
        mTyreTemp=mid, mTyreTempLeft=left, mTyreTempRight=right,
        mTyreCarcassTemp=[(left[i] + mid[i] + right[i]) / 3.0 for i in range(4)],
        mAirPressure=[float(r.tire_pressure[i]) for i in range(4)],
        mTyreWear=[1.0 - float(r.tire_wear[i]) if r.tire_wear[i] >= 0 else 0.0
                   for i in range(4)],
        mBrakeTempCelsius=[float(r.brake_temp[i].current_temp) for i in range(4)],
        mFuelLevel=fuel / cap if cap > 0 else 0.0, mFuelCapacity=cap if cap > 0 else 0.0,
        mAmbientTemperature=None, mTrackTemperature=None, mRainDensity=0.0,
        mBrakeBias=bias,                   # rear share, same as AMS2 (frames converts to front)
        mAntiLockSetting=int(r.abs_setting),
        mTractionControlSetting=int(r.traction_control_setting),
        mTyreCompound=_compound(r),
        # extras (not used by AMS2 code, handy for the brief / debugging)
        r3eFuelPerLap=float(r.fuel_per_lap),
        r3eSessionTimeRemaining=float(r.session_time_remaining),
        r3eFuelUseMultiplier=int(r.fuel_use_active),
        r3eTireWearMultiplier=int(r.tire_wear_active),
        r3eSectorTimesPrevious=[float(x) for x in r.sector_time_previous_self],
    )


if __name__ == "__main__":
    print("sizeof(r3e_shared) =", ctypes.sizeof(r3e_shared),
          " num_cars offset =", EXPECTED_ALL_DRIVERS_OFFSET)
