"""Regulatory numbers and the design values that must sit inside them."""
import pytest

from dcas import regulations as R
from dcas.params import BASELINE as C
from dcas.evaluate import HARSH_DECEL, LAT_SHORT_LIMIT, MAX_DECEL_500MS, MIN_TTC_S


def test_r171_hands_off_eor_table():
    """5.5.4.2.6.5.4: 5.0 s at 10-60 km/h, 3.5 s at 130 km/h, linear in between.  REQ: R171-ENG-03"""
    assert R.r171_hands_off_eor_s(30) == 5.0 and R.r171_hands_off_eor_s(60) == 5.0
    assert R.r171_hands_off_eor_s(130) == 3.5
    assert R.r171_hands_off_eor_s(95) == pytest.approx(4.25)


def test_r171_lateral_acceleration_limits():
    """5.3.7.1.2: declared 2.5 -> sustained 2.8, <= 2 s 3.3; declared 3.0 -> 3.0 / 3.3.  REQ: R171-LAT-02"""
    assert R.r171_lat_acc_limits(2.5) == pytest.approx((2.8, 3.3))
    assert R.r171_lat_acc_limits(3.0) == pytest.approx((3.0, 3.3))
    assert LAT_SHORT_LIMIT == pytest.approx(3.3)


def test_engagement_design_values_inside_r171():
    """Design timings are inside the R171 maxima.  REQ: R171-ENG-01, R171-ENG-02, R171-ENG-03, R171-ENG-05, R171-ENG-08, R171-ENG-09, R171-ENG-10"""
    assert C.eor_s <= R.R171_EOR_S
    assert C.eor_escalate_s <= R.R171_EOR_ESCALATE_S
    assert C.dca_after_escalation_s <= R.R171_DCA_AFTER_ESCALATION_S
    assert C.unavailable_after_escalation_s <= R.R171_UNAVAILABLE_AFTER_S
    assert C.hor_s <= R.R171_HOR_HANDS_OFF_S and C.hor_delay_eyes_on_s <= R.R171_HOR_DELAY_MAX_S
    assert C.hor_escalate_s <= R.R171_HOR_ESCALATE_S
    assert C.reengage_s >= R.R171_REENGAGE_MIN_S
    assert C.tor_timeout_s <= R.R171_UNAVAILABLE_AFTER_S


def test_lateral_and_longitudinal_design_values():
    """ay declared <= 3, LCC saturation <= declared + 0.3, jerk rate <= 5, authority = 5 m/s2.  REQ: R171-LAT-02, R171-LON-06"""
    assert C.ay_declared <= R.R171_LAT_ACC_MAX_M1
    assert C.ay_ctrl_max <= R.r171_lat_acc_limits(C.ay_declared)[0] + 1e-9
    assert C.jy_max <= R.R171_LAT_JERK_MAX
    assert C.a_authority == -R.R171_IMMINENT_DECEL_MPS2 == -R.ENCAP_VA_ACC_DECEL_MAX


def test_ncap_ad_values():
    """EOR threshold within 150 % of the 3 s baseline; DSM fallback <= 10 s; lock-out after 3.  REQ: NCAP-AD-02, NCAP-AD-01, NCAP-AD-03"""
    assert C.eor_s <= R.ENCAP_DE_LONG_DISTRACTION_S[0] * R.ENCAP_AD_LONG_DISTRACTION_RELAX
    assert C.dsm_unavailable_dca_s <= R.ENCAP_AD_DSM_DEACTIVATE_S
    assert C.lockout_escalation_n == R.ENCAP_AD_LOCKOUT_N == R.R171_LOCKOUT_ESCALATION_N


def test_steering_override_threshold_below_50N():
    """3 N.m at an assumed 0.19 m rim radius is about 16 N < 50 N.  REQ: R171-OVR-03"""
    assert C.steer_override_nm / 0.19 <= R.R171_STEER_OVERRIDE_MAX_N


def test_pass_fail_criteria_fixed():
    """The criteria constants used for every verdict.  REQ: PRJ-01, NCAP-VA-01"""
    assert (MIN_TTC_S, MAX_DECEL_500MS, HARSH_DECEL) == (1.0, pytest.approx(5.5), 3.5)
