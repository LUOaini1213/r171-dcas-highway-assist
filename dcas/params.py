"""DCAS design parameters.  Every field is either tied to a regulatory clause (PROVENANCE) or is a design
assumption (DA-xx).  Regulatory limits themselves live in dcas/regulations.py; here are the values the
function USES, which must sit inside those limits (checked in tests/test_params.py).

All values are project choices for a simulation model, not data of any real vehicle.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace

from . import regulations as R


@dataclass(frozen=True)
class DcasConfig:
    name: str = "BASELINE"
    dt: float = 0.02                      # DA-01 control / simulation step 20 ms (esmini fixed time step)
    # ------------------------------------------------------------------ longitudinal (ACC)
    gap_settings_s: tuple = (1.0, 1.4, 1.8, 2.2)   # DA-02 selectable time gaps
    gap_default_idx: int = 2              # DA-02 default 1.8 s (>= 2 s info rule: R171 5.3.7.5.1.1.2)
    d0_m: float = 5.0                     # DA-03 standstill distance
    k_gap: float = 0.25                   # DA-04 spacing-error gain (1/s2)
    k_rel: float = 0.80                   # DA-04 relative-speed gain (1/s)
    k_cruise: float = 0.40                # DA-04 cruise speed-error gain (1/s)
    a_max: float = 2.0                    # DA-05 maximum acceleration (m/s2)
    a_comfort: float = -2.5               # DA-05 comfort deceleration limit (m/s2)
    a_authority: float = -5.0             # DA-05 DCAS braking authority = R171 2.16 / Euro NCAP VA 2 (5 m/s2)
    jerk_comfort: float = 2.5             # DA-06 jerk limit in comfort mode (m/s3)
    jerk_critical: float = 10.0           # DA-06 brake build-up jerk when more than comfort braking is needed
    long_dead_time_s: float = 0.10        # DA-07 longitudinal actuator dead time
    long_tau_s: float = 0.25              # DA-07 longitudinal actuator time constant
    v_max_kph: float = 130.0              # DA-08 designed speed range upper limit (R171 5.3.7.4.3)
    lead_accel_ff: bool = False           # DA-28 use the estimated deceleration of a braking object in the
                                          #   kinematic demand (OFF in the baseline; root-cause counterfactual)
    # ------------------------------------------------------------------ cut-in / target selection
    t_pred_s: float = 1.0                 # DA-09 lateral prediction horizon for cut-in detection (TRADE-OFF)
    intrusion_m: float = 0.30             # DA-09 lane intrusion that makes an object in-path
    v_lat_min: float = 0.20               # DA-09 lateral speed towards the ego lane needed to use the prediction
    release_m: float = 0.05               # DA-09 an object is released when its intrusion drops below this
    # ------------------------------------------------------------------ perception (object list)
    obj_period_s: float = 0.05            # DA-10 object list update 20 Hz
    obj_latency_s: float = 0.10           # DA-10 object list latency
    obj_confirm_n: int = 3                # DA-10 a track is confirmed after 3 consecutive detections (150 ms)
    obj_range_m: float = 200.0            # DA-10 detection range (front)
    obj_fov_deg: float = 45.0             # DA-10 half field of view (front fusion)
    obj_visible_min: float = 0.30         # DA-10 minimum visible fraction of an object's angular extent
    sd_x_m: float = 0.15                  # DA-11 longitudinal position noise (1 sigma)
    sd_y_m: float = 0.08                  # DA-11 lateral position noise (1 sigma)
    sd_v_mps: float = 0.10                # DA-11 range-rate noise (1 sigma)
    kf_q_lat: float = 0.6                 # DA-11 lateral Kalman filter process noise (m/s2, white acceleration)
    # ------------------------------------------------------------------ lateral (lane centring)
    ay_declared: float = 2.5              # DA-12 manufacturer-declared maximum lateral acceleration (<= 3 m/s2)
    ay_ctrl_max: float = 2.8              # DA-12 LCC saturation = declared + 0.3 (R171 5.3.7.1.2 tolerance)
    jy_max: float = 4.0                   # DA-12 rate limit of the lateral-acceleration command (R171: 5 m/s3)
    ay_curve_target: float = 2.3          # DA-13 curve-speed adaptation target (>= 90 % of declared max)
    a_curve_plan: float = 1.5             # DA-13 deceleration used to plan the curve-speed profile
    lcc_wn: float = 0.9                   # DA-14 lane-centring closed-loop natural frequency (rad/s)
    lcc_zeta: float = 0.9                 # DA-14 damping
    lcc_ff_preview_s: float = 0.30        # DA-14 curvature feed-forward preview (compensates steering lag)
    steer_tau_s: float = 0.15             # DA-15 steering / tyre lag (curvature response time constant)
    wheelbase_m: float = 2.8
    # ------------------------------------------------------------------ driver engagement (R171 5.5.4.2)
    eor_s: float = 3.3                    # DA-16 EOR after 3.3 s visual disengagement (R171 <= 5.0 s)
    eor_escalate_s: float = 2.0           # DA-16 escalation 2.0 s after the EOR (R171 <= 3.0 s)
    dca_after_escalation_s: float = 4.0   # DA-16 DCA 4.0 s after the escalation (R171 <= 5.0 s)
    unavailable_after_escalation_s: float = 8.0   # DA-16 unavailability response (R171 <= 10 s)
    hor_s: float = 4.0                    # DA-17 HOR after 4 s hands off (R171 <= 5 s) ...
    hor_delay_eyes_on_s: float = 4.0      # DA-17 ... delayed by 4 s while eyes are on a relevant area (R171 <= 5 s)
    hor_escalate_s: float = 8.0           # DA-17 HOR escalation (R171 <= 10 s)
    reengage_s: float = 0.30              # DA-18 gaze on a relevant area for 0.3 s re-engages (R171 >= 0.2 s)
    redisengage_window_s: float = R.R171_EOR_REDISENGAGE_WINDOW_S
    redisengage_min_s: float = R.R171_EOR_REDISENGAGE_MIN_S
    vats_eor: bool = True                 # DA-19 repeated short aversions -> immediate EOR (R171 5.5.4.2.5.3)
    vats_window_s: float = R.ENCAP_DE_VATS_WINDOW_S
    vats_threshold_s: float = R.ENCAP_DE_VATS_CUM_S
    vats_reset_s: float = 2.0             # DA-19 continuous relevant-area gaze that ends a VATS episode
    dsm_unavailable_dca_s: float = 5.0    # DA-20 DSM not usable for 5 s -> DCA (Euro NCAP AD: deactivate <= 10 s)
    microsleep_s: float = 1.2             # DA-21 within Euro NCAP DE 1.3.3 (1-2 s)
    microsleep_gap_add_s: float = 0.6     # DA-21 time-gap increase after a microsleep (Euro NCAP AD 4.2.1)
    microsleep_gap_hold_s: float = 60.0
    sleep_s: float = R.ENCAP_DE_SLEEP_S
    unresponsive_eyes_s: float = R.ENCAP_DE_UNRESP_EYES_S
    lockout_unavailable_n: int = R.R171_LOCKOUT_UNAVAILABLE_N
    lockout_dca_n: int = R.R171_LOCKOUT_DCA_N
    lockout_escalation_n: int = R.R171_LOCKOUT_ESCALATION_N
    lockout_window_s: float = R.R171_LOCKOUT_WINDOW_S
    # ------------------------------------------------------------------ boundaries / TOR / MRM
    tor_assist_hold_s: float = 10.0       # DA-22 lateral assistance continues during a DCA (R171 5.3.7.1.4)
    tor_decel: float = 0.0                # DA-22 no automatic braking during a boundary DCA (hold speed)
    tor_timeout_s: float = 8.0            # DA-22 no takeover 8 s after a boundary DCA -> MRM (R171 <= 10 s)
    mrm_decel: float = 2.0                # DA-23 risk-mitigation stop deceleration (R79 RMF values: unverified)
    mrm_jerk: float = 2.0                 # DA-23
    steer_override_nm: float = 3.0        # DA-24 steering torque that overrides lateral control (R171 <= 50 N)
    override_release_s: float = 1.0       # DA-24 torque below threshold this long ends a steering override
    lane_marking_lost_s: float = 0.5      # DA-25 markings lost this long -> boundary reached


BASELINE = DcasConfig()
# Fixes found by the root-cause analysis (scripts/root_cause.py), applied before the trade-off study:
#   lead_accel_ff  RC1: the kinematic demand ignored a braking lead (Euro NCAP VA CCRb at the closest gap collided)
#   a_curve_plan   RC4: the curve-speed profile used the controller's own deceleration limit (no margin for lag)
FIXES = dict(lead_accel_ff=True, a_curve_plan=1.0)


def config(**kw) -> DcasConfig:
    return replace(BASELINE, **kw)


PROVENANCE: dict[str, str] = {
    "name": "-",
    "dt": "DA-01 20 ms 控制/仿真步长（esmini 固定步长）",
    "gap_settings_s": "DA-02 时距档位 1.0/1.4/1.8/2.2 s；R171 5.3.7.5.1.1 要求显示当前时距、<2 s 时提示",
    "gap_default_idx": "DA-02 默认 1.8 s（低于 2 s，按 R171 5.3.7.5.1.1.2 需在首次激活时提示）",
    "d0_m": "DA-03 停车间距 5 m",
    "k_gap": "DA-04 定时距跟车律：间距误差增益",
    "k_rel": "DA-04 相对速度增益",
    "k_cruise": "DA-04 定速巡航速度误差增益",
    "a_max": "DA-05 最大加速度 2.0 m/s²（ISO 15622 的舒适限值未查阅原文）",
    "a_comfort": "DA-05 舒适减速度 2.5 m/s²；R171 5.3.6.3.1 要求加减速度对驾驶员和周围交通可控",
    "a_authority": "DA-05 = R171 2.16（5 m/s² 以上属“即将碰撞”）与 Euro NCAP VA 第 2 章（ACC 只评价 ≤5 m/s²）",
    "jerk_comfort": "DA-06 舒适模式冲击度 2.5 m/s³",
    "jerk_critical": "DA-06 需要超过舒适减速度时的制动建立冲击度 10 m/s³",
    "long_dead_time_s": "DA-07 纵向执行器纯延迟 0.10 s",
    "long_tau_s": "DA-07 纵向执行器一阶时间常数 0.25 s",
    "v_max_kph": "DA-08 设计车速上限 130 km/h（R171 5.3.7.4.3 只在设计车速范围内提供辅助）",
    "lead_accel_ff": "DA-28 运动学需求考虑前车减速度（基线关闭；根因分析的反事实开关）",
    "t_pred_s": "DA-09 切入预测时域 1.0 s（权衡参数，见 scripts/tradeoff.py）",
    "intrusion_m": "DA-09 侵入本车道 0.30 m 视为路径内目标",
    "v_lat_min": "DA-09 朝本车道横向速度 ≥0.20 m/s 才使用预测",
    "release_m": "DA-09 侵入量 <0.05 m 释放目标",
    "obj_period_s": "DA-10 目标列表 20 Hz",
    "obj_latency_s": "DA-10 目标列表时延 0.10 s",
    "obj_confirm_n": "DA-10 连续 3 帧检测确认航迹（150 ms）",
    "obj_range_m": "DA-10 前向探测距离 200 m",
    "obj_fov_deg": "DA-10 前向融合半视场角 45°",
    "obj_visible_min": "DA-10 目标角宽可见比例 ≥30 % 才可检测（遮挡模型）",
    "sd_x_m": "DA-11 纵向位置噪声 σ 0.15 m",
    "sd_y_m": "DA-11 横向位置噪声 σ 0.08 m",
    "sd_v_mps": "DA-11 距离变化率噪声 σ 0.10 m/s",
    "kf_q_lat": "DA-11 横向卡尔曼滤波过程噪声",
    "ay_declared": "DA-12 申报最大横向加速度 2.5 m/s²（R171 5.3.7.1.2：M1 ≤3 m/s²）",
    "ay_ctrl_max": "DA-12 车道居中饱和值 = 申报值 + 0.3（R171 5.3.7.1.2 允许超出 ≤0.3 m/s²）",
    "jy_max": "DA-12 横向加速度指令变化率 4 m/s³（R171 5.3.7.1.2.1：0.5 s 滑动平均 ≤5 m/s³）",
    "ay_curve_target": "DA-13 弯道限速目标 2.3 m/s²（≥申报值 90 %，使 R171 附件 4 4.2.5.1.1.1.1 基础试验保持恒速）",
    "a_curve_plan": "DA-13 弯道限速规划减速度 1.5 m/s²（R171 5.3.7.1.1.1 要求能按曲率调整车速）",
    "lcc_wn": "DA-14 车道居中闭环自然频率 0.9 rad/s",
    "lcc_zeta": "DA-14 阻尼比 0.9",
    "lcc_ff_preview_s": "DA-14 曲率前馈预瞄 0.3 s",
    "steer_tau_s": "DA-15 转向/轮胎滞后 0.15 s",
    "wheelbase_m": "DA-15 轴距 2.8 m",
    "eor_s": "DA-16 视觉脱离 3.3 s 发 EOR（R171 5.5.4.2.6.2.1 ≤5 s；与 P7 的 ADDW/Euro NCAP 长时分心阈值一致）",
    "eor_escalate_s": "DA-16 EOR 后 2.0 s 升级（R171 5.5.4.2.6.2.3 ≤3 s）",
    "dca_after_escalation_s": "DA-16 升级后 4.0 s 发 DCA（R171 5.5.4.2.6.3.1 ≤5 s）",
    "unavailable_after_escalation_s": "DA-16 首次升级后 8.0 s 启动驾驶员不可用响应（R171 5.5.4.2.6.4.1 ≤10 s）",
    "hor_s": "DA-17 脱手 4 s 发 HOR（R171 5.5.4.2.6.1.1 >5 s 时最迟发出）",
    "hor_delay_eyes_on_s": "DA-17 视线在相关区域时 HOR 推迟 4 s（R171 允许推迟 ≤5 s）",
    "hor_escalate_s": "DA-17 HOR 后 8 s 升级（R171 5.5.4.2.6.1.2 ≤10 s）",
    "reengage_s": "DA-18 视线回到相关区域 0.3 s 视为重新投入（R171 5.5.4.2.5.2.1 ≥200 ms）",
    "redisengage_window_s": "R171 5.5.4.2.6.2.2（EOR 确认后 2 s 内再次脱离 ≥1 s → 立即 EOR）",
    "redisengage_min_s": "R171 5.5.4.2.6.2.2",
    "vats_eor": "DA-19 多次短时脱离（Euro NCAP DE VATS：30 s 内累计 10 s）→ 立即 EOR（R171 5.5.4.2.5.3 要求有对策）",
    "vats_window_s": "Euro NCAP DE v1.2 §1.2.2",
    "vats_threshold_s": "Euro NCAP DE v1.2 §1.2.2",
    "vats_reset_s": "DA-19 连续 2 s 注视相关区域结束一轮累计（沿用 P7 DA-06）",
    "dsm_unavailable_dca_s": "DA-20 DMS 不可用 5 s → DCA 并退出（Euro NCAP AD 2.3.2.1：≤10 s 退出）",
    "microsleep_s": "DA-21 微睡眠 1.2 s（Euro NCAP DE 1.3.3：1–2 s）",
    "microsleep_gap_add_s": "DA-21 微睡眠后时距 +0.6 s（Euro NCAP AD 4.2.1：报警并加大 ACC 时距）",
    "microsleep_gap_hold_s": "DA-21 加大时距保持 60 s",
    "sleep_s": "Euro NCAP DE 1.3.4（闭眼 ≥3 s）→ 直接 DCA（设计）",
    "unresponsive_eyes_s": "Euro NCAP DE 1.3.5（闭眼 ≥6 s）→ 风险减缓停车（Euro NCAP AD 4.2.3）",
    "lockout_unavailable_n": "R171 5.5.4.2.8.2 (a)",
    "lockout_dca_n": "R171 5.5.4.2.8.2 (b)",
    "lockout_escalation_n": "R171 5.5.4.2.8.2 (c)；Euro NCAP AD 2.3.2.3 锁止加分（30 min 内 [3] 次）",
    "lockout_window_s": "R171 5.5.4.2.8.2 (c) 30 min 滚动窗口",
    "tor_assist_hold_s": "DA-22 DCA 期间继续横向辅助（R171 5.3.7.1.4 避免转向辅助突然消失）",
    "tor_decel": "DA-22 边界 DCA 期间不主动制动（保持车速，由驾驶员接管）",
    "tor_timeout_s": "DA-22 边界 DCA 后 8 s 无人接管 → 风险减缓停车（R171 5.5.4.2.6.4.1 ≤10 s）",
    "mrm_decel": "DA-23 风险减缓停车减速度 2.0 m/s²（R171 5.3.7.3.1 引用 R79 04 系列 RMF，原文数值未核实）",
    "mrm_jerk": "DA-23 风险减缓停车冲击度 2.0 m/s³",
    "steer_override_nm": "DA-24 转向超越扭矩 3.0 N·m（约合 0.19 m 盘缘 16 N，R171 5.5.3.4.1.4 ≤50 N）",
    "override_release_s": "DA-24 扭矩低于阈值 1.0 s 结束转向超越",
    "lane_marking_lost_s": "DA-25 车道线丢失 0.5 s 视为到达系统边界",
}


def parameter_rows(cfg: DcasConfig = BASELINE) -> list[dict]:
    rows = []
    for f in fields(cfg):
        prov = PROVENANCE.get(f.name, "?")
        kind = "-" if prov == "-" else ("设计假设" if prov.startswith("DA-") else "法规/规程")
        rows.append({"parameter": f.name, "value": getattr(cfg, f.name), "provenance": prov, "kind": kind})
    return rows
