"""Scripted driver for the closed loop: gaze / eyelid / hands timeline, pedal and steering events, button
presses, and a simple reaction to DCAS warnings.  All timings are scenario inputs (SYNTHETIC driver).

Reaction model (design assumption DA-27): a driver with respond_to = "EOR" | "EOR_ESC" | "DCA" looks back at
the road reaction_s after that warning level first appears (and puts the hands back on); with
takeover_on_dca the driver also takes control (hands on + steering torque above the override threshold)
reaction_s after a DCA.  respond_to = None models an unresponsive driver.
When the function does not control a channel, the driver does: longitudinal = hold speed / scripted pedals,
lateral = a gentle lane-keeping controller while the hands are on (no steering when hands are off).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from vendor.p7_dms import labels as L

ORDER = {"EOR": 1, "HOR": 1, "EOR_ESC": 2, "HOR_ESC": 2, "DCA": 3, "UNAVAILABLE": 4}


@dataclass
class DriverScript:
    gaze: list = field(default_factory=list)          # (t0, t1, label)
    eyes_closed: list = field(default_factory=list)   # (t0, t1)
    hands_off: list = field(default_factory=list)     # (t0, t1)
    accel: list = field(default_factory=list)         # (t0, t1, accel demand m/s2)
    brake: list = field(default_factory=list)         # (t0, t1, decel m/s2)
    steer: list = field(default_factory=list)         # (t0, t1, torque N.m)
    camera_blocked: list = field(default_factory=list)  # (t0, t1)
    seatbelt_off: list = field(default_factory=list)  # (t0, t1)
    set_at: tuple = (0.0,)                            # set/resume presses
    cancel_at: tuple = ()
    main_switch_off_at: float | None = None
    respond_to: str | None = "EOR"
    reaction_s: float = 1.0
    takeover_on_dca: bool = True


@dataclass
class DriverInputs:
    gaze: str
    eyelid: float
    hands_on: bool
    camera_ok: bool
    seatbelt: bool
    main_switch: bool
    set_pressed: bool
    cancel_pressed: bool
    brake_pedal: bool
    brake_decel: float
    accel_demand: float | None
    steer_torque_nm: float


def _in(t: float, segs) -> object:
    for seg in segs:
        if seg[0] <= t < seg[1]:
            return seg
    return None


class ScriptedDriver:
    def __init__(self, script: DriverScript, dt: float, steer_override_nm: float):
        self.sc, self.dt, self.steer_nm = script, dt, steer_override_nm
        self.t_warn_first: dict[str, float] = {}
        self.responding_since: float | None = None
        self.responding_until: float = -1.0
        self.takeover_since: float | None = None
        self.took_over = False

    def _episode_end(self, t: float) -> float:
        """A response lasts until the scripted distraction active at that moment is over."""
        ends = [seg[1] for segs in (self.sc.gaze, self.sc.hands_off, self.sc.eyes_closed) for seg in segs
                if seg[0] <= t < seg[1]]
        return max(ends) if ends else t

    def notify(self, t: float, level: str, state: str) -> None:
        """Called every step with the current DCAS warning level and mode (driver perception of the HMI)."""
        if level and level not in self.t_warn_first:
            self.t_warn_first[level] = t
        sc = self.sc
        if self.responding_since is not None and t >= self.responding_until and t >= self.responding_since:
            self.responding_since = None                      # episode over: back to the script
        if sc.respond_to and level and ORDER.get(level, 0) >= ORDER.get(sc.respond_to, 9) and self.responding_since is None:
            self.responding_since = t + sc.reaction_s
            self.responding_until = self._episode_end(t + sc.reaction_s)
        if sc.respond_to and sc.takeover_on_dca and level in ("DCA", "UNAVAILABLE") and self.takeover_since is None \
                and ORDER.get(level, 0) >= ORDER.get(sc.respond_to, 9):
            self.takeover_since = t + sc.reaction_s

    def inputs(self, t: float) -> DriverInputs:
        sc, dt = self.sc, self.dt
        responding = self.responding_since is not None and self.responding_since <= t < max(self.responding_until,
                                                                                           self.responding_since + dt)
        taking_over = self.takeover_since is not None and t >= self.takeover_since
        g = _in(t, sc.gaze)
        gaze = g[2] if g else L.ROAD
        hands_on = _in(t, sc.hands_off) is None
        if responding:
            gaze, hands_on = L.ROAD, True
        eyes_closed = _in(t, sc.eyes_closed) is not None and not responding
        torque = 0.0
        s = _in(t, sc.steer)
        if s:
            torque = s[2]
        if taking_over and not self.took_over:
            torque, hands_on = 1.5 * self.steer_nm, True
        a = _in(t, sc.accel)
        b = _in(t, sc.brake)
        return DriverInputs(
            gaze=gaze, eyelid=1.0 if eyes_closed else 0.1, hands_on=hands_on,
            camera_ok=_in(t, sc.camera_blocked) is None, seatbelt=_in(t, sc.seatbelt_off) is None,
            main_switch=sc.main_switch_off_at is None or t < sc.main_switch_off_at,
            set_pressed=any(abs(t - x) < dt / 2 for x in sc.set_at),
            cancel_pressed=any(abs(t - x) < dt / 2 for x in sc.cancel_at),
            brake_pedal=b is not None, brake_decel=b[2] if b else 0.0,
            accel_demand=a[2] if a else None, steer_torque_nm=torque)

    def confirm_takeover(self) -> None:
        self.took_over = True


def manual_lane_keeping(d: float, psi: float, v: float, kappa_road: float) -> float:
    """Driver lateral control when the function does not steer (gentle, DA-27)."""
    vv = max(v, 5.0)
    wn, z = 0.6, 1.0
    return kappa_road - (wn / vv) ** 2 * d - (2.0 * z * wn / vv) * psi
