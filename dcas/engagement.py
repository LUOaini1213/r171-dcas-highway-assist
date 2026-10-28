"""Driver-engagement monitoring for DCAS (R171 5.5.4.2) built on the DMS detectors copied from P7.

The copied P7 code (vendor/p7_dms, unchanged, SHA-256 checked by scripts/check_vendor.py) provides the
per-frame detectors: LongGlance (current glance away, with interruption tolerance and 'unknown' freezing),
Vats (Euro NCAP cumulative glance time), Drowsiness (eye-closure runs) and Availability (camera / face / eyes).
This module adds what R171 requires on top of them:

* Visual disengagement (5.5.4.2.5): gaze away from a driving-task relevant area.  Relevant areas here are the
  road and the mirrors; the instrument panel is NOT relevant (5.5.4.2.5.2) - unlike Euro NCAP DE, which
  treats the instrument cluster as a driving task.  Re-engagement needs > reengage_s on a relevant area
  (LongGlance tolerance; R171 >= 0.2 s).
* Motoric disengagement (5.5.4.2.4): hands off the steering control.
* Escalation (5.5.4.2.6): EOR -> escalated EOR -> DCA -> driver-unavailability response, and the same chain
  for HOR, with the design timings of dcas/params.py (all inside the R171 maxima).
* Immediate EOR for re-disengagement within 2 s (5.5.4.2.6.2.2) and for repeated short aversions
  (5.5.4.2.5.3, implemented with the Euro NCAP VATS rule).
* Repeated / prolonged disengagement (5.5.4.2.8): counters that disable the system (lock-out).
* Euro NCAP AD: DSM not usable -> deactivate (2.3.2.1); microsleep -> warning + longer time gap (4.2.1);
  sleep -> DCA; eyes closed >= 6 s -> unresponsive -> risk-mitigation stop (4.2.3).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from vendor.p7_dms import labels as L
from vendor.p7_dms.config import DmsConfig
from vendor.p7_dms.detectors import DEGRADED, NOMINAL, Availability, Drowsiness, LongGlance, Vats

from . import regulations as R
from .params import DcasConfig

# R171 5.5.4.2.5.2: the instrument panel is not a driving-task relevant area -> counted as disengaged.
R171_NOT_RELEVANT = frozenset({L.INSTRUMENT, L.INFOTAINMENT, L.PHONE, L.OFF_ROAD})

NONE, EOR, EOR_ESC, HOR, HOR_ESC, DCA, UNAVAILABLE = "", "EOR", "EOR_ESC", "HOR", "HOR_ESC", "DCA", "UNAVAILABLE"
URGENCY = {NONE: 0, HOR: 1, EOR: 2, HOR_ESC: 3, EOR_ESC: 3, DCA: 4, UNAVAILABLE: 5}


@dataclass
class EngagementOut:
    level: str = NONE                 # highest active request (one prompt at a time, R171 5.5.4.1.4)
    visual: bool = False
    acoustic: bool = False
    haptic: bool = False
    dca_request: bool = False         # -> state machine: TAKEOVER_REQUEST
    unavailable: bool = False         # -> state machine: risk-mitigation stop
    dsm_ok: bool = True               # DSM able to monitor (activation precondition R171 5.5.3.2.3 (b))
    dsm_unavailable_long: bool = False
    microsleep_event: bool = False
    lockout: bool = False
    vis_s: float = 0.0                # current visual disengagement time
    hands_off_s: float = 0.0
    events: list = field(default_factory=list)


class _Chain:
    """One escalation chain (EOR or HOR): request -> escalated -> DCA -> unavailable."""

    def __init__(self, name: str, t_esc: float, t_dca: float, t_unav: float):
        self.name, self.t_esc, self.t_dca, self.t_unav = name, t_esc, t_dca, t_unav
        self.reset()

    def reset(self):
        self.t_req = self.t_escalated = self.t_dca_issued = None

    def step(self, t: float, trigger: bool, still: bool) -> tuple[str, list]:
        """trigger: condition for a new request; still: disengagement continues.  Returns (stage, events)."""
        ev = []
        if self.t_req is None:
            if trigger:
                self.t_req = t
                ev.append(self.name)
        elif not still:
            ev.append(f"{self.name}_confirmed")
            if self.t_escalated is not None:
                ev.append(f"{self.name}_escalation_ended")
            self.reset()
            return NONE, ev
        if self.t_req is None:
            return NONE, ev
        if self.t_escalated is None and t - self.t_req >= self.t_esc - 1e-9:
            self.t_escalated = t
            ev.append(f"{self.name}_ESC")
        if self.t_escalated is not None and self.t_dca_issued is None and t - self.t_escalated >= self.t_dca - 1e-9:
            self.t_dca_issued = t
            ev.append(f"DCA_{self.name}")
        if self.t_escalated is not None and t - self.t_escalated >= self.t_unav - 1e-9:
            return UNAVAILABLE, ev
        if self.t_dca_issued is not None:
            return DCA, ev
        if self.t_escalated is not None:
            return (EOR_ESC if self.name == "EOR" else HOR_ESC), ev
        return (EOR if self.name == "EOR" else HOR), ev


class EngagementMonitor:
    def __init__(self, cfg: DcasConfig):
        self.cfg = cfg
        self.dms = DmsConfig(dt=cfg.dt, gap_tol_s=cfg.reengage_s, microsleep_hold_s=0.0)
        n = self.dms.n
        self.glance = LongGlance(R171_NOT_RELEVANT, False, n(cfg.reengage_s))
        self.vats = Vats(R171_NOT_RELEVANT, False, n(cfg.vats_window_s), n(cfg.vats_reset_s))
        self.drowsy = Drowsiness(self.dms)
        self.avail = Availability(self.dms)
        self.eor = _Chain("EOR", cfg.eor_escalate_s, cfg.dca_after_escalation_s, cfg.unavailable_after_escalation_s)
        self.hor = _Chain("HOR", cfg.hor_escalate_s, cfg.dca_after_escalation_s, cfg.unavailable_after_escalation_s)
        self.k = 0
        self.hands_off_n = 0
        self.t_reengaged = None
        self.glance_start = None
        self.vats_latched = False
        self.dsm_bad_n = 0
        self.n_unavailable = 0
        self.n_dca = 0
        self.escalations: deque = deque()
        self.lockout = False
        self.t_lockout = None
        self.closure_prev = 0
        self.microsleep_events: list[float] = []

    def step(self, t: float, speed_kph: float, gaze: str, eyelid: float, hands_on: bool, camera_ok: bool = True,
             face: bool = True, eyes: bool = True, monitoring: bool = True) -> EngagementOut:
        cfg, dt = self.cfg, self.cfg.dt
        out = EngagementOut()
        status, _info, _pulse = self.avail.update(camera_ok, face, eyes)
        gaze_ok = status in (NOMINAL, DEGRADED)
        label = gaze if gaze_ok else L.UNKNOWN
        n_vis = self.glance.update(label)
        vats_n = self.vats.update(label)
        _perclos, closure, _level = self.drowsy.update(self.k, eyelid, status == NOMINAL)
        self.k += 1
        out.dsm_ok = gaze_ok
        self.dsm_bad_n = 0 if gaze_ok else self.dsm_bad_n + 1
        out.dsm_unavailable_long = self.dsm_bad_n * dt >= cfg.dsm_unavailable_dca_s - 1e-9
        vis_s = n_vis * dt
        out.vis_s = vis_s
        self.hands_off_n = 0 if hands_on else self.hands_off_n + 1
        out.hands_off_s = self.hands_off_n * dt
        # glance bookkeeping for the re-disengagement rule (5.5.4.2.6.2.2)
        if n_vis > 0 and self.glance_start is None:
            self.glance_start = t - (n_vis - 1) * dt
        elif n_vis == 0:
            self.glance_start = None
        if cfg.vats_eor and vats_n * dt >= cfg.vats_threshold_s - 1e-9:
            self.vats_latched = True
        if vats_n == 0:
            self.vats_latched = False
        warn_ok = monitoring and speed_kph > R.R171_WARN_MIN_SPEED_KPH
        if not warn_ok:
            self.eor.reset()
            self.hor.reset()
            self._lockout_update(t)
            out.lockout = self.lockout
            return out
        # ------------------------------------------------------------------ EOR chain
        redis = (self.t_reengaged is not None and self.glance_start is not None
                 and self.glance_start - self.t_reengaged <= cfg.redisengage_window_s + 1e-9
                 and vis_s >= cfg.redisengage_min_s - 1e-9)
        eor_trigger = vis_s >= cfg.eor_s - 1e-9 or redis or (self.vats_latched and n_vis > 0)
        eor_still = n_vis > 0
        st_e, ev_e = self.eor.step(t, eor_trigger, eor_still)
        if "EOR_confirmed" in ev_e:
            self.t_reengaged = t
        if redis and "EOR" in ev_e:
            ev_e.append("EOR_redisengage")
        if self.vats_latched and "EOR" in ev_e and vis_s < cfg.eor_s - 1e-9 and not redis:
            ev_e.append("EOR_vats")
        # ------------------------------------------------------------------ HOR chain
        eyes_on = n_vis == 0
        hor_thr = cfg.hor_s + (cfg.hor_delay_eyes_on_s if eyes_on else 0.0)
        st_h, ev_h = self.hor.step(t, out.hands_off_s >= hor_thr - 1e-9, not hands_on)
        events = ev_e + ev_h
        for e in events:
            if e.endswith("_ESC"):
                self.escalations.append(t)
            if e.startswith("DCA_"):
                self.n_dca += 1
        stage = st_e if URGENCY[st_e] >= URGENCY[st_h] else st_h
        # ------------------------------------------------------------------ drowsiness (Euro NCAP AD 4.2)
        cl_s = closure * dt
        if closure > 0 and self.closure_prev * dt < cfg.microsleep_s <= cl_s:
            out.microsleep_event = True
            self.microsleep_events.append(t)
            events.append("microsleep")
        if cl_s >= cfg.sleep_s and self.closure_prev * dt < cfg.sleep_s:
            events.append("sleep")
        if cl_s >= cfg.sleep_s and URGENCY[stage] < URGENCY[DCA]:
            stage = DCA
            if self.closure_prev * dt < cfg.sleep_s:
                self.n_dca += 1
        if cl_s >= cfg.unresponsive_eyes_s:
            if self.closure_prev * dt < cfg.unresponsive_eyes_s:
                events.append("unresponsive")
            stage = UNAVAILABLE
        self.closure_prev = closure
        out.level = stage
        out.visual = stage != NONE
        out.acoustic = URGENCY[stage] >= URGENCY[EOR]          # EOR: visual + one other modality (5.5.4.2.3.2.1)
        out.haptic = URGENCY[stage] >= URGENCY[EOR_ESC]
        out.dca_request = stage in (DCA, UNAVAILABLE)
        out.unavailable = stage == UNAVAILABLE
        out.events = events
        self._lockout_update(t)
        out.lockout = self.lockout
        return out

    def driver_took_over(self, t: float) -> None:
        """DCA confirmed by the driver taking control (5.5.4.2.3.3.2): end the current chains."""
        self.eor.reset()
        self.hor.reset()
        self.t_reengaged = t

    def unavailability_started(self, t: float) -> None:
        self.n_unavailable += 1
        self._lockout_update(t)

    def _lockout_update(self, t: float) -> None:
        cfg = self.cfg
        while self.escalations and t - self.escalations[0] > cfg.lockout_window_s:
            self.escalations.popleft()
        if not self.lockout and (self.n_unavailable >= cfg.lockout_unavailable_n or self.n_dca >= cfg.lockout_dca_n
                                 or len(self.escalations) >= cfg.lockout_escalation_n):
            self.lockout = True
            self.t_lockout = t
