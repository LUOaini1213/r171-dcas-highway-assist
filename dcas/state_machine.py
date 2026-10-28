"""DCAS mode manager.  States follow R171 2.14-2.15 / 5.5.1 plus the transitional states the function needs:

  OFF                R171 2.14 'off' (default at every powertrain start, 5.5.3.1)
  STANDBY            R171 2.15.2 'stand-by' (on, no control output; passive or inactive)
  ACTIVE             R171 2.15.1 'active' (longitudinal + lateral assistance)
  DRIVER_OVERRIDE    R171 2.26 / 5.5.3.4.1: driver input has priority, the feature stays active
  TAKEOVER_REQUEST   a Direct Control Alert is presented (R171 2.34, 5.5.4.2.3.3) because of the warning
                     escalation (5.5.4.2.6.3) or a system boundary (5.3.5.1); lateral assistance continues
                     (5.3.7.1.4) until the driver takes control
  MRM                driver-unavailability response: risk-mitigation stop in lane (R171 5.3.7.3, which refers
                     to the R79 04 series Risk Mitigation Function - R79 text not read, design values)

Every transition has an ID (T01..T15) that is logged with its time and cited in report.md / traceability.csv.
"""
from __future__ import annotations

from dataclasses import dataclass, field

OFF, STANDBY, ACTIVE, OVERRIDE, TOR, MRM = "OFF", "STANDBY", "ACTIVE", "DRIVER_OVERRIDE", "TAKEOVER_REQUEST", "MRM"
STATES = (OFF, STANDBY, ACTIVE, OVERRIDE, TOR, MRM)

TRANSITIONS = {   # id: (from, to, condition, source)
    "T01": (OFF, STANDBY, "主开关打开（驾驶员有意操作）", "R171 5.5.3.2.2"),
    "T02": (STANDBY, ACTIVE, "按下设定键且激活前提全部满足", "R171 5.5.3.2.3"),
    "T03": (ACTIVE, STANDBY, "驾驶员踩制动或按取消键", "R171 5.5.3.4.1.1, 5.5.3.4.1.1.1"),
    "T04": (ACTIVE, OVERRIDE, "加速踏板需求高于系统 / 转向扭矩超过阈值", "R171 5.5.3.4.1.3, 5.5.3.4.1.4"),
    "T05": (OVERRIDE, ACTIVE, "超越结束（松开加速踏板 / 扭矩低于阈值 1 s）", "R171 5.5.3.4.1.3"),
    "T06": (ACTIVE, TOR, "脱离报警升级到 DCA（ACTIVE 或 DRIVER_OVERRIDE 中）", "R171 5.5.4.2.6.3.1"),
    "T07": (ACTIVE, TOR, "到达系统边界（ACTIVE 或 DRIVER_OVERRIDE 中）", "R171 5.3.5.1, 5.3.7.1.4; Euro NCAP AD 2.3.2.1"),
    "T08": (TOR, STANDBY, "驾驶员接管（手在盘上且有转向输入，或踩制动）", "R171 5.5.4.2.3.3.2, 5.3.5.1"),
    "T09": (TOR, MRM, "DCA 后驾驶员仍不可用 / 超时未接管", "R171 5.5.4.2.6.4.1, 5.3.7.3.1"),
    "T10": (ACTIVE, MRM, "判定驾驶员无响应（闭眼 ≥6 s）", "Euro NCAP AD 4.2.3; R171 5.3.7.3.1"),
    "T11": (MRM, STANDBY, "风险减缓过程中驾驶员接管", "设计（R79 RMF 原文未核实）"),
    "T12": (MRM, MRM, "停车后保持并开危险报警灯，等待驾驶员", "设计（R79 RMF 原文未核实）"),
    "T13": (STANDBY, OFF, "主开关关闭（任意 on 状态）", "R171 5.5.3.3.1, 5.5.3.3.2"),
    "T14": (ACTIVE, OFF, "影响整个系统的失效（任意 on 状态）", "R171 5.4.2.1"),
    "T15": (STANDBY, STANDBY, "激活被拒绝（锁止 / 前提不满足），给出提示", "R171 5.5.4.2.8.1, 5.4.5"),
}


@dataclass
class SmInputs:
    t: float
    v_kph: float
    main_switch: bool = True
    set_pressed: bool = False
    cancel_pressed: bool = False
    brake_pedal: bool = False
    accel_override: bool = False
    steer_torque_nm: float = 0.0
    hands_on: bool = True
    seatbelt: bool = True
    failure: bool = False
    dca_request: bool = False
    unavailable: bool = False
    dsm_ok: bool = True
    lockout: bool = False
    within_boundaries: bool = True
    boundary_reason: str = ""
    standstill: bool = False


@dataclass
class SmOutputs:
    state: str
    lateral_on: bool
    longitudinal_on: bool
    hazard_lights: bool
    override_kind: str = ""
    events: list = field(default_factory=list)


class StateMachine:
    def __init__(self, cfg, start: str = OFF):
        self.cfg = cfg
        self.state = start
        self.log: list[tuple[float, str, str, str, str]] = []      # (t, from, to, transition id, detail)
        self.t_enter = 0.0
        self.override_kind = ""
        self.torque_low_s = 0.0
        self.tor_cause = ""
        self.refusals: list[tuple[float, str]] = []

    def _go(self, t: float, to: str, tid: str, detail: str = "") -> None:
        self.log.append((round(t, 3), self.state, to, tid, detail))
        self.state = to
        self.t_enter = t

    def preconditions(self, i: SmInputs) -> list[str]:
        missing = []
        if not i.seatbelt:
            missing.append("seatbelt")
        if not i.dsm_ok:
            missing.append("dsm")
        if i.failure:
            missing.append("failure")
        if not i.within_boundaries:
            missing.append(f"boundary:{i.boundary_reason}")
        if i.lockout:
            missing.append("lockout")
        if i.v_kph > self.cfg.v_max_kph:
            missing.append("speed")
        return missing

    def step(self, i: SmInputs) -> SmOutputs:
        cfg, s = self.cfg, self.state
        dt = cfg.dt
        steer_over = abs(i.steer_torque_nm) > cfg.steer_override_nm
        takeover = (i.hands_on and steer_over) or i.brake_pedal
        events = []
        if s != OFF and not i.main_switch:
            self._go(i.t, OFF, "T13", "main switch off")
        elif s != OFF and i.failure:
            self._go(i.t, OFF, "T14", "system failure")
            events.append("failure_warning")
        elif s == OFF:
            if i.main_switch and not i.failure:
                self._go(i.t, STANDBY, "T01")
                if i.set_pressed:                  # switch on and set in the same task cycle
                    missing = self.preconditions(i)
                    if missing:
                        self.refusals.append((round(i.t, 3), "+".join(missing)))
                        self.log.append((round(i.t, 3), STANDBY, STANDBY, "T15", "+".join(missing)))
                        events.append("activation_refused")
                    else:
                        self._go(i.t, ACTIVE, "T02")
        elif s == STANDBY:
            if i.set_pressed:
                missing = self.preconditions(i)
                if missing:
                    self.refusals.append((round(i.t, 3), "+".join(missing)))
                    self.log.append((round(i.t, 3), STANDBY, STANDBY, "T15", "+".join(missing)))
                    events.append("activation_refused")
                else:
                    self._go(i.t, ACTIVE, "T02")
        elif s in (ACTIVE, OVERRIDE):
            if i.unavailable:
                self._go(i.t, MRM, "T10", "driver unresponsive")
            elif i.dca_request:
                self.tor_cause = "engagement"
                self._go(i.t, TOR, "T06", "disengagement escalation")
            elif not i.within_boundaries:
                self.tor_cause = i.boundary_reason
                self._go(i.t, TOR, "T07", i.boundary_reason)
            elif i.brake_pedal or i.cancel_pressed:
                self.override_kind = ""
                self._go(i.t, STANDBY, "T03", "brake" if i.brake_pedal else "cancel")
            elif s == ACTIVE and (i.accel_override or steer_over):
                self.override_kind = "+".join(k for k, on in (("accel", i.accel_override), ("steer", steer_over)) if on)
                self.torque_low_s = 0.0
                self._go(i.t, OVERRIDE, "T04", self.override_kind)
            elif s == OVERRIDE:
                self.torque_low_s = 0.0 if steer_over else self.torque_low_s + dt
                kinds = []
                if i.accel_override:
                    kinds.append("accel")
                if steer_over or self.torque_low_s < cfg.override_release_s:
                    if "steer" in self.override_kind or steer_over:
                        kinds.append("steer")
                if kinds:
                    self.override_kind = "+".join(kinds)
                else:
                    self.override_kind = ""
                    self._go(i.t, ACTIVE, "T05")
        elif s == TOR:
            if takeover:
                self._go(i.t, STANDBY, "T08", "driver took control")
                events.append("driver_took_over")
            elif i.unavailable or (self.tor_cause != "engagement" and i.t - self.t_enter >= cfg.tor_timeout_s - 1e-9):
                self._go(i.t, MRM, "T09", "no takeover")
        elif s == MRM:
            if takeover:
                self._go(i.t, STANDBY, "T11", "driver intervened")
                events.append("driver_took_over")
        st = self.state
        lateral_on = st in (ACTIVE, TOR, MRM) or (st == OVERRIDE and "steer" not in self.override_kind)
        if st == TOR and self.t_enter is not None and i.t - self.t_enter > cfg.tor_assist_hold_s:
            lateral_on = False
        longitudinal_on = st in (ACTIVE, TOR, MRM) or (st == OVERRIDE and "accel" not in self.override_kind)
        return SmOutputs(st, lateral_on, longitudinal_on, st == MRM, self.override_kind, events)
