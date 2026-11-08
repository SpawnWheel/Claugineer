"""Turn a raw shared-memory snapshot into plain Python values.

Works for the real ctypes struct and for the simulator's namespace (same field names).
"""

WHEELS = ("FL", "FR", "RL", "RR")

# Per-sample channels written to every lap file (order = CSV column order).
SAMPLE_COLS = [
    "t", "d", "x", "z", "spd", "thr", "brk", "str", "clu", "gear", "rpm", "abs",
    "latg", "long", "yaw", "vx", "vz",
    "rps0", "rps1", "rps2", "rps3",
    "rh0", "rh1", "rh2", "rh3",
    "sv0", "sv1", "sv2", "sv3",
    "tt0", "tt1", "tt2", "tt3",
    "ter0", "ter1", "ter2", "ter3",
]

G = 9.81


def s(b):
    if hasattr(b, "_length_"):          # ctypes char array (e.g. mTyreCompound[0])
        b = bytes(b)
    if isinstance(b, (bytes, bytearray)):
        return bytes(b).split(b"\x00")[0].decode("utf-8", "replace").strip()
    return str(b)


def kelvin_to_c(v):
    v = float(v)
    return v - 273.15 if v > 200 else v


def player_index(d, name=""):
    n = max(0, min(int(d.mNumParticipants), 64))
    if name:
        name = name.lower()
        for i in range(n):
            p = d.mParticipantInfo[i]
            if p.mIsActive and name in s(p.mName).lower():
                return i
    v = int(d.mViewedParticipantIndex)
    return v if 0 <= v < max(n, 1) else 0


def sample(d, idx):
    """Return one telemetry sample (list matching SAMPLE_COLS)."""
    p = d.mParticipantInfo[idx]
    la = d.mLocalAcceleration
    lv = d.mLocalVelocity
    wp = p.mWorldPosition
    return [
        round(float(d.mCurrentTime), 4),
        round(float(p.mCurrentLapDistance), 2),
        round(float(wp[0]), 2), round(float(wp[2]), 2),
        round(float(d.mSpeed) * 3.6, 2),
        round(float(d.mUnfilteredThrottle), 3),
        round(float(d.mUnfilteredBrake), 3),
        round(float(d.mUnfilteredSteering), 3),
        round(float(d.mUnfilteredClutch), 3),
        int(d.mGear), int(d.mRpm),
        1 if d.mAntiLockActive else 0,
        round(float(la[0]) / G, 3), round(float(la[2]) / G, 3),
        round(float(d.mAngularVelocity[1]), 4),
        round(float(lv[0]), 3), round(float(lv[2]), 3),
        *[round(float(d.mTyreRPS[i]), 3) for i in range(4)],
        *[round(float(d.mRideHeight[i]) * 1000.0, 1) for i in range(4)],   # metres -> mm
        *[round(float(d.mSuspensionVelocity[i]), 4) for i in range(4)],
        *[round(float(d.mTyreTemp[i]), 1) for i in range(4)],
        *[int(d.mTerrain[i]) for i in range(4)],
    ]


def tyre_snapshot(d, pressure_unit="bar100"):
    """Tyre/brake state at one moment. inner/outer resolved from car-frame left/right."""
    out = {}
    for i, w in enumerate(WHEELS):
        left = float(d.mTyreTempLeft[i])
        right = float(d.mTyreTempRight[i])
        # Left-side wheels: inner edge is the car-frame RIGHT reading, and vice versa.
        inner, outer = (right, left) if i in (0, 2) else (left, right)
        pr = float(d.mAirPressure[i])
        if pressure_unit == "bar100":
            pr = pr / 100.0
        elif pressure_unit == "kpa":
            pr = pr / 100.0
        elif pressure_unit == "psi":
            pr = pr * 0.0689476
        out[w] = {
            "inner": round(inner, 1), "middle": round(float(d.mTyreTemp[i]), 1),
            "outer": round(outer, 1),
            "carcass": round(kelvin_to_c(d.mTyreCarcassTemp[i]), 1),
            "pressure": round(pr, 3),
            "wear": round(float(d.mTyreWear[i]), 4),
            "brake": round(float(d.mBrakeTempCelsius[i]), 1),
            "ride_mm": round(float(d.mRideHeight[i]) * 1000.0, 1),
        }
    return out


def front_bias(d):
    """Brake bias as FRONT share (0.62 = 62% front). Every source publishes mBrakeBias as the
    REAR share (AMS2 raw value; RaceRoom's brake_bias is also rear). None if not available."""
    v = float(d.mBrakeBias)
    return round(1.0 - v, 4) if 0.0 <= v <= 1.0 else None


def _r(v, n=1):
    """round() that passes None through (RaceRoom has no air/track temperature)."""
    return None if v is None else round(float(v), n)


def context(d):
    """Slow-changing session/car context."""
    return {
        "game": getattr(d, "_game", "ams2"),
        "track": s(d.mTrackLocation), "variation": s(d.mTrackVariation),
        "car": s(d.mCarName), "car_class": s(d.mCarClassName),
        "track_length": round(float(d.mTrackLength), 1),
        "session_state": int(d.mSessionState),
        "air_c": _r(d.mAmbientTemperature, 1),
        "track_c": _r(d.mTrackTemperature, 1),
        "rain": _r(d.mRainDensity, 2),
        "brake_bias": front_bias(d),
        "abs_setting": int(d.mAntiLockSetting),
        "tc_setting": int(d.mTractionControlSetting),
        "fuel_l": round(float(d.mFuelLevel) * float(d.mFuelCapacity), 2),
        "max_rpm": round(float(d.mMaxRPM)),
        "num_gears": int(d.mNumGears),
        "compound": s(d.mTyreCompound[0]),
    }
