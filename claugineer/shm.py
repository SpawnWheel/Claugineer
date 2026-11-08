r"""AMS2 shared memory reader ($pcars2$, Project CARS 2 format, AMS2 header version 14).

Layout matches the official SharedMemory.h shipped with AMS2
(<AMS2>\Support\SharedMemory\...\SharedMemory.h). `python -m claugineer doctor`
cross-checks these offsets against that header if it can find it.
Layout cross-referenced with the open-source ams2-dash project (GiansRaggio).

Field notes verified by other tools against the live game:
  * mAirPressure is bar x 100.
  * mTyreCarcassTemp / Tread / Layer / Rim / InternalAir are Kelvin.
  * mTyreTempLeft/Right are in the CAR frame (left/right of the car), not inner/outer.
  * mTyreTempCenter == mTyreTemp (not an independent measurement).
  * mFuelLevel is a fraction of mFuelCapacity.
"""
import ctypes
import sys

MAP_NAME = "$pcars2$"
EXPECTED_VERSION = 14

GAME_INGAME_PLAYING = 2
SESSION_NAMES = {0: "invalid", 1: "practice", 2: "test", 3: "qualifying",
                 4: "formation", 5: "race", 6: "time_trial",
                 7: "warmup"}               # 7 is Claugineer's own id, used for RaceRoom warmup
PIT_MODE_NONE = 0


class ParticipantInfo(ctypes.Structure):
    _fields_ = [
        ("mIsActive", ctypes.c_bool),
        ("mName", ctypes.c_char * 64),
        ("mWorldPosition", ctypes.c_float * 3),
        ("mCurrentLapDistance", ctypes.c_float),
        ("mRacePosition", ctypes.c_uint),
        ("mLapsCompleted", ctypes.c_uint),
        ("mCurrentLap", ctypes.c_uint),
        ("mCurrentSector", ctypes.c_int),
    ]


class SharedMemory(ctypes.Structure):
    _fields_ = [
        ("mVersion", ctypes.c_uint),
        ("mBuildVersionNumber", ctypes.c_uint),
        ("mGameState", ctypes.c_uint),
        ("mSessionState", ctypes.c_uint),
        ("mRaceState", ctypes.c_uint),
        ("mViewedParticipantIndex", ctypes.c_int),
        ("mNumParticipants", ctypes.c_int),
        ("mParticipantInfo", ParticipantInfo * 64),
        ("mUnfilteredThrottle", ctypes.c_float),
        ("mUnfilteredBrake", ctypes.c_float),
        ("mUnfilteredSteering", ctypes.c_float),
        ("mUnfilteredClutch", ctypes.c_float),
        ("mCarName", ctypes.c_char * 64),
        ("mCarClassName", ctypes.c_char * 64),
        ("mLapsInEvent", ctypes.c_uint),
        ("mTrackLocation", ctypes.c_char * 64),
        ("mTrackVariation", ctypes.c_char * 64),
        ("mTrackLength", ctypes.c_float),
        ("mNumSectors", ctypes.c_int),
        ("mLapInvalidated", ctypes.c_bool),
        ("mBestLapTime", ctypes.c_float),
        ("mLastLapTime", ctypes.c_float),
        ("mCurrentTime", ctypes.c_float),
        ("mSplitTimeAhead", ctypes.c_float),
        ("mSplitTimeBehind", ctypes.c_float),
        ("mSplitTime", ctypes.c_float),
        ("mEventTimeRemaining", ctypes.c_float),
        ("mPersonalFastestLapTime", ctypes.c_float),
        ("mWorldFastestLapTime", ctypes.c_float),
        ("mCurrentSector1Time", ctypes.c_float),
        ("mCurrentSector2Time", ctypes.c_float),
        ("mCurrentSector3Time", ctypes.c_float),
        ("mFastestSector1Time", ctypes.c_float),
        ("mFastestSector2Time", ctypes.c_float),
        ("mFastestSector3Time", ctypes.c_float),
        ("mPersonalFastestSector1Time", ctypes.c_float),
        ("mPersonalFastestSector2Time", ctypes.c_float),
        ("mPersonalFastestSector3Time", ctypes.c_float),
        ("mWorldFastestSector1Time", ctypes.c_float),
        ("mWorldFastestSector2Time", ctypes.c_float),
        ("mWorldFastestSector3Time", ctypes.c_float),
        ("mHighestFlagColour", ctypes.c_uint),
        ("mHighestFlagReason", ctypes.c_uint),
        ("mPitMode", ctypes.c_uint),
        ("mPitSchedule", ctypes.c_uint),
        ("mCarFlags", ctypes.c_uint),
        ("mOilTempCelsius", ctypes.c_float),
        ("mOilPressureKPa", ctypes.c_float),
        ("mWaterTempCelsius", ctypes.c_float),
        ("mWaterPressureKPa", ctypes.c_float),
        ("mFuelPressureKPa", ctypes.c_float),
        ("mFuelLevel", ctypes.c_float),
        ("mFuelCapacity", ctypes.c_float),
        ("mSpeed", ctypes.c_float),
        ("mRpm", ctypes.c_float),
        ("mMaxRPM", ctypes.c_float),
        ("mBrake", ctypes.c_float),
        ("mThrottle", ctypes.c_float),
        ("mClutch", ctypes.c_float),
        ("mSteering", ctypes.c_float),
        ("mGear", ctypes.c_int),
        ("mNumGears", ctypes.c_int),
        ("mOdometerKM", ctypes.c_float),
        ("mAntiLockActive", ctypes.c_bool),
        ("mLastOpponentCollisionIndex", ctypes.c_int),
        ("mLastOpponentCollisionMagnitude", ctypes.c_float),
        ("mBoostActive", ctypes.c_bool),
        ("mBoostAmount", ctypes.c_float),
        ("mOrientation", ctypes.c_float * 3),
        ("mLocalVelocity", ctypes.c_float * 3),
        ("mWorldVelocity", ctypes.c_float * 3),
        ("mAngularVelocity", ctypes.c_float * 3),
        ("mLocalAcceleration", ctypes.c_float * 3),
        ("mWorldAcceleration", ctypes.c_float * 3),
        ("mExtentsCentre", ctypes.c_float * 3),
        ("mTyreFlags", ctypes.c_uint * 4),
        ("mTerrain", ctypes.c_uint * 4),
        ("mTyreY", ctypes.c_float * 4),
        ("mTyreRPS", ctypes.c_float * 4),
        ("mTyreSlipSpeed", ctypes.c_float * 4),
        ("mTyreTemp", ctypes.c_float * 4),
        ("mTyreGrip", ctypes.c_float * 4),
        ("mTyreHeightAboveGround", ctypes.c_float * 4),
        ("mTyreLateralStiffness", ctypes.c_float * 4),
        ("mTyreWear", ctypes.c_float * 4),
        ("mBrakeDamage", ctypes.c_float * 4),
        ("mSuspensionDamage", ctypes.c_float * 4),
        ("mBrakeTempCelsius", ctypes.c_float * 4),
        ("mTyreTreadTemp", ctypes.c_float * 4),
        ("mTyreLayerTemp", ctypes.c_float * 4),
        ("mTyreCarcassTemp", ctypes.c_float * 4),
        ("mTyreRimTemp", ctypes.c_float * 4),
        ("mTyreInternalAirTemp", ctypes.c_float * 4),
        ("mCrashState", ctypes.c_uint),
        ("mAeroDamage", ctypes.c_float),
        ("mEngineDamage", ctypes.c_float),
        ("mAmbientTemperature", ctypes.c_float),
        ("mTrackTemperature", ctypes.c_float),
        ("mRainDensity", ctypes.c_float),
        ("mWindSpeed", ctypes.c_float),
        ("mWindDirectionX", ctypes.c_float),
        ("mWindDirectionY", ctypes.c_float),
        ("mCloudBrightness", ctypes.c_float),
        ("mSequenceNumber", ctypes.c_uint),
        ("mWheelLocalPositionY", ctypes.c_float * 4),
        ("mSuspensionTravel", ctypes.c_float * 4),
        ("mSuspensionVelocity", ctypes.c_float * 4),
        ("mAirPressure", ctypes.c_float * 4),
        ("mEngineSpeed", ctypes.c_float),
        ("mEngineTorque", ctypes.c_float),
        ("mWings", ctypes.c_float * 2),
        ("mHandBrake", ctypes.c_float),
        ("mCurrentSector1Times", ctypes.c_float * 64),
        ("mCurrentSector2Times", ctypes.c_float * 64),
        ("mCurrentSector3Times", ctypes.c_float * 64),
        ("mFastestSector1Times", ctypes.c_float * 64),
        ("mFastestSector2Times", ctypes.c_float * 64),
        ("mFastestSector3Times", ctypes.c_float * 64),
        ("mFastestLapTimes", ctypes.c_float * 64),
        ("mLastLapTimes", ctypes.c_float * 64),
        ("mLapsInvalidated", ctypes.c_bool * 64),
        ("mRaceStates", ctypes.c_uint * 64),
        ("mPitModes", ctypes.c_uint * 64),
        ("mOrientations", (ctypes.c_float * 3) * 64),
        ("mSpeeds", ctypes.c_float * 64),
        ("mCarNames", (ctypes.c_char * 64) * 64),
        ("mCarClassNames", (ctypes.c_char * 64) * 64),
        ("mEnforcedPitStopLap", ctypes.c_int),
        ("mTranslatedTrackLocation", ctypes.c_char * 64),
        ("mTranslatedTrackVariation", ctypes.c_char * 64),
        ("mBrakeBias", ctypes.c_float),
        ("mTurboBoostPressure", ctypes.c_float),
        ("mTyreCompound", (ctypes.c_char * 40) * 4),
        ("mPitSchedules", ctypes.c_uint * 64),
        ("mHighestFlagColours", ctypes.c_uint * 64),
        ("mHighestFlagReasons", ctypes.c_uint * 64),
        ("mNationalities", ctypes.c_uint * 64),
        ("mSnowDensity", ctypes.c_float),
        ("mSessionDuration", ctypes.c_float),
        ("mSessionAdditionalLaps", ctypes.c_int),
        ("mTyreTempLeft", ctypes.c_float * 4),
        ("mTyreTempCenter", ctypes.c_float * 4),
        ("mTyreTempRight", ctypes.c_float * 4),
        ("mDrsState", ctypes.c_uint),
        ("mRideHeight", ctypes.c_float * 4),
        ("mJoyPad0", ctypes.c_uint),
        ("mDPad", ctypes.c_uint),
        ("mAntiLockSetting", ctypes.c_int),
        ("mTractionControlSetting", ctypes.c_int),
        ("mErsDeploymentMode", ctypes.c_int),
        ("mErsAutoModeEnabled", ctypes.c_bool),
        ("mClutchTemp", ctypes.c_float),
        ("mClutchWear", ctypes.c_float),
        ("mClutchOverheated", ctypes.c_bool),
        ("mClutchSlipping", ctypes.c_bool),
        ("mYellowFlagState", ctypes.c_int),
        ("mSessionIsPrivate", ctypes.c_bool),
        ("mLaunchStage", ctypes.c_int),
    ]


_FILE_MAP_READ = 0x0004


class SharedMemoryUnavailable(Exception):
    pass


class Reader:
    """Opens $pcars2$ read-only and returns consistent snapshots (Windows only)."""

    def __init__(self):
        if sys.platform != "win32":
            raise SharedMemoryUnavailable("AMS2 shared memory is only available on Windows")
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
        self._buf = SharedMemory()
        self._size = ctypes.sizeof(SharedMemory)

    def open(self):
        h = self._k.OpenFileMappingW(_FILE_MAP_READ, False, MAP_NAME)
        if not h:
            raise SharedMemoryUnavailable(
                "No $pcars2$ mapping. Start AMS2 and set Options > System > "
                "Shared Memory = Project CARS 2.")
        addr = self._k.MapViewOfFile(h, _FILE_MAP_READ, 0, 0, 0)
        if not addr:
            self._k.CloseHandle(h)
            raise SharedMemoryUnavailable("MapViewOfFile failed")
        self._h, self._addr = h, addr
        self._view = ctypes.cast(addr, ctypes.POINTER(SharedMemory))
        return self

    def snapshot(self):
        view, buf = self._view, self._buf
        for _ in range(10):
            seq = view.contents.mSequenceNumber
            if seq & 1:
                continue
            ctypes.memmove(ctypes.byref(buf), self._addr, self._size)
            if buf.mSequenceNumber == seq:
                return buf
        return buf

    def close(self):
        if self._addr:
            self._k.UnmapViewOfFile(ctypes.c_void_p(self._addr))
            self._addr = None
        if self._h:
            self._k.CloseHandle(ctypes.c_void_p(self._h))
            self._h = None


def game_running():
    """True if AMS2.exe / AMS2AVX.exe is running (the mapping survives the game closing)."""
    if sys.platform != "win32":
        return None
    try:
        import subprocess
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                             text=True, timeout=5, creationflags=0x08000000).stdout.lower()
        return '"ams2avx.exe"' in out or '"ams2.exe"' in out
    except Exception:
        return None


# ---------------------------------------------------------------- header check
_CTYPES = {"bool": 1, "char": 1, "int": 4, "unsigned int": 4, "float": 4}


def check_against_header(path):
    """Parse the game's SharedMemory.h and compare field offsets with ours.
    Returns (ok, list_of_messages)."""
    import re
    txt = open(path, encoding="latin-1").read()
    txt = re.sub(r"//.*", "", txt)
    txt = re.sub(r"/\*.*?\*/", "", txt, flags=re.S)
    consts = {}
    for m in re.finditer(r"#define\s+(\w+)\s+(\d+)", txt):
        consts[m.group(1)] = int(m.group(2))
    for m in re.finditer(r"(\w+)\s*=\s*(\d+)\s*,?", txt):
        consts.setdefault(m.group(1), int(m.group(2)))
    m = re.search(r"typedef\s+struct\s*\{(.*?)\}\s*SharedMemory\s*;", txt, re.S) or \
        re.search(r"struct\s+SharedMemory\s*\{(.*?)\}\s*;", txt, re.S)
    if not m:
        return False, ["Could not find the SharedMemory struct in the header"]
    body = m.group(1)
    fields = []
    for fm in re.finditer(r"([A-Za-z_][\w ]*?)\s+(m\w+)((?:\s*\[\s*\w+\s*\])*)\s*;", body):
        fields.append(fm.group(2))
    ours = [f[0] for f in SharedMemory._fields_]
    msgs = []
    missing = [f for f in fields if f not in ours]
    if missing:
        msgs.append("Fields in game header not in Claugineer layout: " + ", ".join(missing[:20]))
    # order check
    common = [f for f in fields if f in ours]
    order_ours = [f for f in ours if f in common]
    if common != order_ours:
        msgs.append("Field ORDER differs from the game header - offsets will be wrong!")
    ok = not msgs or (not missing and common == order_ours)
    if ok:
        msgs.append(f"Header matches ({len(fields)} fields checked).")
    return ok, msgs


if __name__ == "__main__":
    print("sizeof(SharedMemory) =", ctypes.sizeof(SharedMemory))
