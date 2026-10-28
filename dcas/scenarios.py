"""Test cases: OpenSCENARIO parameters of every case, the grid files, and the case meta data on the DCAS side.

A Case = (case_id, family, OpenSCENARIO parameter values, meta).  The parameter values are written to
scenarios/<suite>_grid.xosc (ParameterValueDistribution) and read back by BOTH backends, so esmini and the
Python fallback run exactly the same cases.  'meta' holds harness inputs that are not OpenSCENARIO content:
grid coordinates, the DCAS settings (time-gap index, curve adaptation on/off), the scripted driver, injected
boundaries / failures.

Definitions (see dcas/regulations.py for the clauses):
  cut-in TTC   R171 Annex 4 4.2.5.2.6.1.2 / Euro NCAP VA 2.1.4: TTC (longitudinal bumper distance / relative
               speed) at the instant the target has finished its lane change, with both vehicles at their
               initial speeds (open-loop).  Lateral speed in the grid = mean lateral speed 3.5 m / LcTime.
  cut-out TTC  R171 4.2.5.2.5.1.2 / Euro NCAP VA 2.1.5: TTC of the lead to the stationary vehicle when the lead
               starts its lane change.
"""
from __future__ import annotations

import itertools
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from . import regulations as R
from .driver import DriverScript
from .road import LANE_WIDTH_M, lane_center_t
from .vehicle import EGO_FRONT
from vendor.p7_dms import labels as L

ROOT = Path(__file__).resolve().parents[1]
SCEN_DIR = ROOT / "scenarios"
TGT_REAR = 1.3 - 4.0 / 2.0          # target rear bumper relative to its reference point (-0.7 m)
TGT_FRONT = 1.3 + 4.0 / 2.0         # 3.3 m

FAMILY_FILE = {"CutIn": "CutIn.xosc", "CutOut": "CutOut.xosc", "LeadBrake": "LeadBrake.xosc",
               "LatProbe": "LatProbe.xosc", "Highway": "Highway.xosc", "Curve_R250": "Curve_R250.xosc",
               "Curve_R374": "Curve_R374.xosc", "Curve_R500": "Curve_R500.xosc", "SBend": "SBend.xosc"}
CURVE_ROAD = {"Curve_R250": "curve_R250", "Curve_R374": "curve_R374", "Curve_R500": "curve_R500",
              "SBend": "sbend_r171"}

# ---- project choices for the scenario set-up (not regulatory values) ----
EGO_START_S = 100.0
PRE_ROLL_S = 4.0            # steady driving before the manoeuvre (R171 Annex 4 asks for >= 2 s)
G_START_MIN_M = 5.0         # a cut-in must start with the target at least 5 m ahead of the Ego front
LC_T_REG_S = 2.0 * math.sqrt(LANE_WIDTH_M / 1.5)   # 3.055 s: two-arc lane change at 1.5 m/s2 (R171 cut-out/cut-in type 2)

# ---- the cut-in grid (TTC x lateral speed x relative speed), VUT 120 km/h (R171 type 2 base speed) ----
CUTIN_VUT_KPH = 120.0
CUTIN_TTC_S = (-1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0)
CUTIN_VLAT_MPS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
CUTIN_DV_KPH = (10.0, 20.0, 30.0, 40.0, 50.0, 60.0)


@dataclass(frozen=True)
class Case:
    case_id: str
    family: str
    params: dict
    meta: dict = field(default_factory=dict, hash=False, compare=False)


def _f(x: float) -> str:
    return f"{x:.6f}"


# =============================================================== cut-in
def lane_change_s_loss(v: float, lc_time_s: float, width: float = LANE_WIDTH_M, dt: float = 0.02) -> float:
    """Longitudinal distance a target loses during a sinusoidal lane change because esmini moves it v cos(h) dt
    (same discrete semantics as dcas/backends.py); added to the start gap so that the TTC definition holds."""
    loss, h, y_prev, t = 0.0, 0.0, 0.0, 0.0
    while t < lc_time_s - 1e-9:
        loss += v * (1.0 - math.cos(h)) * dt
        t += dt
        y = width * 0.5 * (1.0 - math.cos(math.pi * min(1.0, t / lc_time_s)))
        h = math.atan2(y - y_prev, v * dt) if v > 0 else 0.0
        y_prev = y
    return loss + v * (1.0 - math.cos(h)) * dt


def cutin_params(v_vut_kph: float, v_gvt_kph: float, ttc_end_s: float, lc_time_s: float, tgt_lane: int = -3):
    v_e, v_t = v_vut_kph / 3.6, v_gvt_kph / 3.6
    dv = v_e - v_t
    t_end = PRE_ROLL_S + lc_time_s
    gap_end = ttc_end_s * dv
    loss = lane_change_s_loss(v_t, lc_time_s)
    gap0 = gap_end + dv * t_end + loss
    g_start = gap_end + dv * lc_time_s + loss
    p = {"EgoSpeed": _f(v_e), "EgoStartS": _f(EGO_START_S), "TgtSpeed": _f(v_t),
         "TgtStartS": _f(EGO_START_S + EGO_FRONT + gap0 - TGT_REAR), "TgtLane": str(tgt_lane),
         "LcStart": _f(PRE_ROLL_S), "LcTime": _f(lc_time_s), "SimEndTime": _f(t_end + 9.0)}
    return p, g_start


def cutin_case(ttc: float, vlat: float, dvk: float, v_vut_kph: float = CUTIN_VUT_KPH, prefix: str = "CI") -> Case:
    lc = LANE_WIDTH_M / vlat
    p, g_start = cutin_params(v_vut_kph, v_vut_kph - dvk, ttc, lc)
    cid = f"{prefix}-dv{int(dvk)}-vl{vlat:g}-ttc{ttc:+.2f}"
    p["CaseId"] = cid
    return Case(cid, "CutIn", p, dict(ttc=ttc, vlat=vlat, dv_kph=dvk, v_vut_kph=v_vut_kph, g_start=g_start,
                                      valid=g_start >= G_START_MIN_M))


def cutin_grid_cases(include_invalid: bool = False) -> list[Case]:
    """TTC x lateral speed x relative speed.  Combinations where the target would start its lane change less
    than G_START_MIN_M ahead of the Ego front (it would cut in beside the Ego) are left out of the grid file and
    listed separately (results/cutin_invalid.csv)."""
    out = [cutin_case(ttc, vlat, dvk) for ttc, vlat, dvk in itertools.product(CUTIN_TTC_S, CUTIN_VLAT_MPS, CUTIN_DV_KPH)]
    return out if include_invalid else [c for c in out if c.meta["valid"]]


def cutin_official_cases() -> list[Case]:
    defs = [("OFF-CI-R171-T1", R.R171_CUTIN_T1, "R171 Annex 4 4.2.5.2.6.1 Type 1"),
            ("OFF-CI-R171-T2", R.R171_CUTIN_T2, "R171 Annex 4 4.2.5.2.6.1 Type 2"),
            ("OFF-CI-NCAPVA-1", R.ENCAP_VA_CUTIN[0], "Euro NCAP VA 2.1.4 TTC 0.0"),
            ("OFF-CI-NCAPVA-2", R.ENCAP_VA_CUTIN[1], "Euro NCAP VA 2.1.4 TTC 1.5"),
            ("OFF-CI-NCAPAD-1", dict(R.ENCAP_AD_CUTIN[0], lc_len_m=14.5), "Euro NCAP AD 4.3.1 TTC -1.5"),
            ("OFF-CI-NCAPAD-2", dict(R.ENCAP_AD_CUTIN[1], lc_len_m=60.0), "Euro NCAP AD 4.3.1 TTC 0.5")]
    out = []
    for cid, d, label in defs:
        lc = d["lc_len_m"] / (d["v_gvt_kph"] / 3.6)
        p, g_start = cutin_params(d["v_vut_kph"], d["v_gvt_kph"], d["ttc_s"], lc)
        p["CaseId"] = cid
        out.append(Case(cid, "CutIn", p, dict(ttc=d["ttc_s"], vlat=LANE_WIDTH_M / lc, dv_kph=d["v_vut_kph"] - d["v_gvt_kph"],
                                              v_vut_kph=d["v_vut_kph"], g_start=g_start, valid=True, label=label,
                                              official=True, gap_idx=0)))
    return out


# =============================================================== cut-out
def cutout_case(cid: str, v_set_kph: float, v_lead_kph: float, ttc_s: float, gap_idx: int, lc_len_m: float | None,
                label: str = "", official: bool = False) -> Case:
    from .params import BASELINE
    v_l = v_lead_kph / 3.6
    tau = BASELINE.gap_settings_s[gap_idx]
    gap0 = BASELINE.d0_m + tau * v_l
    lead_s0 = EGO_START_S + EGO_FRONT + gap0 - TGT_REAR
    co_time = lc_len_m / v_l if lc_len_m else LC_T_REG_S
    stat_s = lead_s0 + v_l * PRE_ROLL_S + TGT_FRONT + ttc_s * v_l - TGT_REAR
    p = {"CaseId": cid, "EgoSpeed": _f(v_l), "EgoStartS": _f(EGO_START_S), "LeadSpeed": _f(v_l),
         "LeadStartS": _f(lead_s0), "StatS": _f(stat_s), "CoStart": _f(PRE_ROLL_S), "CoTime": _f(co_time),
         "SimEndTime": _f(PRE_ROLL_S + co_time + 12.0)}
    return Case(cid, "CutOut", p, dict(v_set_kph=v_set_kph, v_lead_kph=v_lead_kph, ttc=ttc_s, gap_idx=gap_idx,
                                       label=label, official=official))


def cutout_cases() -> list[Case]:
    out = [cutout_case("OFF-CO-R171", 70, 50, 3.0, 0, 44.0, "R171 Annex 4 4.2.5.2.5.1", True),
           cutout_case("OFF-CO-NCAPVA-1", 70, 50, 3.0, 0, 44.0, "Euro NCAP VA 2.1.5 70/50", True),
           cutout_case("OFF-CO-NCAPVA-2", 90, 70, 3.0, 0, 60.0, "Euro NCAP VA 2.1.5 90/70", True),
           cutout_case("OFF-CO-NCAPAD-1", 70, 50, 2.0, 0, 44.0, "Euro NCAP AD 4.3.1 70/50 TTC 2.0", True),
           cutout_case("OFF-CO-NCAPAD-2", 90, 70, 2.0, 0, 60.0, "Euro NCAP AD 4.3.1 90/70 TTC 2.0", True)]
    for (vs, vl), ttc, gi in itertools.product(((70, 50), (90, 70), (120, 100)), (1.5, 2.0, 2.5, 3.0, 3.5), (0, 2)):
        out.append(cutout_case(f"CO-{vs}-{vl}-ttc{ttc:.1f}-g{gi}", vs, vl, ttc, gi, None))
    return out


# =============================================================== decelerating lead
def leadbrake_case(cid: str, v_kph: float, v_set_kph: float, decel: float, gap_idx: int, label: str = "",
                   official: bool = False) -> Case:
    from .params import BASELINE
    v = v_kph / 3.6
    gap0 = BASELINE.d0_m + BASELINE.gap_settings_s[gap_idx] * v
    p = {"CaseId": cid, "EgoSpeed": _f(v), "EgoStartS": _f(EGO_START_S), "LeadSpeed": _f(v),
         "LeadStartS": _f(EGO_START_S + EGO_FRONT + gap0 - TGT_REAR), "LeadDecel": _f(decel),
         "DecelStart": _f(PRE_ROLL_S), "SimEndTime": _f(PRE_ROLL_S + v / decel + 8.0)}
    return Case(cid, "LeadBrake", p, dict(v_kph=v_kph, v_set_kph=v_set_kph, decel=decel, gap_idx=gap_idx,
                                          label=label, official=official))


def leadbrake_cases() -> list[Case]:
    out = [leadbrake_case("OFF-LB-R171", 50, 60, 4.0, 2, "R171 Annex 4 4.2.5.2.4.1 (default gap)", True),
           leadbrake_case("OFF-LB-NCAPVA", 50, 55, 4.0, 0, "Euro NCAP VA 2.1.3 CCRb 55/50 (closest gap)", True)]
    for v, d, gi in itertools.product((50, 80, 100, 120), (2.0, 4.0, 6.0, 8.0), (0, 2)):
        out.append(leadbrake_case(f"LB-v{v}-d{d:g}-g{gi}", v, v + 10, d, gi))
    return out


# =============================================================== non-threatening lateral approach (false braking)
PROBE_OFFSETS_M = (0.4, 0.6, 0.8, 1.0)
PROBE_TIMES_S = (1.0, 2.0)
PROBE_GAPS_M = (10.0, 20.0, 35.0)
PROBE_DV_KPH = (10.0, 30.0)
PROBE_HOLD_S = 1.0


def latprobe_cases() -> list[Case]:
    out = []
    v_e = CUTIN_VUT_KPH / 3.6
    for off, pt, gap, dvk in itertools.product(PROBE_OFFSETS_M, PROBE_TIMES_S, PROBE_GAPS_M, PROBE_DV_KPH):
        v_a = v_e - dvk / 3.6
        gap0 = gap + (v_e - v_a) * PRE_ROLL_S         # gap at ProbeStart = 'gap' with constant speeds
        cid = f"LP-off{off:g}-t{pt:g}-g{int(gap)}-dv{int(dvk)}"
        p = {"CaseId": cid, "EgoSpeed": _f(v_e), "EgoStartS": _f(EGO_START_S), "AdjSpeed": _f(v_a),
             "AdjStartS": _f(EGO_START_S + EGO_FRONT + gap0 - TGT_REAR), "AdjLane": "-3",
             "ProbeOffset": _f(off), "ProbeStart": _f(PRE_ROLL_S), "ProbeTime": _f(pt),
             "ProbeBackStart": _f(PRE_ROLL_S + pt + PROBE_HOLD_S), "SimEndTime": _f(PRE_ROLL_S + 2 * pt + PROBE_HOLD_S + 6.0)}
        out.append(Case(cid, "LatProbe", p, dict(offset=off, probe_time=pt, gap=gap, dv_kph=dvk,
                                                 max_intrusion=off - (LANE_WIDTH_M / 2 - 0.9) - 0.0)))
    return out


# =============================================================== curves (lane centring)
CURVE_SPEEDS_KPH = (80.0, 90.0, 100.0, 110.0, 120.0, 130.0)


def curve_cases() -> list[Case]:
    from .params import BASELINE
    from .road import all_roads, EGO_LANE
    out = []
    roads = all_roads()
    t_lane = lane_center_t(EGO_LANE)
    # R171 Annex 4 4.2.5.1.1.1.1: required a_y 80-90 % of the declared max, constant speed, on R374 (2nd S-bend turn radius)
    r_lane = 1.0 / roads["curve_R374"].lane_curvature(1000.0, t_lane)
    v_base = math.sqrt(0.85 * BASELINE.ay_declared * r_lane) * 3.6
    v_prov = math.sqrt((BASELINE.ay_declared + R.R171_POS_PROVOKE_AY_MARGIN + 0.3) * r_lane) * 3.6
    for fam in ("Curve_R250", "Curve_R374", "Curve_R500", "SBend"):
        for v, csa in itertools.product(CURVE_SPEEDS_KPH, (True, False)):
            cid = f"CV-{fam[6:] if fam != 'SBend' else 'Sbend'}-v{int(v)}-{'csa' if csa else 'nocsa'}"
            out.append(_curve_case(cid, fam, v, csa))
    out.append(_curve_case("OFF-CV-R171-BASE", "Curve_R374", round(v_base, 3), False,
                           "R171 Annex 4 4.2.5.1.1.1.1 (85 % of declared a_y, constant speed)", True))
    out.append(_curve_case("OFF-CV-R171-PROVOKE", "Curve_R374", round(v_prov, 3), True,
                           "R171 Annex 4 4.2.5.1.1.1.2 (> declared + 0.3 m/s2)", True))
    out.append(_curve_case("OFF-CV-R171-PROVOKE-nocsa", "Curve_R374", round(v_prov, 3), False,
                           "4.2.5.1.1.1.2 without curve-speed adaptation", True))
    return out


def _curve_case(cid, fam, v_kph, csa, label="", official=False) -> Case:
    road = CURVE_ROAD[fam]
    from .road import all_roads, EGO_LANE
    rd = all_roads()[road]
    v = v_kph / 3.6
    s_end = min(rd.length - 50.0, 1650.0 if fam != "SBend" else 1500.0)
    k_max = max(abs(rd.lane_curvature(x, lane_center_t(EGO_LANE))) for x in range(300, int(s_end), 2))
    p = {"CaseId": cid, "EgoSpeed": _f(v), "EgoStartS": _f(300.0), "SimEndTime": _f((s_end - 300.0) / v)}
    return Case(cid, fam, p, dict(v_kph=v_kph, csa=csa, road=road, label=label, official=official,
                                  ay_need=round(v * v * k_max, 4)))


# =============================================================== driver engagement timelines (Highway)
def _hw_params(cid: str, v_kph: float = 120.0, lead_gap: float | None = None, t_end: float = 40.0) -> dict:
    v = v_kph / 3.6
    lead_s = EGO_START_S + 1500.0 if lead_gap is None else EGO_START_S + EGO_FRONT + lead_gap - TGT_REAR
    return {"CaseId": cid, "EgoSpeed": _f(v), "EgoStartS": _f(EGO_START_S), "LeadSpeed": _f(v),
            "LeadStartS": _f(lead_s), "SimEndTime": _f(t_end)}


def engagement_cases() -> list[Case]:
    P = L.PHONE
    defs = [
        ("EG-01-attentive", DriverScript(gaze=[(5 + 8 * i, 5.8 + 8 * i, L.MIRROR) for i in range(4)]), 40,
         "mirror glances 0.8 s: relevant area, no request expected"),
        ("EG-02-instrument-4s", DriverScript(gaze=[(10, 14, L.INSTRUMENT)]), 25,
         "4 s on the instrument panel: not relevant under R171 5.5.4.2.5.2 -> EOR"),
        ("EG-03-phone-4s", DriverScript(gaze=[(10, 14, P)]), 25, "single 4 s phone glance -> EOR, confirmed on return"),
        ("EG-04-vats", DriverScript(gaze=[(10 + 3 * i, 12.4 + 3 * i, P) for i in range(8)], respond_to="EOR", reaction_s=0.8), 45,
         "2.4 s glances every 3 s (VATS) -> immediate EOR before any single glance reaches 3.3 s"),
        ("EG-05-redisengage", DriverScript(gaze=[(10, 13.6, P), (14.2, 16.0, P)], respond_to=None), 30,
         "EOR, re-engaged 0.6 s, away again 1.8 s -> immediate EOR (5.5.4.2.6.2.2)"),
        ("EG-06-unresponsive", DriverScript(gaze=[(10, 80, P)], respond_to=None), 60,
         "phone 70 s, ignores all warnings -> EOR -> escalation -> DCA -> risk-mitigation stop"),
        ("EG-07-responds-DCA", DriverScript(gaze=[(10, 80, P)], respond_to="DCA", reaction_s=1.2), 40,
         "ignores EOR and escalation, takes over 1.2 s after the DCA"),
        ("EG-08-hands-off-eyes-on", DriverScript(hands_off=[(10, 80)], respond_to=None), 60,
         "hands off, eyes on road: HOR delayed to 8 s, escalation, DCA, unavailability"),
        ("EG-09-hands-off-eyes-off", DriverScript(hands_off=[(10, 80)], gaze=[(10, 80, L.OFF_ROAD)], respond_to=None), 50,
         "hands off and looking away: the EOR chain dominates"),
        ("EG-10-sleep", DriverScript(eyes_closed=[(10, 70)], respond_to=None), 50,
         "eyes closed: microsleep 1.2 s, sleep 3 s -> DCA, unresponsive 6 s -> risk-mitigation stop (Euro NCAP AD 4.2.3)"),
        ("EG-11-microsleep", DriverScript(eyes_closed=[(10, 11.6)]), 30,
         "1.6 s eye closure: microsleep warning + time gap +0.6 s (Euro NCAP AD 4.2.1)"),
        ("EG-12-three-escalations", DriverScript(gaze=[(10, 18, P), (40, 48, P), (70, 78, P), (100, 104, P)], respond_to="EOR_ESC", reaction_s=0.5,
                                                 set_at=(0.0, 30.0, 60.0, 90.0, 110.0)), 120,
         "three escalations within 30 min -> lock-out (R171 5.5.4.2.8.2 (c)), re-activation refused"),
        ("EG-13-dsm-blocked", DriverScript(camera_blocked=[(10, 30)], set_at=(0.0, 20.0)), 40,
         "camera blocked 20 s: DCA and stand-by (Euro NCAP AD <= 10 s), activation refused while blocked"),
    ]
    out = []
    for cid, script, t_end, label in defs:
        lead_gap = 60.0 if cid in ("EG-06-unresponsive",) else None
        out.append(Case(cid, "Highway", _hw_params(cid, 120.0, lead_gap, t_end), dict(script=script, label=label)))
    return out


def functional_cases() -> list[Case]:
    defs = [
        ("FN-01-accel-override", DriverScript(accel=[(10, 13, 1.2)]), 30, dict(steady_kph=100.0, v_set_kph=120.0),
         "steady following at 100 km/h, accelerator override 3 s, release -> resume (R171 5.5.3.4.1.3)"),
        ("FN-02-brake-cancel", DriverScript(brake=[(10, 11, 2.0)]), 25, dict(lead_gap=None),
         "driver brakes 1 s -> stand-by, no automatic resume (R171 5.5.3.4.1.1)"),
        ("FN-03-steer-override", DriverScript(steer=[(10, 12, 4.0)]), 25, dict(lead_gap=None),
         "steering torque 4 N.m for 2 s -> lateral override, release -> active (R171 5.5.3.4.1.4)"),
        ("FN-04-markings-lost", DriverScript(respond_to="DCA", reaction_s=1.0), 30, dict(lead_gap=None, markings_lost=(10.0, 30.0)),
         "lane markings lost -> stand-by request (DCA), driver takes over (R171 5.3.5.1)"),
        ("FN-05-markings-lost-noresponse", DriverScript(respond_to=None), 45, dict(lead_gap=None, markings_lost=(10.0, 45.0)),
         "lane markings lost, no takeover -> risk-mitigation stop after 8 s"),
        ("FN-06-seatbelt", DriverScript(seatbelt_off=[(0, 5), (12, 40)], set_at=(1.0, 6.0, 20.0)), 30, dict(lead_gap=None),
         "activation refused without seat belt; unfastened while active -> DCA (R171 5.5.3.2.3 (a))"),
        ("FN-07-failure", DriverScript(), 25, dict(lead_gap=None, failure_at=10.0),
         "system failure -> off + failure warning (R171 5.4.2.1)"),
        ("FN-08-main-switch-off", DriverScript(main_switch_off_at=10.0), 20, dict(lead_gap=None),
         "main switch off -> off at any time (R171 5.5.3.3.1)"),
        ("FN-09-follow-steady", DriverScript(), 40, dict(steady_kph=100.0, v_set_kph=120.0),
         "steady following at 100 km/h with the default 1.8 s gap (R171 5.3.7.5.1.1)"),
    ]
    from .params import BASELINE
    out = []
    for cid, script, t_end, extra, label in defs:
        if "steady_kph" in extra:                  # start in steady following at the default time gap
            v = extra["steady_kph"]
            p = _hw_params(cid, v, BASELINE.d0_m + BASELINE.gap_settings_s[BASELINE.gap_default_idx] * v / 3.6, t_end)
        else:
            p = _hw_params(cid, 120.0, extra.get("lead_gap"), t_end)
        out.append(Case(cid, "Highway", p, dict(script=script, label=label, **{k: v for k, v in extra.items()
                                                                              if k not in ("lead_gap", "steady_kph")})))
    return out


# =============================================================== grid files
SUITES = {
    "cutin_grid.xosc": ("CutIn", cutin_grid_cases),
    "cutin_official.xosc": ("CutIn", cutin_official_cases),
    "cutout_grid.xosc": ("CutOut", cutout_cases),
    "leadbrake_grid.xosc": ("LeadBrake", leadbrake_cases),
    "latprobe_grid.xosc": ("LatProbe", latprobe_cases),
    "engagement_cases.xosc": ("Highway", engagement_cases),
    "functional_cases.xosc": ("Highway", functional_cases),
}


def write_grid(name: str, family: str, cases: list[Case], note: str = "") -> Path:
    root = ET.Element("OpenSCENARIO")
    ET.SubElement(root, "FileHeader", revMajor="1", revMinor="2", date="2026-10-28T00:00:00",
                  author="Luo Wenjie (AI-assisted)",
                  description=f"{len(cases)} cases of {FAMILY_FILE[family] if family in FAMILY_FILE else family} "
                              f"(generated by dcas/scenarios.py){' - ' + note if note else ''}")
    dist = ET.SubElement(root, "ParameterValueDistribution")
    ET.SubElement(dist, "ScenarioFile", filepath=FAMILY_FILE[family] if family in FAMILY_FILE else "mixed")
    vs = ET.SubElement(ET.SubElement(ET.SubElement(dist, "Deterministic"), "DeterministicMultiParameterDistribution"),
                       "ValueSetDistribution")
    for c in cases:
        pvs = ET.SubElement(vs, "ParameterValueSet")
        if family not in FAMILY_FILE:
            ET.SubElement(pvs, "ParameterAssignment", parameterRef="ScenarioFile", value=FAMILY_FILE[c.family])
        for k, v in c.params.items():
            ET.SubElement(pvs, "ParameterAssignment", parameterRef=k, value=str(v))
    ET.indent(root, space="  ")
    path = SCEN_DIR / name
    ET.ElementTree(root).write(path, encoding="UTF-8", xml_declaration=True)
    return path


def read_grid(name: str) -> tuple[str, list[dict]]:
    root = ET.parse(SCEN_DIR / name).getroot()
    dist = root.find("ParameterValueDistribution")
    scen = dist.find("ScenarioFile").get("filepath")
    sets = [{a.get("parameterRef"): a.get("value") for a in pvs.iter("ParameterAssignment")}
            for pvs in dist.iter("ParameterValueSet")]
    return scen, sets


def curve_suite_files() -> dict[str, tuple[str, list[Case]]]:
    by_fam: dict[str, list[Case]] = {}
    for c in curve_cases():
        by_fam.setdefault(c.family, []).append(c)
    return {f"curve_{fam[6:] if fam != 'SBend' else 'sbend'}_grid.xosc".lower(): (fam, cs) for fam, cs in by_fam.items()}


def all_cases() -> list[Case]:
    out = []
    for name, (fam, fn) in SUITES.items():
        out += fn()
    out += curve_cases()
    return out


def case_index() -> dict[str, Case]:
    return {c.case_id: c for c in all_cases()}


def declared_types(scen_file: str) -> dict[str, str]:
    root = ET.parse(SCEN_DIR / scen_file).getroot()
    return {d.get("name"): d.get("parameterType") for d in root.find("ParameterDeclarations").iter("ParameterDeclaration")}


def declared_defaults(scen_file: str) -> dict[str, str]:
    root = ET.parse(SCEN_DIR / scen_file).getroot()
    return {d.get("name"): d.get("value") for d in root.find("ParameterDeclarations").iter("ParameterDeclaration")}
