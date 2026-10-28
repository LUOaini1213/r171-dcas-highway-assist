"""ACC, lane centring, perception helpers."""
import pytest

from dcas.acc import Acc, intrusion
from dcas.backends import PythonBackend
from dcas.closed_loop import run_case
from dcas.lcc import LaneCentering
from dcas.params import BASELINE, config
from dcas.perception import Track, visible_fractions
from dcas.road import EGO_LANE, curve_road, lane_center_t, straight_road
from dcas.scenarios import case_index


def test_steady_following_gap():
    """Steady following holds d0 + tau v within 1 m.  REQ: R171-LON-05"""
    r = run_case(case_index()["FN-09-follow-steady"], PythonBackend())
    g_des = BASELINE.d0_m + 1.8 * 100 / 3.6
    assert abs(r.min_gap_m - g_des) < 1.0 and not r.collision


def test_acc_authority_and_jerk_limit():
    """Braking never beyond 5 m/s2; the command obeys the jerk limit.  REQ: R171-LON-06, NCAP-VA-01"""
    acc = Acc(BASELINE, straight_road(), lane_center_t(EGO_LANE))
    tr = Track("x", gap=15.0, v_rel=-15.0, v_obj=15.0, y=0.0, width=1.8, confirmed=True)
    prev = 0.0
    out = None
    for _ in range(100):
        out = acc.step([tr], 30.0, 0.0, 0.0, 33.0)
        assert out.a_cmd >= BASELINE.a_authority - 1e-9
        assert out.a_cmd - prev >= -BASELINE.jerk_critical * BASELINE.dt - 1e-9
        prev = out.a_cmd
    assert out.mode == "critical" and out.a_cmd == pytest.approx(-5.0)


def test_lane_centring_limits():
    """|a_y command| <= declared + 0.3 and its rate <= jy_max.  REQ: R171-LAT-02, R171-LAT-03"""
    lcc = LaneCentering(BASELINE, curve_road(250.0), lane_center_t(EGO_LANE))
    prev = 0.0
    for s in range(600, 900):
        k = lcc.step(float(s), 0.3, 0.0, 36.0)
        ay = k * 36.0 ** 2
        assert abs(ay) <= BASELINE.ay_ctrl_max + 1e-9
        assert abs(ay - prev) <= BASELINE.jy_max * BASELINE.dt + 1e-9
        prev = ay


def test_occlusion_model():
    """A nearer object of the same width hides the farther one; a lateral shift reveals part of it.  REQ: R171-LON-02"""
    hid = visible_fractions([("lead", 15.0, 19.0, -0.9, 0.9), ("stat", 45.0, 49.0, -0.9, 0.9)], 0.0)
    assert hid["stat"] == pytest.approx(0.0)
    shifted = visible_fractions([("lead", 15.0, 19.0, 0.0, 1.8), ("stat", 45.0, 49.0, -0.9, 0.9)], 0.0)
    assert shifted["stat"] == pytest.approx(0.5, abs=0.01)


def test_cut_in_prediction_and_release():
    """Prediction selects an approaching object early; t_pred = 0 waits for 0.3 m intrusion.  REQ: R171-LON-01"""
    tr = Track("t", gap=30.0, v_rel=-5.0, v_obj=25.0, y=-3.3, vy=1.0, width=1.8, confirmed=True)
    assert intrusion(tr) == pytest.approx(1.75 - (3.3 - 0.9))
    on = Acc(config(t_pred_s=1.0), straight_road(), lane_center_t(EGO_LANE))
    off = Acc(config(t_pred_s=0.0), straight_road(), lane_center_t(EGO_LANE))
    assert [t.oid for t in on.select([tr])] == ["t"] and off.select([tr]) == []
    tr.y = -2.4                      # intrusion 0.25 m: kept by hysteresis, then released below 0.05 m
    assert [t.oid for t in on.select([tr])] == ["t"]
    tr.y, tr.vy = -2.7, -0.5
    assert on.select([tr]) == []


def test_lead_braking_feedforward_counterfactual():
    """RC1 fix: with the braking-lead term the Euro NCAP VA CCRb point (closest gap) no longer collides.  REQ: NCAP-VA-04, R171-LON-03"""
    c = case_index()["OFF-LB-NCAPVA"]
    base = run_case(c, PythonBackend())
    fix = run_case(c, PythonBackend(), config(lead_accel_ff=True))
    assert base.collision and not fix.collision
