"""World backends: move every vehicle except the Ego and keep the scenario clock.

EsminiBackend  esmini v3.10.2 via esminiLib (ctypes), as in P5.  esmini loads the family .xosc with the case
               parameters, runs the storyboard, and checks bounding-box collisions; the Ego is under the
               ExternalController and is reported every step with SE_ReportObjectRoadPos (lane -2, lane offset,
               s) and SE_ReportObjectSpeed.
PythonBackend  fallback / cross-check: reads the SAME parameter values and reproduces the storyboards with
               the esmini v3.10.2 semantics measured in a probe run (report.md 3.3):
                 - sinusoidal lane change: t = t0 + (t1 - t0) (1 - cos(pi x)) / 2, x = (time - start) / duration,
                   the first lateral motion in the step after the trigger time;
                 - during lateral motion the vehicle advances v cos(h) dt along s, h = atan(lateral step / (v dt))
                   of the previous step;
                 - linear speed change (braking): speed updated first, then s += v dt.
esmini cannot open non-ASCII absolute paths on this machine (the project path contains Chinese characters),
so it is started with scenarios/ as working directory and relative file names (same as P5).
"""
from __future__ import annotations

import ctypes as C
import math
import os

from .perception import ObjTruth
from .road import EGO_LANE, LANE_WIDTH_M, lane_center_t
from .scenarios import FAMILY_FILE, SCEN_DIR, declared_defaults, declared_types
from .xosc import TARGET_BB, EGO_BB


class _State(C.Structure):          # SE_ScenarioObjectState, esminiLib.hpp v3.10.2
    _fields_ = [("id", C.c_int), ("model_id", C.c_int), ("ctrl_type", C.c_int), ("timestamp", C.c_double),
                ("x", C.c_double), ("y", C.c_double), ("z", C.c_double),
                ("h", C.c_double), ("p", C.c_double), ("r", C.c_double),
                ("roadId", C.c_uint32), ("junctionId", C.c_uint32), ("t", C.c_double), ("laneId", C.c_int),
                ("laneOffset", C.c_double), ("s", C.c_double), ("speed", C.c_double),
                ("centerOffsetX", C.c_double), ("centerOffsetY", C.c_double), ("centerOffsetZ", C.c_double),
                ("width", C.c_double), ("length", C.c_double), ("height", C.c_double),
                ("objectType", C.c_int), ("objectCategory", C.c_int),
                ("wheel_angle", C.c_double), ("wheel_rot", C.c_double), ("visibilityMask", C.c_int)]


class EsminiBackend:
    name = "esmini"
    _lib = None

    def __init__(self, lib_path: str):
        if EsminiBackend._lib is None:
            lib = C.CDLL(lib_path)
            lib.SE_InitWithArgs.argtypes = [C.c_int, C.POINTER(C.c_char_p)]
            lib.SE_InitWithArgs.restype = C.c_int
            lib.SE_StepDT.argtypes = [C.c_double]
            lib.SE_StepDT.restype = C.c_int
            lib.SE_GetSimulationTime.restype = C.c_double
            lib.SE_GetIdByName.argtypes = [C.c_char_p]
            lib.SE_GetIdByName.restype = C.c_int
            lib.SE_GetNumberOfObjects.restype = C.c_int
            lib.SE_GetId.argtypes = [C.c_int]
            lib.SE_GetId.restype = C.c_int
            lib.SE_GetObjectName.argtypes = [C.c_int]
            lib.SE_GetObjectName.restype = C.c_char_p
            lib.SE_GetObjectState.argtypes = [C.c_int, C.POINTER(_State)]
            lib.SE_GetObjectState.restype = C.c_int
            lib.SE_ReportObjectRoadPos.argtypes = [C.c_int, C.c_uint32, C.c_int, C.c_double, C.c_double]
            lib.SE_ReportObjectRoadPos.restype = C.c_int
            lib.SE_ReportObjectSpeed.argtypes = [C.c_int, C.c_double]
            lib.SE_ReportObjectSpeed.restype = C.c_int
            lib.SE_SetParameterDouble.argtypes = [C.c_char_p, C.c_double]
            lib.SE_SetParameterDouble.restype = C.c_int
            lib.SE_SetParameterInt.argtypes = [C.c_char_p, C.c_int]
            lib.SE_SetParameterInt.restype = C.c_int
            lib.SE_SetParameterBool.argtypes = [C.c_char_p, C.c_bool]
            lib.SE_SetParameterBool.restype = C.c_int
            lib.SE_SetParameterString.argtypes = [C.c_char_p, C.c_char_p]
            lib.SE_SetParameterString.restype = C.c_int
            lib.SE_GetObjectNumberOfCollisions.argtypes = [C.c_int]
            lib.SE_GetObjectNumberOfCollisions.restype = C.c_int
            lib.SE_Close.restype = None
            EsminiBackend._cb_type = C.CFUNCTYPE(None, C.c_void_p)
            lib.SE_RegisterParameterDeclarationCallback.argtypes = [EsminiBackend._cb_type, C.c_void_p]
            lib.SE_SetOptionPersistent.argtypes = [C.c_char_p]
            lib.SE_SetOptionPersistent(b"disable_stdout")
            EsminiBackend._lib = lib
        self.lib = EsminiBackend._lib
        self._st = _State()
        self._cwd = None

    def start(self, family: str, params: dict, dt: float, log_stem: str | None = None) -> None:
        lib = self.lib
        scen = FAMILY_FILE[family]
        types = declared_types(scen)
        keep: list[bytes] = []

        def on_params(_):
            for k, v in params.items():
                kind = types.get(k)
                if kind is None:
                    raise ValueError(f"{k} is not declared in {scen}")
                if kind == "double":
                    rc = lib.SE_SetParameterDouble(k.encode(), float(v))
                elif kind == "int":
                    rc = lib.SE_SetParameterInt(k.encode(), int(v))
                elif kind == "string":
                    keep.append(str(v).encode())
                    rc = lib.SE_SetParameterString(k.encode(), keep[-1])
                elif kind == "boolean":
                    rc = lib.SE_SetParameterBool(k.encode(), str(v).lower() == "true")
                else:
                    raise ValueError(f"parameter type {kind} not handled")
                if rc != 0:
                    raise RuntimeError(f"esmini rejected parameter {k}={v}")
            lib.SE_SetParameterBool(b"ExtCtrl", True)

        self._cb = EsminiBackend._cb_type(on_params)
        lib.SE_RegisterParameterDeclarationCallback(self._cb, None)
        args = ["esmini", "--osc", scen, "--headless", "--fixed_timestep", f"{dt}", "--collision", "--disable_stdout"]
        if log_stem:
            os.makedirs(SCEN_DIR.parent / "results" / "esmini_logs", exist_ok=True)
            rel = f"../results/esmini_logs/{log_stem}"
            args += ["--csv_logger", f"{rel}.csv", "--logfile_path", f"{rel}.log.txt"]
        else:
            args += ["--disable_log"]
        self._cwd = os.getcwd()
        os.chdir(SCEN_DIR)
        argv = (C.c_char_p * len(args))(*[a.encode("ascii") for a in args])
        if lib.SE_InitWithArgs(len(args), argv) != 0:
            os.chdir(self._cwd)
            raise RuntimeError(f"esmini failed to load {scen} with {params.get('CaseId')}")
        self.ego = lib.SE_GetIdByName(b"Ego")
        e = self._state(self.ego)
        if e.ctrl_type != 1:
            raise RuntimeError("Ego is not under the ExternalController (ctrl_type != 1)")
        self.others = []
        for i in range(lib.SE_GetNumberOfObjects()):
            oid = lib.SE_GetId(i)
            if oid != self.ego:
                self.others.append((oid, lib.SE_GetObjectName(oid).decode()))
        self.collision = False

    def _state(self, oid: int) -> _State:
        self.lib.SE_GetObjectState(oid, C.byref(self._st))
        return _State.from_buffer_copy(self._st)

    def objects(self) -> list[ObjTruth]:
        out = []
        for oid, name in self.others:
            st = self._state(oid)
            out.append(ObjTruth(name, st.s, st.t, st.speed, st.length, st.width, st.centerOffsetX))
        return out

    def advance(self, dt: float, ego_s: float, ego_d: float, ego_v: float) -> None:
        self.lib.SE_ReportObjectRoadPos(self.ego, 1, EGO_LANE, ego_d, ego_s)
        self.lib.SE_ReportObjectSpeed(self.ego, ego_v)
        self.lib.SE_StepDT(dt)
        if not self.collision and self.lib.SE_GetObjectNumberOfCollisions(self.ego) > 0:
            self.collision = True

    def time(self) -> float:
        return self.lib.SE_GetSimulationTime()

    def close(self) -> None:
        self.lib.SE_Close()
        if self._cwd:
            os.chdir(self._cwd)
            self._cwd = None


class _PyEntity:
    def __init__(self, name: str, s: float, lane: int, v: float):
        self.name, self.s, self.v = name, s, v
        self.t = lane_center_t(lane)
        self.h = 0.0
        self.lat_events = []      # (start, duration, t_from(None = current at start), t_to)
        self.brake = None         # (start, rate)
        self.active_lat = None

    def step(self, time: float, dt: float) -> None:
        # longitudinal: braking (speed first), then s with the heading of the previous step
        if self.brake and time >= self.brake[0] - 1e-9:
            self.v = max(0.0, self.v - self.brake[1] * dt)
        self.s += self.v * math.cos(self.h) * dt
        # lateral
        t_old = self.t
        for ev in self.lat_events:
            start, dur, t_from, t_to = ev
            if time >= start - 1e-9 and (self.active_lat is None or self.active_lat[0] < start):
                self.active_lat = [start, dur, self.t if t_from is None else t_from, t_to]
        if self.active_lat is not None:
            start, dur, t_from, t_to = self.active_lat
            x = min(1.0, max(0.0, (time + dt - start) / dur))
            self.t = t_from + (t_to - t_from) * 0.5 * (1.0 - math.cos(math.pi * x))
        dlat = self.t - t_old
        self.h = math.atan2(dlat, self.v * dt) if (dlat != 0.0 and self.v > 0) else 0.0


class PythonBackend:
    """Same .xosc parameters, storyboards of dcas/xosc.py reproduced in Python (no esmini)."""
    name = "python"

    def start(self, family: str, params: dict, dt: float, log_stem: str | None = None) -> None:
        vals = {**declared_defaults(FAMILY_FILE[family]), **{k: str(v) for k, v in params.items()}}
        g = lambda k: float(vals[k])                                   # noqa: E731
        self.time_ = 0.0
        self.ents: list[_PyEntity] = []
        self.collision = False
        if family == "CutIn":
            e = _PyEntity("Target", g("TgtStartS"), int(vals["TgtLane"]), g("TgtSpeed"))
            e.lat_events.append((g("LcStart"), g("LcTime"), None, lane_center_t(EGO_LANE)))
            self.ents.append(e)
        elif family == "CutOut":
            e = _PyEntity("Lead", g("LeadStartS"), EGO_LANE, g("LeadSpeed"))
            e.lat_events.append((g("CoStart"), g("CoTime"), None, lane_center_t(-1)))
            self.ents += [e, _PyEntity("Stat", g("StatS"), EGO_LANE, 0.0)]
        elif family == "LeadBrake":
            e = _PyEntity("Lead", g("LeadStartS"), EGO_LANE, g("LeadSpeed"))
            e.brake = (g("DecelStart"), g("LeadDecel"))
            self.ents.append(e)
        elif family == "LatProbe":
            lane = int(vals["AdjLane"])
            e = _PyEntity("Adj", g("AdjStartS"), lane, g("AdjSpeed"))
            tc = lane_center_t(lane)
            # esmini: positive lane offset = to the left (towards the Ego lane when AdjLane = -3)
            e.lat_events.append((g("ProbeStart"), g("ProbeTime"), None, tc + g("ProbeOffset")))
            e.lat_events.append((g("ProbeBackStart"), g("ProbeTime"), None, tc))
            self.ents.append(e)
        elif family == "Highway":
            self.ents.append(_PyEntity("Lead", g("LeadStartS"), EGO_LANE, g("LeadSpeed")))
        # curve families: Ego only

    def objects(self) -> list[ObjTruth]:
        bb = TARGET_BB
        return [ObjTruth(e.name, e.s, e.t, e.v, bb["length"], bb["width"], bb["cx"]) for e in self.ents]

    def advance(self, dt: float, ego_s: float, ego_d: float, ego_v: float) -> None:
        for e in self.ents:
            e.step(self.time_, dt)
        self.time_ += dt

    def time(self) -> float:
        return self.time_

    def close(self) -> None:
        pass


def boxes_overlap(ego_s: float, ego_t: float, o: ObjTruth) -> bool:
    """Axis-aligned overlap in (s, t) of the Ego and an object (straight-road approximation, headings ignored)."""
    e0 = ego_s + EGO_BB["cx"] - EGO_BB["length"] / 2.0
    e1 = e0 + EGO_BB["length"]
    o0 = o.s + o.cx - o.length / 2.0
    o1 = o0 + o.length
    if e1 <= o0 or o1 <= e0:
        return False
    return abs(ego_t - o.t) < (EGO_BB["width"] + o.width) / 2.0


def make_backend(kind: str, esmini_lib: str | None):
    if kind == "esmini":
        if not esmini_lib:
            raise SystemExit("--esmini-lib <path to esminiLib.dll> is required for the esmini backend")
        return EsminiBackend(esmini_lib)
    return PythonBackend()


_ = LANE_WIDTH_M
