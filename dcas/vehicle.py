"""Ego vehicle plant in road (Frenet) coordinates of the reference line.

State: s (reference-line station), d (lateral offset from the centre of the Ego lane, + = left), psi (heading
relative to the road), v (speed), a (actual longitudinal acceleration), kappa (actual path curvature).

Longitudinal: requested acceleration -> pure dead time -> first-order lag (DA-07).
Lateral: requested path curvature -> first-order lag (steering + tyre, DA-15); kinematic single-track model
  ds/dt = v cos(psi) / (1 - k_ref t),  dd/dt = v sin(psi),  dpsi/dt = v kappa - k_ref ds/dt,
  with t = t_lane + d.  Lateral acceleration a_y = v^2 kappa (no tyre slip: a toy model).
Values are design assumptions, not a real vehicle.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from .params import DcasConfig
from .road import Road, lane_center_t, EGO_LANE

EGO_LENGTH, EGO_WIDTH, EGO_CX = 4.6, 1.85, 1.4      # bounding box of the Ego in all .xosc files
EGO_FRONT = EGO_CX + EGO_LENGTH / 2.0               # front bumper ahead of the reference point (3.7 m)


@dataclass
class EgoState:
    s: float
    d: float
    psi: float
    v: float
    a: float = 0.0
    kappa: float = 0.0


class EgoVehicle:
    def __init__(self, cfg: DcasConfig, road: Road, s0: float, v0: float, d0: float = 0.0):
        self.cfg, self.road, self.dt = cfg, road, cfg.dt
        self.t_lane = lane_center_t(EGO_LANE)
        self.x = EgoState(s=s0, d=d0, psi=0.0, v=v0, kappa=road.lane_curvature(s0, self.t_lane + d0))
        n_dead = max(0, round(cfg.long_dead_time_s / cfg.dt))
        self.queue = deque([0.0] * n_dead)
        self.alpha_long = 1.0 - math.exp(-cfg.dt / cfg.long_tau_s)
        self.alpha_lat = 1.0 - math.exp(-cfg.dt / cfg.steer_tau_s)
        self.ay = v0 * v0 * self.x.kappa

    def step(self, a_req: float, kappa_req: float) -> EgoState:
        x, dt = self.x, self.dt
        self.queue.append(a_req)
        a_cmd = self.queue.popleft() if self.queue else a_req
        x.a += (a_cmd - x.a) * self.alpha_long
        x.kappa += (kappa_req - x.kappa) * self.alpha_lat
        k_ref = self.road.curvature(x.s)
        t_abs = self.t_lane + x.d
        v_new = max(0.0, x.v + x.a * dt)
        if v_new == 0.0 and x.a < 0.0:
            x.a = 0.0
        v_mid = 0.5 * (x.v + v_new)
        s_dot = v_mid * math.cos(x.psi) / (1.0 - k_ref * t_abs)
        x.s += s_dot * dt
        x.d += v_mid * math.sin(x.psi) * dt
        x.psi += (v_mid * x.kappa - k_ref * s_dot) * dt
        x.v = v_new
        self.ay = x.v * x.v * x.kappa
        return x
