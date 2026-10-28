"""Requirement checks on run results -> rows of results/checks.csv (req_id, case_id, item, measured, limit, verdict).

Timing checks compare the measured times with the R171 maxima (dcas/regulations.py), not with the design
values: a design value inside the limit is the margin.  Times are decision times of the 20 ms task.
"""
from __future__ import annotations

from collections import defaultdict

from . import regulations as R
from .evaluate import MAX_DECEL_500MS, MIN_TTC_S, HARSH_DECEL, LAT_JERK_MAX, LAT_SHORT_LIMIT, LAT_SHORT_S, is_safe
from .params import BASELINE

OK, NOK, INFO = "通过", "不通过", "信息"


def _row(rid, cid, item, measured, limit, ok, note=""):
    verdict = INFO if ok is None else (OK if ok else NOK)
    return {"req_id": rid, "case_id": cid, "item": item, "measured": measured, "limit": limit, "verdict": verdict,
            "note": note}


def _first(r, name):
    return r.first(name)


def _tids(r):
    return [tid for _t, _a, _b, tid, _d in r.transitions]


def _tr(r, tid):
    return next(((t, a, b, d) for t, a, b, x, d in r.transitions if x == tid), None)


def _f(x, nd=2):
    return "-" if x is None else f"{x:.{nd}f}"


def engagement_checks(res: dict) -> list[dict]:
    """res: case_id -> RunResult for the engagement and functional suites."""
    rows = []
    g = res.get
    # ---------------------------------------------------------------- EG-01 mirror glances
    r = g("EG-01-attentive")
    if r:
        n = sum(1 for _t, e in r.events if e in ("EOR", "HOR"))
        rows.append(_row("R171-ENG-04", r.case_id, "后视镜注视（相关区域）不触发请求", f"EOR/HOR 次数 {n}", "0", n == 0))
        rows.append(_row("R171-GEN-01", r.case_id, "专注驾驶时无误报", f"请求次数 {n}", "0", n == 0))
    # ---------------------------------------------------------------- EG-02 instrument panel
    r = g("EG-02-instrument-4s")
    if r:
        t = _first(r, "EOR")
        lat = None if t is None else t - 10.0
        rows.append(_row("R171-ENG-04", r.case_id, "注视仪表板 4 s 计为视觉脱离", f"EOR 在脱离后 {_f(lat)} s", "出现 EOR", t is not None))
        rows.append(_row("R171-ENG-03", r.case_id, "EOR 时刻", f"{_f(lat)} s", f"≤ {R.R171_EOR_S} s", lat is not None and lat <= R.R171_EOR_S))
    # ---------------------------------------------------------------- EG-03 single phone glance
    r = g("EG-03-phone-4s")
    if r:
        t, tc = _first(r, "EOR"), _first(r, "EOR_confirmed")
        lat = None if t is None else t - 10.0
        rows.append(_row("R171-ENG-03", r.case_id, "EOR 时刻（手机 4 s）", f"{_f(lat)} s", f"≤ {R.R171_EOR_S} s", lat is not None and lat <= R.R171_EOR_S))
        rows.append(_row("NCAP-AD-02", r.case_id, "辅助模式长时分心报警阈值", f"{_f(lat)} s",
                         f"≤ {R.ENCAP_DE_LONG_DISTRACTION_S[0] * R.ENCAP_AD_LONG_DISTRACTION_RELAX:.1f} s（3 s 基准 ×150 %）",
                         lat is not None and lat <= R.ENCAP_DE_LONG_DISTRACTION_S[0] * R.ENCAP_AD_LONG_DISTRACTION_RELAX))
        conf = None if tc is None else tc - 14.0
        rows.append(_row("R171-ENG-05", r.case_id, "视线回到道路后到确认 EOR 的时间", f"{_f(conf)} s", f"≥ {R.R171_REENGAGE_MIN_S} s",
                         conf is not None and conf >= R.R171_REENGAGE_MIN_S - 1e-9))
        rows.append(_row("R171-GEN-01", r.case_id, "单次长时分心被提示", f"EOR {_f(t)} s", "出现 EOR", t is not None))
    # ---------------------------------------------------------------- EG-04 VATS
    r = g("EG-04-vats")
    if r:
        t = _first(r, "EOR_vats")
        rows.append(_row("R171-ENG-07", r.case_id, "多次短时偏离（每次 2.4 s < EOR 阈值 3.3 s）触发 EOR",
                         f"EOR(VATS) {_f(t)} s", "出现，且早于任何单次注视达到 EOR 阈值", t is not None))
    # ---------------------------------------------------------------- EG-05 re-disengagement
    r = g("EG-05-redisengage")
    if r:
        t = _first(r, "EOR_redisengage")
        tc = _first(r, "EOR_confirmed")
        gap = None if tc is None else 14.2 - tc
        lat = None if t is None else t - 14.2
        rows.append(_row("R171-ENG-06", r.case_id, "确认后再次脱离开始的间隔 / 再次 EOR 的时刻",
                         f"间隔 {_f(gap)} s，再次脱离 {_f(lat)} s 后 EOR",
                         f"间隔 ≤ {R.R171_EOR_REDISENGAGE_WINDOW_S} s 时，脱离满 {R.R171_EOR_REDISENGAGE_MIN_S} s 立即 EOR",
                         t is not None and lat is not None and lat <= R.R171_EOR_REDISENGAGE_MIN_S + BASELINE.dt + 1e-9))
    # ---------------------------------------------------------------- EG-06 full escalation (EOR chain)
    for cid in ("EG-06-unresponsive", "EG-07-responds-DCA"):
        r = g(cid)
        if not r:
            continue
        te, ts, td = _first(r, "EOR"), _first(r, "EOR_ESC"), _first(r, "DCA_EOR")
        rows.append(_row("R171-ENG-03", cid, "EOR 时刻", f"{_f(None if te is None else te - 10.0)} s", f"≤ {R.R171_EOR_S} s",
                         te is not None and te - 10.0 <= R.R171_EOR_S))
        rows.append(_row("R171-ENG-08", cid, "EOR → 升级", f"{_f(None if ts is None or te is None else ts - te)} s",
                         f"≤ {R.R171_EOR_ESCALATE_S} s，升级含声/触觉", ts is not None and ts - te <= R.R171_EOR_ESCALATE_S))
        rows.append(_row("R171-ENG-09", cid, "升级 → DCA", f"{_f(None if td is None or ts is None else td - ts)} s",
                         f"≤ {R.R171_DCA_AFTER_ESCALATION_S} s", td is not None and td - ts <= R.R171_DCA_AFTER_ESCALATION_S))
        if cid == "EG-06-unresponsive":
            tm = _first(r, "mrm_start")
            rows.append(_row("R171-ENG-10", cid, "首次升级 → 驾驶员不可用响应",
                             f"{_f(None if tm is None or ts is None else tm - ts)} s，停车于 {_f(r.t_standstill)} s",
                             f"≤ {R.R171_UNAVAILABLE_AFTER_S} s，并停车", tm is not None and tm - ts <= R.R171_UNAVAILABLE_AFTER_S
                             and r.t_standstill is not None))
            rows.append(_row("R171-ENG-12", cid, "1 次不可用响应后锁止", f"lockout={r.lockout}", "锁止 ≥30 min", r.lockout))
            rows.append(_row("R171-GEN-01", cid, "持续分心最终被处理（停车）", f"停车 {_f(r.t_standstill)} s", "停车", r.t_standstill is not None))
        else:
            tk = _tr(r, "T08")
            rows.append(_row("R171-ENG-11", cid, "DCA 后驾驶员接管", f"T08 于 {_f(tk[0] if tk else None)} s，DCA {_f(td)} s",
                             "接管后退出 DCA，不再进入 MRM", tk is not None and "MRM" not in r.states))
    # ---------------------------------------------------------------- EG-08 / EG-09 hands-off chain
    r = g("EG-08-hands-off-eyes-on")
    if r:
        th, ts, tm = _first(r, "HOR"), _first(r, "HOR_ESC"), _first(r, "mrm_start")
        lat = None if th is None else th - 10.0
        rows.append(_row("R171-ENG-01", r.case_id, "脱手、视线在道路：HOR 时刻", f"{_f(lat)} s",
                         f"≤ {R.R171_HOR_HANDS_OFF_S + R.R171_HOR_DELAY_MAX_S} s（5 s + 允许推迟 5 s）",
                         lat is not None and lat <= R.R171_HOR_HANDS_OFF_S + R.R171_HOR_DELAY_MAX_S))
        rows.append(_row("R171-ENG-02", r.case_id, "HOR → 升级", f"{_f(None if ts is None else ts - th)} s",
                         f"≤ {R.R171_HOR_ESCALATE_S} s", ts is not None and ts - th <= R.R171_HOR_ESCALATE_S))
        rows.append(_row("R171-ENG-10", r.case_id, "HOR 升级 → 驾驶员不可用响应", f"{_f(None if tm is None else tm - ts)} s",
                         f"≤ {R.R171_UNAVAILABLE_AFTER_S} s", tm is not None and tm - ts <= R.R171_UNAVAILABLE_AFTER_S))
    r = g("EG-09-hands-off-eyes-off")
    if r:
        th, te = _first(r, "HOR"), _first(r, "EOR")
        rows.append(_row("R171-ENG-01", r.case_id, "脱手且视线离开：HOR 时刻", f"{_f(None if th is None else th - 10.0)} s",
                         f"≤ {R.R171_HOR_HANDS_OFF_S} s（不得推迟）", th is not None and th - 10.0 <= R.R171_HOR_HANDS_OFF_S))
        tm, ts = _first(r, "mrm_start"), _first(r, "EOR_ESC")
        rows.append(_row("R171-ENG-10", r.case_id, "首次升级 → 驾驶员不可用响应", f"{_f(None if tm is None or ts is None else tm - ts)} s",
                         f"≤ {R.R171_UNAVAILABLE_AFTER_S} s", tm is not None and tm - ts <= R.R171_UNAVAILABLE_AFTER_S))
    # ---------------------------------------------------------------- EG-10 / EG-11 drowsiness
    r = g("EG-10-sleep")
    if r:
        tms, tsl, tu, tm = _first(r, "microsleep"), _first(r, "sleep"), _first(r, "unresponsive"), _first(r, "mrm_start")
        rows.append(_row("NCAP-AD-04", r.case_id, "闭眼：微睡眠 / 睡眠 → 警告与 DCA", f"微睡眠 {_f(None if tms is None else tms - 10)} s，睡眠 {_f(None if tsl is None else tsl - 10)} s",
                         "微睡眠 1–2 s，睡眠 ≥3 s（Euro NCAP DE 1.3.3/1.3.4）", tms is not None and tsl is not None))
        rows.append(_row("NCAP-AD-05", r.case_id, "无响应 → 保持转向并停车",
                         f"无响应 {_f(None if tu is None else tu - 10)} s，MRM {_f(tm)} s，停车 {_f(r.t_standstill)} s，最大横向偏移 {r.max_abs_d:.2f} m",
                         "闭眼 ≥6 s 判定无响应，停车且不离开车道", tm is not None and r.t_standstill is not None and not r.lane_departure))
    r = g("EG-11-microsleep")
    if r:
        tms = _first(r, "microsleep")
        tg = next((t for t, e in r.events if e.startswith("time_gap+")), None)
        rows.append(_row("NCAP-AD-04", r.case_id, "微睡眠 → 警告并加大 ACC 时距", f"微睡眠 {_f(tms)} s，时距 +{BASELINE.microsleep_gap_add_s} s 于 {_f(tg)} s",
                         "同时出现", tms is not None and tg is not None))
    # ---------------------------------------------------------------- EG-12 lock-out
    r = g("EG-12-three-escalations")
    if r:
        tl = _first(r, "lockout")
        esc = [t for t, e in r.events if e.endswith("_ESC")]
        refused = [t for t, why in r.refusals if "lockout" in why]
        rows.append(_row("R171-ENG-12", r.case_id, "30 min 内第 3 次升级后锁止，此后激活被拒",
                         f"升级 {len(esc)} 次（{', '.join(_f(t) for t in esc)} s），锁止 {_f(tl)} s，被拒 {len(refused)} 次",
                         "第 3 次升级时锁止", tl is not None and len(esc) >= 3 and abs(tl - esc[2]) < 1e-6 and len(refused) > 0))
        rows.append(_row("NCAP-AD-03", r.case_id, "重复分心后锁止辅助模式", f"锁止 {_f(tl)} s", "30 min 内 [3] 次", tl is not None))
        for te, ts in zip([t for t, e in r.events if e == "EOR"], esc):
            rows.append(_row("R171-ENG-08", r.case_id, "EOR → 升级", f"{ts - te:.2f} s", f"≤ {R.R171_EOR_ESCALATE_S} s", ts - te <= R.R171_EOR_ESCALATE_S))
    # ---------------------------------------------------------------- EG-13 DSM blocked
    r = g("EG-13-dsm-blocked")
    if r:
        td = _first(r, "dca_shown:dsm")
        refused = [t for t, why in r.refusals if "dsm" in why]
        rows.append(_row("NCAP-AD-01", r.case_id, "摄像头被遮挡 → 退出辅助模式", f"{_f(None if td is None else td - 10.0)} s",
                         f"≤ {R.ENCAP_AD_DSM_DEACTIVATE_S} s", td is not None and td - 10.0 <= R.ENCAP_AD_DSM_DEACTIVATE_S))
        rows.append(_row("R171-ENG-14", r.case_id, "DSM 不可用时拒绝激活", f"被拒 {len(refused)} 次（{', '.join(_f(t) for t in refused)} s）",
                         "拒绝", len(refused) > 0))
        rows.append(_row("R171-BND-01", r.case_id, "DSM 边界 → DCA → stand-by", f"状态 {r.states}", "TAKEOVER_REQUEST → STANDBY",
                         "TAKEOVER_REQUEST>STANDBY" in r.states))
    # ---------------------------------------------------------------- functional cases
    r = g("FN-01-accel-override")
    if r:
        t4, t5 = _tr(r, "T04"), _tr(r, "T05")
        n4 = _tids(r).count("T04")
        rows.append(_row("R171-OVR-02", r.case_id, "加速踏板超越后恢复", f"T04 {_f(t4[0] if t4 else None)} s，T05 {_f(t5[0] if t5 else None)} s，T04 次数 {n4}",
                         "超越 1 次并自动恢复", t4 is not None and t5 is not None and n4 == 1))
        rows.append(_row("R171-GEN-02", r.case_id, "驾驶员加速超越", f"{r.states}", "可超越", t4 is not None))
    r = g("FN-02-brake-cancel")
    if r:
        t3 = _tr(r, "T03")
        end_standby = r.states.endswith("STANDBY")
        rows.append(_row("R171-OVR-01", r.case_id, "制动中止纵向辅助、不自动恢复", f"T03 {_f(t3[0] if t3 else None)} s，结束状态 {r.states.split('>')[-1]}",
                         "STANDBY 且不自动恢复", t3 is not None and end_standby))
        rows.append(_row("R171-GEN-02", r.case_id, "驾驶员制动超越", f"{r.states}", "可超越", t3 is not None))
    r = g("FN-03-steer-override")
    if r:
        t4, t5 = _tr(r, "T04"), _tr(r, "T05")
        force = BASELINE.steer_override_nm / 0.19
        rows.append(_row("R171-OVR-03", r.case_id, "转向超越与恢复", f"T04 {_f(t4[0] if t4 else None)} s（{t4[3] if t4 else '-'}），T05 {_f(t5[0] if t5 else None)} s；阈值 {BASELINE.steer_override_nm} N·m ≈ {force:.0f} N（盘缘半径 0.19 m 假设）",
                         f"≤ {R.R171_STEER_OVERRIDE_MAX_N:.0f} N", t4 is not None and t5 is not None and force <= R.R171_STEER_OVERRIDE_MAX_N))
    r = g("FN-04-markings-lost")
    if r:
        t7, t8 = _tr(r, "T07"), _tr(r, "T08")
        rows.append(_row("R171-BND-01", r.case_id, "车道线丢失 → DCA → 接管后 stand-by",
                         f"T07 {_f(t7[0] if t7 else None)} s（{t7[3] if t7 else '-'}），T08 {_f(t8[0] if t8 else None)} s", "立即通知并可控终止",
                         t7 is not None and t8 is not None and t7[0] - 10.0 <= BASELINE.lane_marking_lost_s + 2 * BASELINE.dt))
        rows.append(_row("R171-ENG-11", r.case_id, "DCA 后驾驶员接管", f"T08 {_f(t8[0] if t8 else None)} s", "接管确认 DCA", t8 is not None))
    r = g("FN-05-markings-lost-noresponse")
    if r:
        t7, t9 = _tr(r, "T07"), _tr(r, "T09")
        dtm = None if not (t7 and t9) else t9[0] - t7[0]
        rows.append(_row("R171-BND-01", r.case_id, "边界 DCA 无人接管 → 风险减缓停车", f"DCA→MRM {_f(dtm)} s，停车 {_f(r.t_standstill)} s",
                         f"≤ {R.R171_UNAVAILABLE_AFTER_S} s", dtm is not None and dtm <= R.R171_UNAVAILABLE_AFTER_S and r.t_standstill is not None))
    r = g("FN-06-seatbelt")
    if r:
        refused = [t for t, why in r.refusals if "seatbelt" in why]
        t7 = _tr(r, "T07")
        rows.append(_row("R171-HMI-02", r.case_id, "未系安全带拒绝激活", f"被拒 {len(refused)} 次（{', '.join(_f(t) for t in refused)} s）", "拒绝", len(refused) == 2))
        rows.append(_row("R171-BND-01", r.case_id, "行驶中解开安全带 → DCA", f"T07 {_f(t7[0] if t7 else None)} s（{t7[3] if t7 else '-'}）", "DCA", t7 is not None))
    r = g("FN-07-failure")
    if r:
        t14 = _tr(r, "T14")
        rows.append(_row("R171-FLT-01", r.case_id, "整体失效 → off + 失效警告", f"T14 {_f(t14[0] if t14 else None)} s，警告 {_f(_first(r, 'failure_warning'))} s",
                         "off 且有光学警告", t14 is not None and _first(r, "failure_warning") is not None))
    r = g("FN-08-main-switch-off")
    if r:
        t13 = _tr(r, "T13")
        rows.append(_row("R171-OVR-04", r.case_id, "主开关随时关闭", f"T13 {_f(t13[0] if t13 else None)} s", "off", t13 is not None))
        rows.append(_row("R171-GEN-02", r.case_id, "驾驶员关闭系统", f"{r.states}", "off", t13 is not None))
    r = g("FN-09-follow-steady")
    if r:
        g_des = BASELINE.d0_m + BASELINE.gap_settings_s[BASELINE.gap_default_idx] * 100 / 3.6
        th = _first(r, "headway_info")
        rows.append(_row("R171-LON-05", r.case_id, "稳态跟车间距 / 时距 <2 s 提示", f"最小间距 {r.min_gap_m:.2f} m（期望 {g_des:.2f} m），提示 {_f(th)} s",
                         "间距误差 ≤1 m，首次激活时提示", abs(r.min_gap_m - g_des) <= 1.0 and th is not None))
    return rows


def suite_checks(results: dict[str, list]) -> list[dict]:
    """Aggregate checks over whole suites.  results: suite -> list of (Case, RunResult, verdict)."""
    rows = []
    lon_suites = [s for s in ("cutin_official", "cutin_grid", "cutout", "leadbrake") if s in results]
    # NCAP-VA-01 / PRJ-01 / R171-LON-04 / R171-LON-06
    for s in lon_suites:
        trip = results[s]
        n = len(trip)
        dec = max(r.peak_decel_500ms for _c, r, _v in trip)
        n_dec = sum(1 for _c, r, _v in trip if r.peak_decel_500ms > MAX_DECEL_500MS)
        rows.append(_row("NCAP-VA-01", f"suite:{s}", "500 ms 平均减速度最大值", f"{dec:.2f} m/s²（{n_dec}/{n} 次超出）", f"≤ {MAX_DECEL_500MS} m/s²", n_dec == 0))
        n_ttc = sum(1 for _c, r, v in trip if v == "FAIL_TTC")
        rows.append(_row("PRJ-01", f"suite:{s}", "无碰撞但最小 TTC < 1.0 s 的次数", f"{n_ttc}/{n}", f"TTC ≥ {MIN_TTC_S} s", None,
                         "判定已计入各用例的 verdict"))
        safe = [(c, r) for c, r, v in trip if is_safe(v)]
        harsh = sum(1 for c, r in safe if r.peak_decel_500ms > HARSH_DECEL)
        rows.append(_row("R171-LON-04", f"suite:{s}", "安全通过的运行中出现 >3.5 m/s² 制动的比例", f"{harsh}/{len(safe)}", "信息（法规无数值）", None,
                         "PASS_HARSH：为避撞需要的较大减速度，R171 5.3.6.3.1 允许"))
        unsafe = [(c, r) for c, r, v in trip if not is_safe(v)]
        beyond = sum(1 for c, r in unsafe if (r.a_kin_at_selection or 0.0) > R.R171_IMMINENT_DECEL_MPS2)
        never = sum(1 for c, r in unsafe if r.t_selected is None)
        rows.append(_row("R171-LON-06", f"suite:{s}", "不安全运行中，目标被选中时运动学需求已 >5 m/s² 的次数",
                         f"{beyond}/{len(unsafe)}（另有 {never} 次从未选中）", "超过 5 m/s² 属 AEB 范畴", None))
    # lateral
    if "curve" in results:
        trip = results["curve"]
        lat_runs = [(c, r, v) for c, r, v in trip]
        n_ay = sum(1 for _c, r, _v in lat_runs if r.peak_ay > LAT_SHORT_LIMIT + 1e-9 or r.ay_over_sustained_max_s > LAT_SHORT_S)
        rows.append(_row("R171-LAT-02", "suite:curve", "系统横向加速度峰值 / 超过申报值 +0.3 的最长连续时间",
                         f"峰值 {max(r.peak_ay for _c, r, _v in lat_runs):.2f} m/s²，最长 {max(r.ay_over_sustained_max_s for _c, r, _v in lat_runs):.2f} s（{n_ay}/{len(lat_runs)} 次超限）",
                         f"≤ {LAT_SHORT_LIMIT} m/s²；>{BASELINE.ay_declared + 0.3:.1f} m/s² 连续 ≤ {LAT_SHORT_S} s", n_ay == 0))
        n_j = sum(1 for _c, r, _v in lat_runs if r.peak_jy_500ms > LAT_JERK_MAX)
        rows.append(_row("R171-LAT-03", "suite:curve", "0.5 s 平均横向冲击度最大值", f"{max(r.peak_jy_500ms for _c, r, _v in lat_runs):.2f} m/s³（{n_j}/{len(lat_runs)} 次超限）",
                         f"≤ {LAT_JERK_MAX} m/s³", n_j == 0))
        for c, r, v in lat_runs:
            need = c.meta.get("ay_need")
            if need is not None and need <= BASELINE.ay_declared + 1e-9:
                rows.append(_row("R171-LAT-01", c.case_id, f"所需横向加速度 {need:.2f} m/s² ≤ 申报值", f"最大偏移 {r.max_abs_d:.2f} m，越线 {r.lane_departure}",
                                 "不越线", not r.lane_departure))
            if c.meta.get("csa") and need is not None and need > BASELINE.ay_curve_target:
                rows.append(_row("R171-LAT-04", c.case_id, f"所需 {need:.2f} m/s² > 弯道限速目标，系统应降速",
                                 f"最低车速 {r.v_min_kph:.1f} km/h（设定 {r.v0_kph:.0f}），系统峰值 {r.peak_ay:.2f} m/s²，越线 {r.lane_departure}",
                                 "降速且不越线", r.v_min_kph < r.v0_kph - 1.0 and not r.lane_departure))
            if not c.meta.get("csa") and (r.lane_departure or r.t_d05 is not None):
                dca = r.first("dca_shown:lateral_limit")
                rows.append(_row("R171-LAT-05", c.case_id, "到达横向边界：DCA 不晚于越线", f"DCA {_f(dca)} s，越线 {_f(r.t_lane_departure)} s，判定 {v}",
                                 "BOUNDARY_HANDLED", v == "BOUNDARY_HANDLED"))
                appr = r.first("boundary_approaching")
                lead = None if (appr is None or dca is None) else dca - appr
                rows.append(_row("R171-BND-02", c.case_id, "“接近边界”提示早于 DCA 的时间", f"{_f(lead)} s", "≥ 3 s（设计目标，法规未给数值）",
                                 lead is not None and lead >= 3.0))
    # fluctuation and default-off over every run
    all_runs = [r for trip in results.values() for _c, r, _v in trip]
    worst = 0
    for r in all_runs:
        ts = [t for t, a, b, tid, _d in r.transitions if a != b and tid in ("T02", "T03", "T06", "T07", "T08")]
        for i in range(len(ts)):
            worst = max(worst, sum(1 for x in ts[i:] if x - ts[i] <= 2.0))
    rows.append(_row("R171-BND-03", "suite:all", "任意 2 s 内 active/stand-by 相关切换的最大次数", f"{worst}（共 {len(all_runs)} 次运行）", "≤ 2", worst <= 2))
    first_ok = sum(1 for r in all_runs if r.transitions and r.transitions[0][3] == "T01" and r.transitions[0][1] == "OFF")
    rows.append(_row("R171-HMI-01", "suite:all", "上电默认 off，第一个转换为主开关 T01", f"{first_ok}/{len(all_runs)}", "全部", first_ok == len(all_runs)))
    return rows


def robustness_checks(rob: dict[str, list[str]]) -> list[dict]:
    """rob: official case id -> verdicts over the noise seeds (R171 Annex 3 Appendix 4: >= 90 %)."""
    rows = []
    for cid, vs in rob.items():
        n_safe = sum(1 for v in vs if is_safe(v))
        share = n_safe / len(vs)
        rows.append(_row("R171-VAL-01", cid, f"{len(vs)} 个噪声种子下安全通过的比例", f"{n_safe}/{len(vs)}（{share:.0%}）",
                         f"≥ {R.R171_CAPABILITY_SHARE:.0%}（仅对本模型能避撞的用例有意义）", share >= R.R171_CAPABILITY_SHARE))
    return rows


_ = defaultdict
