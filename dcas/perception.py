"""Object-list model between the world truth (esmini or Python backend) and the DCAS function.

Per object update (DA-10/11): field of view, range, simple angular occlusion (a nearer object hides a farther
one if it covers more than 1 - obj_visible_min of its angular width, seen from the Ego front bumper), track
confirmation after obj_confirm_n consecutive detections, latency, Gaussian measurement noise, and a
constant-velocity Kalman filter on the lateral position that estimates the lateral speed used for cut-in
prediction.  Lateral positions are relative to the CENTRE OF THE EGO LANE (lane-relative object list).

This is a toy model chosen to make occlusion (cut-out reveal) and lateral-speed noise (false cut-in
predictions) visible; it is not a sensor model of any product.
"""
from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field

from .params import DcasConfig
from .road import EGO_LANE, lane_center_t
from .vehicle import EGO_FRONT


A_OBJ_TAU_S = 0.5          # DA-28 low-pass time constant of the object acceleration estimate


@dataclass(frozen=True)
class ObjTruth:
    oid: str
    s: float            # reference point station
    t: float            # lateral position (absolute, reference line)
    v: float            # speed
    length: float
    width: float
    cx: float           # bounding-box centre ahead of the reference point


@dataclass
class Track:
    oid: str
    gap: float = 0.0          # bumper-to-bumper longitudinal distance
    v_rel: float = 0.0        # object speed - ego speed (negative = closing)
    v_obj: float = 0.0
    y: float = 0.0            # lateral centre relative to the Ego lane centre (+ = left)
    vy: float = 0.0           # filtered lateral speed
    width: float = 1.8
    a_obj: float = 0.0        # filtered object acceleration (from successive object speeds)
    hits: int = 0
    misses: int = 0
    confirmed: bool = False
    P: list = field(default_factory=lambda: [[0.0, 0.0], [0.0, 0.0]])


def _interval(x0: float, x1: float, y0: float, y1: float, ys: float) -> tuple[float, float]:
    angs = [math.atan2(yy - ys, xx) for xx in (x0, x1) for yy in (y0, y1)]
    return min(angs), max(angs)


def visible_fractions(objs: list[tuple[str, float, float, float, float]], ys: float) -> dict[str, float]:
    """objs: (oid, x_rear, x_front, y_right, y_left) in the sensor frame (x forward from the Ego front bumper).
    Returns the visible fraction of each object's angular extent after occlusion by nearer objects."""
    ivs = [(o[1], o[0], _interval(o[1], o[2], o[3], o[4], ys)) for o in objs if o[1] > 0.0]
    ivs.sort()
    out = {}
    for i, (xr, oid, (a0, a1)) in enumerate(ivs):
        width = a1 - a0
        if width <= 0:
            out[oid] = 0.0
            continue
        cover = []
        for xr2, oid2, (b0, b1) in ivs[:i]:          # nearer objects only
            lo, hi = max(a0, b0), min(a1, b1)
            if hi > lo:
                cover.append((lo, hi))
        cover.sort()
        covered, cur_lo, cur_hi = 0.0, None, None
        for lo, hi in cover:
            if cur_hi is None or lo > cur_hi:
                if cur_hi is not None:
                    covered += cur_hi - cur_lo
                cur_lo, cur_hi = lo, hi
            else:
                cur_hi = max(cur_hi, hi)
        if cur_hi is not None:
            covered += cur_hi - cur_lo
        out[oid] = max(0.0, 1.0 - covered / width)
    return out


class Perception:
    def __init__(self, cfg: DcasConfig, seed: int = 0):
        self.cfg = cfg
        self.dt = cfg.dt
        self.n_upd = max(1, round(cfg.obj_period_s / cfg.dt))
        self.n_lat = round(cfg.obj_latency_s / cfg.dt)
        self.hist: deque = deque(maxlen=self.n_lat + 2)
        self.rng = random.Random(seed)
        self.tracks: dict[str, Track] = {}
        self.t_lane = lane_center_t(EGO_LANE)
        self.T = self.n_upd * cfg.dt
        q = cfg.kf_q_lat
        T = self.T
        self.Q = [[q * q * T ** 4 / 4.0, q * q * T ** 3 / 2.0], [q * q * T ** 3 / 2.0, q * q * T * T]]
        self.Rm = cfg.sd_y_m ** 2

    def _detections(self, ego_s: float, ego_d: float, ego_v: float, objs: list[ObjTruth]) -> list[tuple]:
        cfg = self.cfg
        rows = []
        geo = []
        for o in objs:
            x_rear = (o.s + o.cx - o.length / 2.0) - (ego_s + EGO_FRONT)
            x_front = x_rear + o.length
            y = o.t - self.t_lane
            geo.append((o.oid, x_rear, x_front, y - o.width / 2.0, y + o.width / 2.0))
            rows.append((o, x_rear, y))
        vis = visible_fractions(geo, ego_d)
        out = []
        half_fov = math.radians(cfg.obj_fov_deg)
        for o, x_rear, y in rows:
            if x_rear <= 0.0 or x_rear > cfg.obj_range_m:
                continue
            near_y = 0.0 if abs(y - ego_d) < o.width / 2.0 else (abs(y - ego_d) - o.width / 2.0)
            if math.atan2(near_y, x_rear) > half_fov:
                continue
            if vis.get(o.oid, 0.0) < cfg.obj_visible_min:
                continue
            out.append((o.oid, x_rear, o.v - ego_v, o.v, y, o.width))
        return out

    def step(self, k: int, ego_s: float, ego_d: float, ego_v: float, objs: list[ObjTruth]) -> list[Track]:
        self.hist.append(self._detections(ego_s, ego_d, ego_v, objs))
        if k % self.n_upd == 0:
            dets = self.hist[0] if len(self.hist) > self.n_lat else []
            if len(self.hist) > self.n_lat:
                dets = self.hist[-1 - self.n_lat]
            self._update(dets)
        return [tr for tr in self.tracks.values() if tr.confirmed]

    def _update(self, dets: list[tuple]) -> None:
        cfg, rng, T = self.cfg, self.rng, self.T
        seen = set()
        for oid, gap, v_rel, v_obj, y, w in dets:
            seen.add(oid)
            gap_m = gap + (rng.gauss(0.0, cfg.sd_x_m) if cfg.sd_x_m else 0.0)
            v_m = v_rel + (rng.gauss(0.0, cfg.sd_v_mps) if cfg.sd_v_mps else 0.0)
            y_m = y + (rng.gauss(0.0, cfg.sd_y_m) if cfg.sd_y_m else 0.0)
            tr = self.tracks.get(oid)
            if tr is None:
                tr = Track(oid=oid, y=y_m, vy=0.0, width=w)
                tr.P = [[self.Rm, 0.0], [0.0, 1.0]]
                self.tracks[oid] = tr
            else:                                   # constant-velocity Kalman filter on y
                P = tr.P
                y_p = tr.y + tr.vy * T
                P00 = P[0][0] + T * (P[1][0] + P[0][1]) + T * T * P[1][1] + self.Q[0][0]
                P01 = P[0][1] + T * P[1][1] + self.Q[0][1]
                P11 = P[1][1] + self.Q[1][1]
                S = P00 + self.Rm
                K0, K1 = P00 / S, P01 / S
                innov = y_m - y_p
                tr.y = y_p + K0 * innov
                tr.vy = tr.vy + K1 * innov
                tr.P = [[(1 - K0) * P00, (1 - K0) * P01], [P01 - K1 * P00, P11 - K1 * P01]]
            v_obj_m = v_obj + (v_m - v_rel)            # object speed seen through the noisy range rate
            if tr.hits > 0:
                a_raw = (v_obj_m - tr.v_obj) / T
                tr.a_obj += (a_raw - tr.a_obj) * min(1.0, T / A_OBJ_TAU_S)
            tr.gap, tr.v_rel, tr.v_obj, tr.width = gap_m, v_m, v_obj_m, w
            tr.hits += 1
            tr.misses = 0
            if tr.hits >= cfg.obj_confirm_n:
                tr.confirmed = True
        for oid in list(self.tracks):
            if oid not in seen:
                tr = self.tracks[oid]
                tr.misses += 1
                tr.hits = 0
                if tr.misses >= 2:
                    del self.tracks[oid]
