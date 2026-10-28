"""Regulatory / protocol numbers - every value carries its source clause.

Documents actually read for this project (2026-10-28):

R171   UN Regulation No. 171 (DCAS), consolidated text "Incorporating all valid text up to: 01 series of
       amendments - Date of entry into force: 26 September 2025", OJ L 2025/1899 (26.9.2025),
       https://eur-lex.europa.eu/eli/reg/2025/1899/oj/eng .  The page states that the authentic text is
       ECE/TRANS/WP.29/2025/7 as amended by paragraph 64 of report ECE/TRANS/WP.29/1184.
       unece.org returned HTTP 403 to the fetch tool, so the UNECE PDF itself was not compared word by word.
       Status (UN Treaty Collection depositary notifications, treaties.un.org, chapter XI.B.16.171):
         original                 in force 22 Sep 2024   C.N.392.2024
         WP.29/2024/146           binding 12 Jun 2025    C.N.351.2025
         WP.29/2025/7 (01 series) binding 26 Sep 2025    C.N.539.2025
         WP.29/2025/65            binding 11 Jan 2026    C.N.48.2026
         WP.29/2025/143           binding  4 Jun 2026    C.N.238.2026
         WP.29/2025/144           binding  4 Jun 2026    C.N.239.2026  (Supplement 1 to the 01 series)
       The texts of 2025/65, 2025/143 and 2025/144 were NOT read (unece.org blocked); a secondary source
       (globalautoregs.com) describes 2025/143 and 2025/144 as adding an Annex 6 on DETA data exchange.
       A 02 series (WP.29/2026/86) is reported as adopted in June 2026 but not yet in force (unverified).
ENCAP_AD  Euro NCAP "Assisted Driving - Highway & Interurban Assist Systems Protocol" v1.2, July 2026,
       implementation January 2026, cdn.euroncap.com/cars/assets/Euro_NCAP_Protocol_Assisted_Driving_v1_2_7150e4e41e.pdf
       (SHA-256 of the copy read 98c2ce70e82f45200a7b4eb917ff7d7658344f00047e992306f124895d92cdd9).
ENCAP_VA  Euro NCAP "Safe Driving - Vehicle Assistance Protocol" v1.2, July 2026,
       cdn.euroncap.com/cars/assets/Euro_NCAP_Protocol_Safe_Driving_Vehicle_Assistance_v1_2_b6fb486fa6.pdf
       (SHA-256 196583ce2eee0516b0f259413fd1b1937ec5d539ffb23fcd80b7604a11c8ed2a).
ENCAP_DE  Euro NCAP "Safe Driving - Driver Engagement Protocol" v1.2 (July 2026) - numbers taken over from the
       copied P7 module vendor/p7_dms/regulations.py (where they carry their clauses).

Printed page numbers of the Euro NCAP PDFs are used.  Anything not in these documents is a design
assumption and lives in dcas/params.py with a DA-xx tag.
"""
from __future__ import annotations

R171_SRC = "UN R171 01 series (OJ L 2025/1899)"
ENCAP_AD_SRC = "Euro NCAP AD v1.2 (2026-07)"
ENCAP_VA_SRC = "Euro NCAP VA v1.2 (2026-07)"
ENCAP_DE_SRC = "Euro NCAP DE v1.2 (2026-07)"

# =============================================================== UN R171, 01 series
R171_IMMINENT_DECEL_MPS2 = 5.0          # 2.16 risk of imminent collision: not avoidable with a demand < 5 m/s2
R171_LAT_ACC_MAX_M1 = 3.0               # 5.3.7.1.2 specified max lateral acceleration <= 3 m/s2 (M1/N1)
R171_LAT_ACC_TOL = 0.3                  # 5.3.7.1.2 may exceed the specified value by <= 0.3 m/s2 (not above 3)
R171_LAT_ACC_SHORT_FACTOR = 0.40        # 5.3.7.1.2 for <= 2 s: specified value + 40 %, capped at 3 + 0.3
R171_LAT_ACC_SHORT_S = 2.0
R171_LAT_JERK_MAX = 5.0                 # 5.3.7.1.2.1 0.5 s moving average of lateral jerk <= 5 m/s3
R171_LAT_JERK_WINDOW_S = 0.5
R171_STEER_OVERRIDE_MAX_N = 50.0        # 5.5.3.4.1.4 steering control effort to override <= 50 N
R171_BRAKE_RESUME_DV_KPH = 30.0         # 5.5.3.4.1.1.1 may resume if driver braking reduced speed <= 30 km/h ...
R171_BRAKE_RESUME_WINDOW_S = 2.0        # ... within 2 s
R171_HEADWAY_INFO_S = 2.0               # 5.3.7.5.1.1.2 inform the driver if the headway setting is < 2 s
R171_WARN_MIN_SPEED_KPH = 10.0          # 5.5.4.2.6.1.1 / 5.5.4.2.6.2.1 "at speeds above 10 km/h"
R171_HOR_HANDS_OFF_S = 5.0              # 5.5.4.2.6.1.1 HOR at the latest when hands off for more than 5 s
R171_HOR_DELAY_MAX_S = 5.0              # 5.5.4.2.6.1.1 HOR may be delayed up to 5 s if not visually disengaged
R171_HOR_ESCALATE_S = 10.0              # 5.5.4.2.6.1.2 escalate at the latest 10 s after the initial HOR
R171_EOR_S = 5.0                        # 5.5.4.2.6.2.1 EOR at the latest after 5 s of visual disengagement
R171_EOR_REDISENGAGE_WINDOW_S = 2.0     # 5.5.4.2.6.2.2 disengaged again for >= 1 s within the following 2 s
R171_EOR_REDISENGAGE_MIN_S = 1.0        #   -> EOR immediately
R171_EOR_ESCALATE_S = 3.0               # 5.5.4.2.6.2.3 escalate at the latest 3 s after the initial EOR
R171_DCA_AFTER_ESCALATION_S = 5.0       # 5.5.4.2.6.3.1 DCA at the latest 5 s after the escalation of the EOR
R171_UNAVAILABLE_AFTER_S = 10.0         # 5.5.4.2.6.4.1 unavailability response at the latest 10 s after the
                                        #   first escalated request or DCA
R171_REENGAGE_MIN_S = 0.2               # 5.5.4.2.5.2.1 re-engaged after >= 200 ms gaze on a relevant area
R171_HANDS_OFF_MAX_KPH = 130.0          # 5.5.4.2.6.5 HORs may be withheld on a highway up to 130 km/h
R171_HANDS_OFF_EOR_TABLE = ((10.0, 5.0), (60.0, 5.0), (130.0, 3.5))   # 5.5.4.2.6.5.4 (linear 60-130 km/h)
R171_HOR_BEFORE_BOUNDARY_S = 5.0        # 5.5.4.2.6.5.1 (only while HORs are withheld)
R171_DCA_REACTION_MIN_S = 1.0           # 5.3.6.1.1 reaction to a DCA never assumed < 1 s (HORs withheld)
R171_EOR_BLOCKS_MANOEUVRE_S = 7.0       # 5.3.7.2.4.2 no system-initiated manoeuvre within 7 s after an EOR
R171_LOCKOUT_MIN_S = 1800.0             # 5.5.4.2.8.1 disabled for >= 30 min when engagement is insufficient
R171_LOCKOUT_UNAVAILABLE_N = 1          # 5.5.4.2.8.2 (a) one unavailability response initiation
R171_LOCKOUT_DCA_N = 2                  # 5.5.4.2.8.2 (b) at most 2 DCAs due to prolonged insufficient engagement
R171_LOCKOUT_ESCALATION_N = 3           # 5.5.4.2.8.2 (c) at most 3 escalations ...
R171_LOCKOUT_WINDOW_S = 1800.0          #   ... in a rolling 30 min window
# Driving-task relevant areas (5.5.4.2.5.2): "the dashboard and instrument panel shall not be considered as a
# driving task relevant area" - unlike Euro NCAP DE, which treats the instrument cluster as a driving task.

# Annex 4 physical tests (scenario definitions used in dcas/scenarios.py)
R171_PRE_TEST_STRAIGHT_S = 2.0          # 4.2.5.2.x.1.1 straight line >= 2 s before the functional part
R171_CUTIN_T1 = dict(v_vut_kph=50.0, v_gvt_kph=10.0, lat_acc=0.5, lc_len_m=14.0, radius_m=15.0, ttc_s=0.0)   # 4.2.5.2.6.1
R171_CUTIN_T2 = dict(v_vut_kph=120.0, v_gvt_kph=70.0, lat_acc=1.5, lc_len_m=60.0, radius_m=250.0, ttc_s=1.5)  # 4.2.5.2.6.1
# 4.2.5.2.6.1.2: TTC at the instant the target has finished the lane change (rear centre in the middle of
# the VUT lane).  Annex 4 2.1: TTC = longitudinal distance / longitudinal relative speed.
R171_CUTOUT = dict(v_vut_kph=70.0, v_lead_kph=50.0, lat_acc=1.5, lc_len_m=44.0, radius_m=130.0, ttc_s=3.0)    # 4.2.5.2.5.1
# 4.2.5.2.5.1.2: TTC of the lead vehicle to the stationary target when the lead starts its lane change.
R171_DECEL_LEAD = dict(v_kph=50.0, decel_mps2=4.0)                       # 4.2.5.2.4.1 (steady-state following)
R171_SLOWER_VEHICLE_DV_KPH = 50.0                                        # 4.2.5.2.3.1.2
R171_POS_BASE_AY_FRACTION = (0.80, 0.90)                                 # 4.2.5.1.1.1.1 80-90 % of declared max
R171_POS_PROVOKE_AY_MARGIN = 0.3                                         # 4.2.5.1.1.1.2 > declared max + 0.3 m/s2
R171_CAPABILITY_SHARE = 0.90            # Annex 3 Appendix 4: capability shown in >= 90 % of corresponding tests
R171_BASE_TEST_RUNS = 2                 # Annex 4 3.1.6.2: base tests at least 2 times (one repeat allowed)

# =============================================================== Euro NCAP Assisted Driving v1.2
ENCAP_AD_DSM_DEACTIVATE_S = 10.0        # 2.3.2.1: AD deactivated <= 10 s after DSM becomes non-functional
ENCAP_AD_LONG_DISTRACTION_RELAX = 1.5   # 2.3.2.2: long-distraction thresholds relaxed by <= 150 % (3 s -> 4.5 s)
ENCAP_AD_LOCKOUT_N = 3                  # 2.3.2.3 bonus: lock-out after [3] repetitive distractions ...
ENCAP_AD_LOCKOUT_WINDOW_S = 1800.0      #   ... in a window not greater than 30 min (bracketed = provisional)
ENCAP_AD_TTC_ODD_S = 3.0                # 2.3.2.2: ODD-dependent strategy, e.g. TTC <= [3] s to vehicle ahead
ENCAP_AD_CUTIN = (dict(v_vut_kph=50.0, v_gvt_kph=10.0, ttc_s=-1.5), dict(v_vut_kph=120.0, v_gvt_kph=70.0, ttc_s=0.5))  # 4.3.1
ENCAP_AD_CUTOUT = (dict(v_vut_kph=70.0, v_lead_kph=50.0, ttc_s=2.0), dict(v_vut_kph=90.0, v_lead_kph=70.0, ttc_s=2.0))  # 4.3.1
ENCAP_AD_GRADES = (("VERY GOOD", 160), ("GOOD", 140), ("MODERATE", 120), ("ENTRY", 100))   # 1.2

# =============================================================== Euro NCAP Vehicle Assistance v1.2
ENCAP_VA_ACC_DECEL_MAX = 5.0            # 2: ACC capability assessed with deceleration <= 5 m/s2 ...
ENCAP_VA_ACC_DECEL_TOL = 0.10           #   ... +10 % tolerance over a running average of 500 ms
ENCAP_VA_ACC_DECEL_WINDOW_S = 0.5
ENCAP_VA_CUTIN = (dict(v_vut_kph=50.0, v_gvt_kph=10.0, lat_acc=0.5, lc_len_m=14.5, radius_m=15.0, ttc_s=0.0),
                  dict(v_vut_kph=120.0, v_gvt_kph=70.0, lat_acc=1.5, lc_len_m=60.0, radius_m=250.0, ttc_s=1.5))  # 2.1.4
ENCAP_VA_CUTOUT = (dict(v_vut_kph=70.0, v_lead_kph=50.0, lat_acc=1.5, lc_len_m=44.0, radius_m=130.0, ttc_s=3.0),
                   dict(v_vut_kph=90.0, v_lead_kph=70.0, lat_acc=1.5, lc_len_m=60.0, radius_m=250.0, ttc_s=3.0))  # 2.1.5
ENCAP_VA_CCRB = dict(v_vut_kph=55.0, v_gvt_kph=50.0, decel_mps2=4.0)    # 2.1.3, ACC set to closest distance
ENCAP_VA_ORANGE_DV_KPH = 15.0           # colour table p.15: orange = speed reduction > 15 km/h, grey <= 15

# =============================================================== Euro NCAP Driver Engagement (via P7 copy)
ENCAP_DE_LONG_DISTRACTION_S = (3.0, 4.0)  # DE 1.2.1 (P7: ENCAP_LGA_RANGE_S)
ENCAP_DE_VATS_CUM_S = 10.0                # DE 1.2.2 cumulative 10 s ...
ENCAP_DE_VATS_WINDOW_S = 30.0             #   ... in a 30 s window
ENCAP_DE_MICROSLEEP_S = (1.0, 2.0)        # DE 1.3.3
ENCAP_DE_SLEEP_S = 3.0                    # DE 1.3.4
ENCAP_DE_UNRESP_EYES_S = 6.0              # DE 1.3.5


def r171_hands_off_eor_s(v_kph: float) -> float:
    """5.5.4.2.6.5.4: latest EOR timing while HORs are withheld (5.0 s at 10-60 km/h, 3.5 s at 130 km/h,
    linear in between).  Outside 10-130 km/h the table does not apply (None is not returned: callers clamp)."""
    (v0, t0), (v1, t1), (v2, t2) = R171_HANDS_OFF_EOR_TABLE
    if v_kph <= v1:
        return t1
    if v_kph >= v2:
        return t2
    return t1 + (t2 - t1) * (v_kph - v1) / (v2 - v1)


def r171_lat_acc_limits(declared: float) -> tuple[float, float]:
    """(sustained limit, <= 2 s limit) for a declared maximum lateral acceleration (5.3.7.1.2)."""
    sustained = min(declared + R171_LAT_ACC_TOL, R171_LAT_ACC_MAX_M1)        # "... while not exceeding 3 m/s2"
    short = min(declared * (1.0 + R171_LAT_ACC_SHORT_FACTOR), R171_LAT_ACC_MAX_M1 + R171_LAT_ACC_TOL)
    return sustained, max(short, sustained)
