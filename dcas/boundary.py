"""System-boundary monitor (R171 5.3.5): detects boundaries being approached / reached while 'on'.

Boundaries modelled (declared in report.md, R171 5.3.5.2 / Annex 3 Appendix 3):
  lane_markings  lane markings not detected for > lane_marking_lost_s (scenario input)
  lateral_limit  lane centring saturated and the Ego has drifted beyond LAT_LIMIT_D_M towards the marking
                 (R171 5.3.7.1.4: continued assistance + optical and acoustic/haptic warning)
  speed_range    speed above the designed range + tolerance (e.g. driver accelerating, R171 5.3.7.4.3)
  dsm            driver monitoring not usable for > dsm_unavailable_dca_s (Euro NCAP AD 2.3.2.1)
  seatbelt       driver seat belt unfastened (R171 5.5.3.2.3 (a))
Approaching (R171 5.3.5.5, inform with lead time): the curvature preview needs more lateral acceleration
than ay_ctrl_max at the speed the Ego can reach there.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .params import DcasConfig
from .road import Road

LAT_LIMIT_D_M = 0.5          # DA-26 drift beyond 0.5 m with saturated lane centring = lateral boundary reached
SPEED_TOL_KPH = 5.0          # DA-26 tolerance above the designed speed range


@dataclass
class BoundaryOut:
    within: bool = True
    reason: str = ""
    approaching: bool = False
    approach_reason: str = ""


class BoundaryMonitor:
    def __init__(self, cfg: DcasConfig, road: Road, t_lane: float):
        self.cfg, self.road, self.t_lane = cfg, road, t_lane
        self.lost_n = 0

    def step(self, v: float, s: float, d: float, lcc_saturated: bool, markings_ok: bool, dsm_long_bad: bool,
             seatbelt: bool, curve_on: bool, lateral_active: bool) -> BoundaryOut:
        cfg = self.cfg
        out = BoundaryOut()
        self.lost_n = 0 if markings_ok else self.lost_n + 1
        reasons = []
        if self.lost_n * cfg.dt > cfg.lane_marking_lost_s:
            reasons.append("lane_markings")
        if lateral_active and lcc_saturated and abs(d) > LAT_LIMIT_D_M:
            reasons.append("lateral_limit")
        if v * 3.6 > cfg.v_max_kph + SPEED_TOL_KPH:
            reasons.append("speed_range")
        if dsm_long_bad:
            reasons.append("dsm")
        if not seatbelt:
            reasons.append("seatbelt")
        if reasons:
            out.within, out.reason = False, "+".join(reasons)
        # approaching a lateral boundary: preview 5 s; with curve-speed adaptation the speed at x is limited
        horizon = max(50.0, 5.0 * v)
        for i in range(1, int(horizon / 5.0) + 1):
            x = i * 5.0
            k = abs(self.road.lane_curvature(s + x, self.t_lane + d))
            if k < 1e-5:
                continue
            v_at = v
            if curve_on:                       # slowest speed reachable with the planning deceleration
                v_reach = math.sqrt(max(v * v - 2.0 * cfg.a_curve_plan * x, 0.0))
                v_at = max(v_reach, min(v, math.sqrt(cfg.ay_curve_target / k)))
            if v_at * v_at * k > cfg.ay_ctrl_max:
                out.approaching, out.approach_reason = True, "curvature"
                break
        return out
