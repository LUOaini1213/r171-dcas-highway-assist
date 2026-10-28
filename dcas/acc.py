"""Longitudinal control: target selection (incl. cut-in prediction), constant-time-gap following, cruise,
curve-speed adaptation, comfort / critical limits.

Target selection (DA-09) uses the lane-relative object list:
  intrusion = lane half-width - (|y| - width/2)       (> 0: the object's near edge is inside the Ego lane)
  in path   = centre inside the lane, or intrusion >= intrusion_m
  cut-in    = lateral speed towards the lane >= v_lat_min and intrusion + v_lat * t_pred_s >= intrusion_m
  release   = an in-path object is dropped when its intrusion falls below release_m (cut-out)
Following law per in-path object (DA-04): a = k_gap clip(gap - d0 - tau v, +-8 m) + k_rel v_rel, kept inside
the comfort range; while closing, never less braking than 1.25 x the kinematic demand v_rel^2 / (2 (gap - d0)).
The most demanding object wins (multi-target).
Limits (DA-05/06): accel <= a_max; comfort mode decel >= a_comfort with jerk_comfort; when 1.25 x the
kinematic demand exceeds the comfort limit, critical mode allows the authority a_authority (= 5 m/s2,
R171 2.16) with jerk_critical.
Curve speed (DA-13, R171 5.3.7.1.1.1): v <= sqrt(ay_curve_target / |k|) along the preview, reachable with
a_curve_plan.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .params import DcasConfig
from .perception import Track
from .road import LANE_WIDTH_M, Road

HALF_LANE = LANE_WIDTH_M / 2.0
GAP_ERR_CLIP_M = 8.0      # DA-04 gap error is clipped: a large gap error alone asks for at most k_gap * 8 m = 2 m/s2
KIN_MARGIN = 1.25         # DA-04 brake 25 % harder than the bare kinematic demand (lag and noise margin)


def intrusion(tr: Track) -> float:
    return HALF_LANE - (abs(tr.y) - tr.width / 2.0)


def towards_lane_speed(tr: Track) -> float:
    """Lateral speed towards the Ego lane centre (+ = approaching)."""
    return -math.copysign(1.0, tr.y) * tr.vy if tr.y != 0.0 else 0.0


@dataclass
class AccOutput:
    a_des: float = 0.0
    a_cmd: float = 0.0
    mode: str = "cruise"          # cruise | follow | critical
    target: str = ""              # most demanding object
    targets: tuple = ()
    a_kin_req: float = 0.0        # kinematic deceleration demand of the most demanding object (>= 0)
    v_curve: float = float("inf")
    gap_s: float = 0.0


class Acc:
    def __init__(self, cfg: DcasConfig, road: Road, t_lane: float):
        self.cfg, self.road, self.t_lane = cfg, road, t_lane
        self.gap_idx = cfg.gap_default_idx
        self.in_path: set[str] = set()
        self.a_cmd = 0.0
        self.gap_add_s = 0.0          # microsleep intervention (Euro NCAP AD 4.2.1)
        self.v_set = 0.0

    @property
    def time_gap(self) -> float:
        return self.cfg.gap_settings_s[self.gap_idx] + self.gap_add_s

    def select(self, tracks: list[Track]) -> list[Track]:
        cfg = self.cfg
        keep = []
        new_set = set()
        for tr in tracks:
            if tr.gap <= 0.0:
                continue
            e = intrusion(tr)
            centre_in = abs(tr.y) < HALF_LANE
            was = tr.oid in self.in_path
            if centre_in or e >= cfg.intrusion_m:
                sel = True
            elif was:
                sel = e >= cfg.release_m          # hysteresis: keep until it has (nearly) left the lane
            else:
                vl = towards_lane_speed(tr)
                sel = cfg.t_pred_s > 0.0 and vl >= cfg.v_lat_min and e + vl * cfg.t_pred_s >= cfg.intrusion_m
            if sel:
                keep.append(tr)
                new_set.add(tr.oid)
        self.in_path = new_set
        return keep

    def curve_speed(self, s: float, d: float, v: float) -> float:
        """Highest speed now that lets the Ego meet sqrt(ay_target/|k|) everywhere in the preview."""
        cfg = self.cfg
        horizon = v * v / (2.0 * cfg.a_curve_plan) + 3.0 * v + 20.0
        v_lim = float("inf")
        step = 5.0
        n = int(horizon / step) + 1
        t = self.t_lane + d
        for i in range(n):
            x = i * step
            k = abs(self.road.lane_curvature(s + x, t))
            if k < 1e-5:
                continue
            vc = math.sqrt(cfg.ay_curve_target / k)
            v_lim = min(v_lim, math.sqrt(vc * vc + 2.0 * cfg.a_curve_plan * x))
        return v_lim

    def step(self, tracks: list[Track], v: float, s: float, d: float, v_set: float, curve_on: bool = True,
             a_override_min: float | None = None) -> AccOutput:
        cfg = self.cfg
        out = AccOutput()
        self.v_set = v_set
        v_target = min(v_set, cfg.v_max_kph / 3.6)
        if curve_on:
            out.v_curve = self.curve_speed(s, d, v)
            v_target = min(v_target, out.v_curve)
        a = max(-1.5, min(cfg.a_max, cfg.k_cruise * (v_target - v)))
        out.mode = "cruise"
        tau = self.time_gap
        out.gap_s = tau
        sel = self.select(tracks)
        out.targets = tuple(tr.oid for tr in sel)
        worst = None
        critical = False
        for tr in sel:
            g_des = cfg.d0_m + tau * v
            e_gap = max(-GAP_ERR_CLIP_M, min(GAP_ERR_CLIP_M, tr.gap - g_des))
            a_f = max(cfg.a_comfort, cfg.k_gap * e_gap + cfg.k_rel * tr.v_rel)   # regulation stays in comfort range
            a_kin = 0.0
            if cfg.lead_accel_ff and tr.a_obj < -1.5 and tr.v_obj > 0.5:        # object is braking (DA-28)
                v_e = max(0.0, tr.v_obj - tr.v_rel)
                stop_obj = tr.v_obj * tr.v_obj / (2.0 * -tr.a_obj)
                a_stop = v_e * v_e / (2.0 * max(tr.gap - cfg.d0_m + stop_obj, 0.5))
                if KIN_MARGIN * a_stop > -cfg.a_comfort:
                    critical = True
                a_f = min(a_f, -KIN_MARGIN * a_stop)
            if tr.v_rel < 0.0:                                                   # kinematic demand (closing only)
                a_kin = tr.v_rel * tr.v_rel / (2.0 * max(tr.gap - cfg.d0_m, 0.5))
                if KIN_MARGIN * a_kin > -cfg.a_comfort:
                    critical = True
                a_f = min(a_f, -KIN_MARGIN * a_kin)
            if a_f < a:
                a = a_f
                worst = tr
                out.a_kin_req = a_kin
        if worst is not None:
            out.target = worst.oid
            out.mode = "follow"
        if critical:
            out.mode = "critical"
        a_lo = cfg.a_authority if critical else cfg.a_comfort
        a = max(a_lo, min(cfg.a_max, a))
        if a_override_min is not None:
            a = min(a, a_override_min)        # e.g. risk-mitigation stop profile
            a = max(cfg.a_authority, a)
        out.a_des = a
        # jerk limiter: braking build-up uses jerk_critical in critical mode, everything else jerk_comfort
        dt = cfg.dt
        j_down = cfg.jerk_critical if critical else cfg.jerk_comfort
        lo = self.a_cmd - j_down * dt
        hi = self.a_cmd + cfg.jerk_comfort * dt
        self.a_cmd = min(hi, max(lo, a))
        out.a_cmd = self.a_cmd
        return out

    def reset_command(self, a_now: float) -> None:
        """Bumpless transfer when the function (re)takes longitudinal control."""
        self.a_cmd = a_now
