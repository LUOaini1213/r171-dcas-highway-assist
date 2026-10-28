"""Lane centring: curvature feed-forward + state feedback, with lateral-acceleration and lateral-jerk limits.

kappa_cmd = kappa_lane(s + v * t_ff) - k_d d - k_psi psi,  k_d = (wn / v)^2,  k_psi = 2 zeta wn / v
(closed loop on a straight road: d'' + 2 zeta wn d' + wn^2 d = 0).
Limits: |v^2 kappa_cmd| <= ay_ctrl_max (declared max + 0.3 m/s2, R171 5.3.7.1.2) and the lateral-acceleration
command changes at most jy_max per second (R171 5.3.7.1.2.1: 0.5 s mean lateral jerk <= 5 m/s3).
When the road needs more than ay_ctrl_max the command saturates and the vehicle drifts outwards: that is the
system boundary of lateral control (handled by dcas/boundary.py).
"""
from __future__ import annotations

from .params import DcasConfig
from .road import Road

V_MIN = 5.0


class LaneCentering:
    def __init__(self, cfg: DcasConfig, road: Road, t_lane: float):
        self.cfg, self.road, self.t_lane = cfg, road, t_lane
        self.ay_cmd = 0.0
        self.saturated = False

    def reset(self, ay_now: float) -> None:
        self.ay_cmd = ay_now

    def step(self, s: float, d: float, psi: float, v: float) -> float:
        cfg = self.cfg
        vv = max(v, V_MIN)
        wn, z = cfg.lcc_wn, cfg.lcc_zeta
        k_ff = self.road.lane_curvature(s + v * cfg.lcc_ff_preview_s, self.t_lane + d)
        kappa = k_ff - (wn / vv) ** 2 * d - (2.0 * z * wn / vv) * psi
        ay = vv * vv * kappa
        self.saturated = abs(ay) > cfg.ay_ctrl_max
        ay = max(-cfg.ay_ctrl_max, min(cfg.ay_ctrl_max, ay))
        dmax = cfg.jy_max * cfg.dt
        self.ay_cmd = max(self.ay_cmd - dmax, min(self.ay_cmd + dmax, ay))
        return self.ay_cmd / (vv * vv)
