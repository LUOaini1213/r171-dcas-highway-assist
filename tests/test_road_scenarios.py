"""Road geometry, scenario definitions and the two backends."""
import os

import pytest

from dcas import road as RD
from dcas.backends import EsminiBackend, PythonBackend
from dcas.closed_loop import run_case
from dcas.scenarios import SUITES, TGT_REAR, case_index, cutin_official_cases, cutout_cases, read_grid
from dcas.vehicle import EGO_FRONT

LIB = os.environ.get("ESMINI_LIB")


def test_sbend_clothoids_match_r171_table():
    """R171 Annex 4 4.2.4.1: A^2 / L equals the arc radius within 0.2 %.  REQ: R171-LAT-01"""
    (a1, l1), (a2, l2), (a3, l3), (a4, l4) = RD.SBEND_CLOTHOIDS
    r1, r2 = RD.SBEND_RADII_M
    for a, ln, r in ((a1, l1, r1), (a2, l2, r1), (a3, l3, r2), (a4, l4, r2)):
        assert a * a / ln == pytest.approx(r, rel=0.002)
    road = RD.sbend_r171()
    assert road.curvature(RD.SBEND_START_S + 31.0) == pytest.approx(1 / 787)
    assert road.curvature(RD.SBEND_START_S + 30 + 57.1 + 14 + 26 + 2.0) == pytest.approx(-1 / 374)


def _open_loop_ttc_end(case):
    """Replay the target with the Python backend and a constant-speed Ego; TTC when the lane change ends."""
    p = case.params
    be = PythonBackend()
    be.start(case.family, p, 0.02)
    v_e, s_e = float(p["EgoSpeed"]), float(p["EgoStartS"])
    t_end = float(p["LcStart"]) + float(p["LcTime"])
    t = 0.0
    while t < t_end - 1e-9:
        s_e += v_e * 0.02
        be.advance(0.02, s_e, 0.0, v_e)
        t += 0.02
    o = be.objects()[0]
    gap = (o.s + o.cx - o.length / 2) - (s_e + EGO_FRONT)
    return gap / (v_e - o.v)


def test_cutin_ttc_definition():
    """Grid TTC = TTC when the target has finished the lane change (R171 Annex 4 4.2.5.2.6.1.2).  REQ: R171-LON-01"""
    for c in cutin_official_cases():
        assert _open_loop_ttc_end(c) == pytest.approx(c.meta["ttc"], abs=0.03)


def test_cutout_ttc_definition():
    """Lead TTC to the stationary vehicle when the lead starts its lane change (4.2.5.2.5.1.2).  REQ: R171-LON-02"""
    c = next(c for c in cutout_cases() if c.case_id == "OFF-CO-R171")
    p = c.params
    lead_front = float(p["LeadStartS"]) + float(p["LeadSpeed"]) * float(p["CoStart"]) + 3.3
    stat_rear = float(p["StatS"]) + TGT_REAR
    assert (stat_rear - lead_front) / float(p["LeadSpeed"]) == pytest.approx(3.0)


def test_grid_files_hold_the_case_parameters():
    """The OpenSCENARIO grid files contain exactly the parameters of the cases.  REQ: R171-LON-01"""
    idx = case_index()
    for name in SUITES:
        _scen, sets = read_grid(name)
        for s in sets:
            assert dict(s) == {k: str(v) for k, v in idx[s["CaseId"]].params.items()}


@pytest.mark.skipif(not LIB, reason="set ESMINI_LIB to esminiLib.dll to run")
def test_esmini_equals_python_backend():
    """Same states; gap within 0.1 m and peak deceleration within 0.05 m/s2.  REQ: R171-LON-01"""
    idx = case_index()
    for cid in ("OFF-CI-R171-T2", "OFF-CO-R171", "OFF-LB-R171", "EG-06-unresponsive"):
        a = run_case(idx[cid], EsminiBackend(LIB))
        b = run_case(idx[cid], PythonBackend())
        assert a.states == b.states and a.collision == b.collision
        assert abs(a.min_gap_m - b.min_gap_m) < 0.1 and abs(a.peak_decel - b.peak_decel) < 0.05


@pytest.mark.skipif(not LIB, reason="set ESMINI_LIB to esminiLib.dll to run")
def test_esmini_road_curvature_equals_python_model():
    """esmini's lane-centre curvature (look-ahead mode 0) equals dcas/road.py k/(1 - k t).  REQ: R171-LAT-01"""
    import ctypes as C

    class RoadInfo(C.Structure):
        _fields_ = [(n, C.c_double) for n in ("gx", "gy", "gz", "lx", "ly", "lz", "angle", "rh", "rp", "rr", "th",
                                              "curvature", "speed_limit")] + \
                   [("roadId", C.c_uint32), ("junctionId", C.c_uint32), ("laneId", C.c_int), ("laneOffset", C.c_double),
                    ("s", C.c_double), ("t", C.c_double), ("road_type", C.c_int), ("road_rule", C.c_int),
                    ("lane_type", C.c_int), ("twa", C.c_double)]

    be = EsminiBackend(LIB)
    lib = be.lib
    lib.SE_GetRoadInfoAtDistance.argtypes = [C.c_int, C.c_double, C.POINTER(RoadInfo), C.c_int, C.c_bool]
    c = case_index()["OFF-CV-R171-BASE"]
    be.start(c.family, c.params, 0.02)
    ri = RoadInfo()
    road = RD.curve_road(374.0)
    worst = 0.0
    for s in range(560, 1300, 20):
        be.advance(0.02, float(s), 0.0, 20.0)
        lib.SE_GetRoadInfoAtDistance(be.ego, 0.0, C.byref(ri), 0, True)
        worst = max(worst, abs(ri.curvature - road.lane_curvature(be._state(be.ego).s, RD.lane_center_t(RD.EGO_LANE))))
    be.close()
    assert worst < 1e-6
