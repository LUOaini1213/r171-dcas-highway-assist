"""Driver-engagement escalation (R171 5.5.4.2) and the mode manager."""
import pytest

from dcas.engagement import DCA, EOR, EOR_ESC, HOR, NONE, UNAVAILABLE, URGENCY, EngagementMonitor
from dcas.params import BASELINE as C
from dcas.state_machine import ACTIVE, OFF, OVERRIDE, STANDBY, SmInputs, StateMachine
from vendor.p7_dms import labels as L

DT = C.dt


def run_monitor(seq, speed=120.0, hands=None, warm=5.0):
    """seq: list of (label, seconds).  Returns the first time of each level / event, counted from the end of warm-up."""
    m = EngagementMonitor(C)
    first, t = {}, 0.0
    for lab, dur in [(L.ROAD, warm)] + list(seq):
        for _ in range(round(dur / DT)):
            out = m.step(t, speed, lab, 0.1, True if hands is None else hands(t))
            for e in out.events + ([out.level] if out.level else []):
                first.setdefault(e, round(t - warm, 3))
            t += DT
    return first, m


def test_eor_escalation_chain_timing():
    """Continuous phone gaze: EOR 3.3 s, escalation +2 s, DCA +4 s, unavailable +8 s after escalation.  REQ: R171-ENG-03, R171-ENG-08, R171-ENG-09, R171-ENG-10, R171-GEN-01"""
    f, _m = run_monitor([(L.PHONE, 25.0)])
    assert f["EOR"] == pytest.approx(3.28, abs=0.021) and f["EOR"] <= 5.0
    assert f["EOR_ESC"] - f["EOR"] == pytest.approx(2.0, abs=0.021)
    assert f["DCA_EOR"] - f["EOR_ESC"] == pytest.approx(4.0, abs=0.021)
    assert f[UNAVAILABLE] - f["EOR_ESC"] == pytest.approx(8.0, abs=0.021)


def test_instrument_counts_mirror_does_not():
    """R171 5.5.4.2.5.2: the instrument panel is not relevant, mirrors are.  REQ: R171-ENG-04"""
    f, _ = run_monitor([(L.INSTRUMENT, 4.0)])
    assert "EOR" in f
    f, _ = run_monitor([(L.MIRROR, 6.0)])
    assert "EOR" not in f


def test_reengagement_needs_more_than_200ms():
    """A 0.2 s road glance does not end the disengagement; 0.4 s does.  REQ: R171-ENG-05"""
    f, _ = run_monitor([(L.PHONE, 2.0), (L.ROAD, 0.2), (L.PHONE, 1.6)])
    assert "EOR" in f                       # 2.0 + 0.2 + 1.6 counted as one glance > 3.3 s
    f, _ = run_monitor([(L.PHONE, 2.0), (L.ROAD, 0.4), (L.PHONE, 1.6)])
    assert "EOR" not in f


def test_hor_delay_only_with_eyes_on_road():
    """Hands off: HOR at 4 s when looking away, delayed to 8 s with the eyes on the road.  REQ: R171-ENG-01, R171-ENG-02"""
    f, _ = run_monitor([(L.ROAD, 30.0)], hands=lambda t: t < 5.0)
    assert f["HOR"] == pytest.approx(8.0, abs=0.03)
    assert f["HOR_ESC"] - f["HOR"] == pytest.approx(8.0, abs=0.03)
    f, _ = run_monitor([(L.OFF_ROAD, 10.0)], hands=lambda t: t < 5.0)
    assert f["HOR"] == pytest.approx(4.0, abs=0.03)


def test_message_priority():
    """One prompt at a time, ordered by urgency.  REQ: R171-HMI-03"""
    assert URGENCY[NONE] < URGENCY[HOR] < URGENCY[EOR] < URGENCY[EOR_ESC] < URGENCY[DCA] < URGENCY[UNAVAILABLE]


def test_lockout_after_three_escalations():
    """Three escalations within 30 min disable the function.  REQ: R171-ENG-12, NCAP-AD-03"""
    seq = []
    for _ in range(3):
        seq += [(L.PHONE, 5.6), (L.ROAD, 20.0)]
    _f, m = run_monitor(seq)
    assert m.lockout and len(m.escalations) == 3


def _sm_step(sm, t, **kw):
    return sm.step(SmInputs(t=t, v_kph=100.0, **kw))


def test_default_off_and_activation_preconditions():
    """Off at start; activation only by the driver and only with all preconditions.  REQ: R171-HMI-01, R171-HMI-02, R171-ENG-14"""
    sm = StateMachine(C)
    assert sm.state == OFF
    _sm_step(sm, 0.0, main_switch=False, set_pressed=True)
    assert sm.state == OFF
    _sm_step(sm, 0.1, main_switch=True)
    assert sm.state == STANDBY
    _sm_step(sm, 0.2, set_pressed=True, seatbelt=False)
    _sm_step(sm, 0.3, set_pressed=True, dsm_ok=False)
    assert sm.state == STANDBY and len(sm.refusals) == 2
    _sm_step(sm, 0.4, set_pressed=True)
    assert sm.state == ACTIVE


def test_overrides():
    """Brake cancels without auto-resume; accelerator / steering override and resume.  REQ: R171-OVR-01, R171-OVR-02, R171-OVR-03"""
    sm = StateMachine(C)
    _sm_step(sm, 0.0, set_pressed=True)
    _sm_step(sm, 0.1, accel_override=True)
    assert sm.state == OVERRIDE
    _sm_step(sm, 0.2)
    assert sm.state == ACTIVE
    _sm_step(sm, 0.3, steer_torque_nm=C.steer_override_nm + 1.0)
    assert sm.state == OVERRIDE
    for i in range(60):
        _sm_step(sm, 0.4 + i * DT)
    assert sm.state == ACTIVE
    _sm_step(sm, 2.0, brake_pedal=True)
    for i in range(50):
        _sm_step(sm, 2.1 + i * DT)
    assert sm.state == STANDBY
    _ = (DCA, EOR)
